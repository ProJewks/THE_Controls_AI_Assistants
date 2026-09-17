#!/usr/bin/env python3
"""
Studio 5000 Logix Designer Documentation MCP Server

This MCP server provides access to Studio 5000/Logix Designer instruction documentation,
making it easy to search for and retrieve information about PLC instructions, programming
syntax, and best practices directly within AI conversations.
"""

import asyncio
import html as html_lib
import json
import os
import re
import sys
import threading
import importlib.util
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import argparse
from dataclasses import dataclass, asdict

# Import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Handle relative import for cache_manager (works both as script and module)
try:
    from .cache_manager import shared_cache_manager
except ImportError:
    # Fallback for when run as script
    cache_manager_path = os.path.join(os.path.dirname(__file__), 'cache_manager.py')
    if os.path.exists(cache_manager_path):
        spec = importlib.util.spec_from_file_location("cache_manager", cache_manager_path)
        cache_manager_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cache_manager_module)
        shared_cache_manager = cache_manager_module.shared_cache_manager
    else:
        # Create a minimal fallback cache manager
        class MockCacheManager:
            def get_cache_statistics(self):
                return {'overall': {'total_requests': 0, 'total_hits': 0, 'overall_hit_rate': 0}}
            def get_cache_lock(self, name):
                import threading
                return threading.Lock()
            def is_cache_valid(self, files, max_age_days=30):
                return False
        shared_cache_manager = MockCacheManager()

from code_generator.l5x_generator import L5XGenerator, L5XProject, Program, Routine, LadderRung, create_motor_control_example
from ai_assistant.code_assistant import CodeAssistant
from ai_assistant.mcp_integration import create_mcp_integrated_assistant
from sdk_interface.studio5000_sdk import studio5000_sdk
from sdk_documentation.mcp_sdk_integration import SDKMCPIntegration, SDKMCPTools
from documentation.instruction_mcp_integration import InstructionMCPIntegration, InstructionMCPTools
from l5x_analyzer.l5x_mcp_integration import L5XSDKMCPIntegration, L5XMCPTools
from drawings_analyzer.pdf_mcp_integration import PDFMCPIntegration, PDFMCPTools
from tag_analyzer.tag_mcp_integration import TagMCPIntegration, TagMCPTools

# MCP imports (we'll implement a simplified version)
class MCPServer:
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools = {}
        self.resources = {}
    
    def add_tool(self, name: str, description: str, handler):
        self.tools[name] = {
            "name": name,
            "description": description,
            "handler": handler
        }
    
    def add_resource(self, uri: str, description: str, handler):
        self.resources[uri] = {
            "uri": uri,
            "description": description,
            "handler": handler
        }

@dataclass
class Instruction:
    """Represents a Studio 5000 instruction"""
    name: str
    category: str
    description: str
    file_path: str
    languages: List[str]
    syntax: Optional[str] = None
    parameters: Optional[List[Dict]] = None
    examples: Optional[str] = None

class Studio5000Parser:
    """Parses Studio 5000 HTML documentation"""

    def __init__(self, doc_root: str, version: str = "default"):
        self.doc_root = Path(doc_root)
        self.version = version
        self.instructions = {}
        self.categories = {}
        # Cache lives next to this file, namespaced per documentation version so
        # switching between e.g. v35 and v37 doc roots doesn't clobber a shared
        # cache file and force a full re-parse every time you switch back.
        safe_version = re.sub(r'[^A-Za-z0-9_.-]', '_', version)
        self.INDEX_CACHE_FILE = Path(__file__).parent / f"instruction_index_cache_{safe_version}.json"
        # Rockwell changed documentation authoring tools between Logix Designer
        # versions: v35 and earlier ship a flat folder of numbered .htm files
        # with a single "17691.htm" master index ("legacy"); v36+ ship an
        # Oxygen WebHelp site with one topic-per-file under help/clinset/<Category>/
        # ("oxygen_webhelp"). Detect which one this doc_root actually is so the
        # right parser runs instead of assuming the docs are simply missing.
        self.format = self._detect_format()

    def _detect_format(self) -> str:
        if (self.doc_root / "17691.htm").exists():
            return "legacy"
        if (self.doc_root / "help" / "clinset").is_dir():
            return "oxygen_webhelp"
        return "legacy"

    def parse_main_index(self) -> Dict[str, Any]:
        """Parse the main instruction set index"""
        index_file = self.doc_root / "17691.htm"
        if not index_file.exists():
            raise FileNotFoundError(f"Main index file not found: {index_file}")
        
        with open(index_file, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        categories = {}
        
        # Find instruction category links
        links = soup.find_all('a', href=re.compile(r'\d+\.htm'))
        for link in links:
            if 'Instructions' in link.get_text():
                category_name = link.get_text().strip()
                category_file = link.get('href')
                categories[category_name] = category_file
        
        self.categories = categories
        return categories
    
    def parse_instruction_file(self, file_path: str) -> Optional[Instruction]:
        """Parse an individual instruction file"""
        full_path = self.doc_root / file_path
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
            
            # Extract title
            title_elem = soup.find('title')
            title = title_elem.get_text().strip() if title_elem else ""
            
            # Extract instruction name from title. Rockwell's convention is
            # "Descriptive Name (ABBR)" - e.g. "DINT to String (DTOS)" or
            # "String to DINT (STOD)". Prefer that parenthesized abbreviation
            # at the end of the title; fall back to the old "first ALL-CAPS
            # run anywhere in the title" behavior only when there isn't one.
            # Without this, any title whose descriptive name itself contains
            # an all-caps word before its own abbreviation - "DINT to String
            # (DTOS)" matches "DINT" first, "PID Enhanced (PIDE)" matches
            # "PID" first - got silently indexed under the wrong name, and the
            # real instruction (DTOS, STOD, PIDE, ...) was never indexed at all.
            paren_match = re.search(r'\(([A-Z]{2,}[A-Z0-9]*)\)\s*$', title.strip())
            if paren_match:
                instruction_name = paren_match.group(1)
            else:
                match = re.search(r'([A-Z]{2,}[A-Z0-9]*)', title)
                instruction_name = match.group(1) if match else ""
            
            # Extract breadcrumb for category
            breadcrumb = soup.find('p', class_='breadcrumbs')
            category = ""
            if breadcrumb:
                links = breadcrumb.find_all('a')
                for link in links:
                    if 'Instructions' in link.get_text():
                        category = link.get_text().strip()
                        break
            
            # Extract description from first paragraph
            content_section = soup.find('div', id='content_section')
            description = ""
            if content_section:
                first_p = content_section.find('p')
                if first_p:
                    description = first_p.get_text().strip()
            
            # Determine supported languages from icons
            languages = []
            img_tags = soup.find_all('img', src=re.compile(r'o151\d+\.jpg'))
            if img_tags:
                # Based on the pattern seen in the documentation
                if any('o15168.jpg' in img.get('src', '') for img in img_tags):
                    languages.append('Ladder Diagram')
                if any('o15169.jpg' in img.get('src', '') for img in img_tags):
                    languages.append('Function Block')
                if any('o15170.jpg' in img.get('src', '') for img in img_tags):
                    languages.append('Structured Text')
            
            return Instruction(
                name=instruction_name,
                category=category,
                description=description,
                file_path=file_path,
                languages=languages,
                syntax=self._extract_syntax(soup),
                parameters=self._extract_parameters(soup),
                examples=self._extract_examples(soup)
            )
        
        except Exception as e:
            import sys
            print(f"Error parsing {file_path}: {e}", file=sys.stderr)
            return None
    
    def _extract_syntax(self, soup) -> Optional[str]:
        """Extract syntax information from the HTML"""
        # Look for syntax tables or code blocks
        syntax_patterns = [
            'Syntax',
            'Parameters',
            'Operands'
        ]
        
        for pattern in syntax_patterns:
            heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4'] and 
                              pattern.lower() in tag.get_text().lower())
            if heading:
                # Get the next table or paragraph
                next_elem = heading.find_next_sibling(['table', 'p', 'div'])
                if next_elem:
                    return next_elem.get_text().strip()
        
        return None
    
    def _extract_parameters(self, soup) -> Optional[List[Dict]]:
        """Extract parameter information"""
        parameters = []
        
        # Look for parameter tables
        tables = soup.find_all('table')
        for table in tables:
            headers = table.find_all('th')
            if len(headers) >= 2:
                header_texts = [th.get_text().strip().lower() for th in headers]
                if any('parameter' in h or 'operand' in h for h in header_texts):
                    rows = table.find_all('tr')[1:]  # Skip header row
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            param = {
                                'name': cells[0].get_text().strip(),
                                'description': cells[1].get_text().strip()
                            }
                            if len(cells) > 2:
                                param['type'] = cells[2].get_text().strip()
                            parameters.append(param)
        
        return parameters if parameters else None
    
    def _extract_examples(self, soup) -> Optional[str]:
        """Extract example information"""
        example_patterns = ['example', 'sample', 'usage']
        
        for pattern in example_patterns:
            heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4'] and 
                              pattern.lower() in tag.get_text().lower())
            if heading:
                example_content = []
                current = heading.find_next_sibling()
                while current and current.name not in ['h1', 'h2', 'h3', 'h4']:
                    if current.name in ['p', 'pre', 'code', 'div']:
                        example_content.append(current.get_text().strip())
                    current = current.find_next_sibling()
                
                if example_content:
                    return '\n\n'.join(example_content)
        
        return None
    
    def _compute_doc_fingerprint(self, html_files: List[Path]) -> Dict[str, Any]:
        """Cheap fingerprint of the doc set (file count + newest mtime) to detect changes"""
        newest_mtime = max((f.stat().st_mtime for f in html_files), default=0)
        return {
            "doc_root": str(self.doc_root),
            "file_count": len(html_files),
            "newest_mtime": newest_mtime,
        }

    def _load_cached_index(self, fingerprint: Dict[str, Any]) -> Optional[Dict[str, Instruction]]:
        """Load the instruction index from disk if the cache matches the current doc set"""
        if not self.INDEX_CACHE_FILE.exists():
            return None

        try:
            with open(self.INDEX_CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        if cached.get("fingerprint") != fingerprint:
            return None

        try:
            self.categories = cached["categories"]
            return {
                name: Instruction(**fields)
                for name, fields in cached["instructions"].items()
            }
        except (KeyError, TypeError):
            return None

    def _save_cached_index(self, fingerprint: Dict[str, Any], instructions: Dict[str, Instruction]) -> None:
        """Persist the parsed instruction index so future startups can skip re-parsing"""
        try:
            with open(self.INDEX_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "fingerprint": fingerprint,
                    "categories": self.categories,
                    "instructions": {name: asdict(inst) for name, inst in instructions.items()},
                }, f)
        except OSError as e:
            print(f"Warning: could not write instruction index cache: {e}", file=sys.stderr)

    def build_instruction_index(self) -> Dict[str, Instruction]:
        """Build a comprehensive index of all instructions, reusing a cached index when the docs haven't changed"""
        if self.format == "oxygen_webhelp":
            return self._build_instruction_index_oxygen_webhelp()
        return self._build_instruction_index_legacy()

    def _build_instruction_index_legacy(self) -> Dict[str, Instruction]:
        """Parse the flat numbered-.htm documentation shipped with Logix Designer v35 and earlier"""
        # Find all HTML files that might be instructions
        html_files = list(self.doc_root.glob("*.htm"))
        fingerprint = self._compute_doc_fingerprint(html_files)

        cached_instructions = self._load_cached_index(fingerprint)
        if cached_instructions is not None:
            self.instructions = cached_instructions
            return cached_instructions

        # Parse categories first
        self.parse_main_index()

        instructions = {}
        for html_file in html_files:
            instruction = self.parse_instruction_file(html_file.name)
            if instruction and instruction.name:
                instructions[instruction.name.upper()] = instruction

        self.instructions = instructions
        self._save_cached_index(fingerprint, instructions)
        return instructions

    def _build_instruction_index_oxygen_webhelp(self) -> Dict[str, Instruction]:
        """Parse the Oxygen WebHelp documentation shipped with Logix Designer v36+.

        Instead of a flat folder of numbered .htm files with one master index,
        this format has one topic per file under help/clinset/<Category>/, and
        real instruction topics are reliably titled "<Description> (<MNEMONIC>)"
        e.g. "Examine if Closed (XIC)" - other topics in the same folders (UI
        dialog-box help, etc.) don't match that pattern and are skipped so they
        don't pollute instruction search results.
        """
        clinset_root = self.doc_root / "help" / "clinset"
        html_files = [
            f for f in clinset_root.glob("*/*.html")
            if not any(part.lower() == "graphics" for part in f.parts)
        ]
        fingerprint = self._compute_doc_fingerprint(html_files)

        cached_instructions = self._load_cached_index(fingerprint)
        if cached_instructions is not None:
            self.instructions = cached_instructions
            return cached_instructions

        name_pattern = re.compile(r'\(([A-Z][A-Z0-9_]{1,15})\)\s*$')
        instructions: Dict[str, Instruction] = {}
        categories: Dict[str, List[str]] = {}

        for html_file in html_files:
            try:
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except OSError:
                continue

            title_match = re.search(r'<title>(.*?)</title>', content, re.S)
            if not title_match:
                continue
            title = html_lib.unescape(re.sub(r'<[^>]+>', '', title_match.group(1))).strip()

            name_match = name_pattern.search(title)
            if not name_match:
                # Not an instruction topic page (e.g. a dialog-box help page) - skip it
                continue

            name = name_match.group(1).upper()
            description = title[:name_match.start()].strip(' -–—')
            category = html_file.parent.name

            categories.setdefault(category, []).append(name)
            # A handful of instructions have more than one topic page (overloads,
            # split parts) - keep the first one found, consistent with the legacy
            # parser's "first write wins" behavior for duplicate names.
            if name not in instructions:
                instructions[name] = Instruction(
                    name=name,
                    category=category,
                    description=description,
                    file_path=str(html_file.relative_to(self.doc_root)),
                    languages=[],
                )

        self.categories = categories
        self.instructions = instructions
        self._save_cached_index(fingerprint, instructions)
        return instructions

class Studio5000MCPServer:
    """MCP Server for Studio 5000 documentation with optimized lazy loading"""

    # Some Logix Designer doc versions ship help files that are indexed far
    # thinner than others even though the instruction set itself is unchanged
    # - e.g. v37's help folder was reorganized around OPC UA/networking and
    # hardware changes, not the instruction language, so its per-instruction
    # syntax/parameters are often missing where v36 (functionally the same
    # software release) still has them. This maps a version to the reference
    # version its instruction syntax/parameters may be backfilled from when
    # its own docs come back empty.
    SYNTAX_REFERENCE_VERSION = {
        'v37': 'v36',
    }

    def __init__(self, doc_root: Union[str, Dict[str, str]]):
        # doc_root is either a single path (backward compatible - one Logix
        # Designer version's documentation) or a {version_label: path} dict
        # so multiple installed versions (e.g. "v35" and "v37") can be
        # queried side by side in the same running server, without a restart
        # or env-var change to switch between them.
        self.doc_roots = self._normalize_doc_roots(doc_root)
        self.default_version = next(iter(self.doc_roots))
        self.parsers = {
            version: Studio5000Parser(path, version)
            for version, path in self.doc_roots.items()
        }
        self.server = MCPServer("studio5000-ai-assistant", "2.0.0")
        self.instructions_by_version = {}

        # Initialize basic components immediately (lightweight)
        self.l5x_generator = L5XGenerator()
        self.code_assistant = CodeAssistant(mcp_server=self)
        self.enhanced_assistant = create_mcp_integrated_assistant(self)
        self.studio5000_sdk = studio5000_sdk

        # Shared sentence transformer model for all vector databases
        self._shared_model = None
        self._model_lock = threading.Lock()

        # Lazy initialization flags and cached integrations
        self._sdk_integration = None
        self._sdk_tools = None
        self._instruction_integrations = {}  # version -> InstructionMCPIntegration
        self._instruction_tools_cache = {}   # version -> InstructionMCPTools
        self._l5x_integration = None
        self._l5x_tools = None
        self._pdf_integration = None
        self._pdf_tools = None
        self._tag_integration = None
        self._tag_tools = None

        # Initialization locks for thread safety
        self._init_locks = {
            'sdk': threading.Lock(),
            'instruction': threading.Lock(),
            'l5x': threading.Lock(),
            'pdf': threading.Lock(),
            'tag': threading.Lock()
        }

        # Fast basic initialization only - vector DBs loaded on demand
        self._initialize_basic()

    @staticmethod
    def _normalize_doc_roots(doc_root: Union[str, Dict[str, str]]) -> Dict[str, str]:
        """Turn the constructor's doc_root argument into a {version_label: path} dict"""
        if isinstance(doc_root, dict):
            if not doc_root:
                raise ValueError("doc_root dict must contain at least one version")
            return dict(doc_root)
        # Single path - tag it with the version segment from the path itself
        # (".../ENU/v35/Bin/Help/..." -> "v35") so it still shows up correctly
        # in list_documentation_versions and per-version cache filenames.
        match = re.search(r'[\\/](v\d+)[\\/]', str(doc_root))
        version = match.group(1) if match else "default"
        return {version: doc_root}

    @property
    def doc_root(self) -> str:
        """Backward-compat accessor: the default version's doc root path"""
        return self.doc_roots[self.default_version]

    @property
    def parser(self) -> 'Studio5000Parser':
        """Backward-compat accessor: the default version's parser"""
        return self.parsers[self.default_version]

    @property
    def instructions(self) -> Dict[str, 'Instruction']:
        """Backward-compat accessor: the default version's instruction index"""
        return self.instructions_by_version.get(self.default_version, {})

    def _resolve_version(self, version: Optional[str]) -> str:
        """Resolve a caller-supplied version label, defaulting when omitted and
        raising a clear error for an unrecognized one instead of silently
        falling back to the wrong version's data."""
        if version is None:
            return self.default_version
        if version not in self.doc_roots:
            raise ValueError(
                f"Unknown Logix Designer documentation version '{version}'. "
                f"Available: {', '.join(sorted(self.doc_roots))}"
            )
        return version

    def _backfill_syntax_from_reference(self, result: Optional[Dict], name: str, version: str) -> Optional[Dict]:
        """If `result` has no syntax/parameters, backfill them from this
        version's reference version (see SYNTAX_REFERENCE_VERSION) when that
        version is loaded and has the same instruction. The result is tagged
        with `syntax_source_version` so callers can tell the syntax/parameters
        didn't come from `version`'s own documentation."""
        if not result or result.get('syntax') or result.get('parameters'):
            return result
        reference_version = self.SYNTAX_REFERENCE_VERSION.get(version)
        if not reference_version or reference_version not in self.instructions_by_version:
            return result
        reference_instruction = self.instructions_by_version[reference_version].get(name.upper())
        if not reference_instruction:
            return result
        if reference_instruction.syntax:
            result['syntax'] = reference_instruction.syntax
        if reference_instruction.parameters:
            result['parameters'] = reference_instruction.parameters
        if result.get('syntax') or result.get('parameters'):
            result['syntax_source_version'] = reference_version
        return result

    def _initialize_basic(self):
        """Fast basic initialization - only load instruction index, no vector DBs"""
        import sys
        print("Starting fast initialization...", file=sys.stderr)
        for version, parser in self.parsers.items():
            try:
                self.instructions_by_version[version] = parser.build_instruction_index()
            except Exception as e:
                print(f"⚠️ Could not build instruction index for {version} ({parser.doc_root}): {e}", file=sys.stderr)
                self.instructions_by_version[version] = {}
        total = sum(len(v) for v in self.instructions_by_version.values())
        print(
            f"✅ Basic initialization complete. {total} instructions loaded across "
            f"{len(self.parsers)} version(s): {', '.join(self.doc_roots)} (default: {self.default_version}).",
            file=sys.stderr
        )
        print("📚 Vector databases will load automatically when needed for semantic search.", file=sys.stderr)
        
        # Register all tools (lightweight operation)
        self._register_tools()
        print("🔧 MCP tools registered successfully", file=sys.stderr)
    
    def _get_shared_model(self):
        """Get shared sentence transformer model, initializing if needed"""
        if self._shared_model is None:
            with self._model_lock:
                if self._shared_model is None:  # Double-check pattern
                    try:
                        import sys
                        print("🔄 Loading shared sentence transformer model...", file=sys.stderr)
                        from sentence_transformers import SentenceTransformer
                        self._shared_model = SentenceTransformer('all-MiniLM-L6-v2')
                        print("✅ Shared model loaded successfully", file=sys.stderr)
                    except Exception as e:
                        print(f"❌ Failed to load shared model: {e}", file=sys.stderr)
                        self._shared_model = None
        return self._shared_model
    
    @property
    def sdk_integration(self):
        """Lazy-loaded SDK integration"""
        if self._sdk_integration is None:
            with self._init_locks['sdk']:
                if self._sdk_integration is None:
                    print("🔄 Initializing SDK documentation system...", file=sys.stderr)
                    self._sdk_integration = SDKMCPIntegration()
                    # Inject shared model and cache manager
                    if hasattr(self._sdk_integration, 'vector_db'):
                        if hasattr(self._sdk_integration.vector_db, 'model'):
                            self._sdk_integration.vector_db.model = self._get_shared_model()
                        # Inject shared cache manager for optimized caching
                        self._sdk_integration.vector_db.cache_manager = shared_cache_manager
                    print("✅ SDK system ready", file=sys.stderr)
        return self._sdk_integration
    
    @property 
    def sdk_tools(self):
        """Lazy-loaded SDK tools"""
        if self._sdk_tools is None:
            self._sdk_tools = SDKMCPTools(self.sdk_integration)
        return self._sdk_tools
    
    def get_instruction_integration(self, version: Optional[str] = None) -> 'InstructionMCPIntegration':
        """Lazy-loaded instruction integration for a specific Logix Designer documentation version"""
        version = self._resolve_version(version)
        if version not in self._instruction_integrations:
            with self._init_locks['instruction']:
                if version not in self._instruction_integrations:
                    print(f"🔄 Initializing instruction documentation system for {version}...", file=sys.stderr)
                    # Each version gets its own vector cache directory so v35 and
                    # v37 embeddings never overwrite each other.
                    integration = InstructionMCPIntegration(cache_dir=f"instruction_vector_cache_{version}")
                    # Inject shared model and cache manager
                    if hasattr(integration, 'vector_db'):
                        if hasattr(integration.vector_db, 'model'):
                            integration.vector_db.model = self._get_shared_model()
                        # Inject shared cache manager for optimized caching
                        integration.vector_db.cache_manager = shared_cache_manager
                    self._instruction_integrations[version] = integration
                    print(f"✅ Instruction system ready for {version}", file=sys.stderr)
        return self._instruction_integrations[version]

    def get_instruction_tools(self, version: Optional[str] = None) -> 'InstructionMCPTools':
        """Lazy-loaded instruction tools for a specific Logix Designer documentation version"""
        version = self._resolve_version(version)
        if version not in self._instruction_tools_cache:
            self._instruction_tools_cache[version] = InstructionMCPTools(self.get_instruction_integration(version))
        return self._instruction_tools_cache[version]

    @property
    def instruction_integration(self):
        """Backward-compat accessor: instruction integration for the default version"""
        return self.get_instruction_integration()

    @property
    def instruction_tools(self):
        """Backward-compat accessor: instruction tools for the default version"""
        return self.get_instruction_tools()
    
    @property
    def l5x_integration(self):
        """Lazy-loaded L5X integration"""
        if self._l5x_integration is None:
            with self._init_locks['l5x']:
                if self._l5x_integration is None:
                    print("🔄 Initializing L5X analyzer system...", file=sys.stderr)
                    self._l5x_integration = L5XSDKMCPIntegration()
                    # Inject shared model and cache manager
                    if hasattr(self._l5x_integration, 'vector_db'):
                        if hasattr(self._l5x_integration.vector_db, 'model'):
                            self._l5x_integration.vector_db.model = self._get_shared_model()
                        # Inject shared cache manager for optimized caching
                        self._l5x_integration.vector_db.cache_manager = shared_cache_manager
                    print("✅ L5X system ready", file=sys.stderr)
        return self._l5x_integration
    
    @property
    def l5x_tools(self):
        """Lazy-loaded L5X tools"""
        if self._l5x_tools is None:
            self._l5x_tools = L5XMCPTools
        return self._l5x_tools
    
    @property
    def pdf_integration(self):
        """Lazy-loaded PDF integration"""
        if self._pdf_integration is None:
            with self._init_locks['pdf']:
                if self._pdf_integration is None:
                    print("🔄 Initializing PDF drawings analyzer system...", file=sys.stderr)
                    self._pdf_integration = PDFMCPIntegration()
                    # Inject shared model and cache manager
                    if hasattr(self._pdf_integration, 'vector_db'):
                        if hasattr(self._pdf_integration.vector_db, 'model'):
                            self._pdf_integration.vector_db.model = self._get_shared_model()
                        # Inject shared cache manager for optimized caching
                        self._pdf_integration.vector_db.cache_manager = shared_cache_manager
                    print("✅ PDF system ready", file=sys.stderr)
        return self._pdf_integration
    
    @property
    def pdf_tools(self):
        """Lazy-loaded PDF tools"""
        if self._pdf_tools is None:
            self._pdf_tools = PDFMCPTools
        return self._pdf_tools
    
    @property
    def tag_integration(self):
        """Lazy-loaded tag integration"""
        if self._tag_integration is None:
            with self._init_locks['tag']:
                if self._tag_integration is None:
                    print("🔄 Initializing tag analyzer system...", file=sys.stderr)
                    self._tag_integration = TagMCPIntegration()
                    # Inject shared model and cache manager
                    if hasattr(self._tag_integration, 'vector_db'):
                        if hasattr(self._tag_integration.vector_db, 'model'):
                            self._tag_integration.vector_db.model = self._get_shared_model()
                        # Inject shared cache manager for optimized caching
                        self._tag_integration.vector_db.cache_manager = shared_cache_manager
                    print("✅ Tag system ready", file=sys.stderr)
        return self._tag_integration
    
    @property
    def tag_tools(self):
        """Lazy-loaded tag tools"""
        if self._tag_tools is None:
            self._tag_tools = TagMCPTools
        return self._tag_tools
    
    async def _ensure_instruction_db_ready(self, version: Optional[str] = None):
        """Ensure the instruction vector database for one documentation version is fully initialized"""
        version = self._resolve_version(version)
        integration = self.get_instruction_integration(version)

        # Initialize with that version's instructions if not already done
        if hasattr(integration, 'initialize'):
            try:
                await integration.initialize(self.instructions_by_version[version], force_rebuild=False)
            except Exception as e:
                print(f"Warning: Could not initialize instruction vector DB for {version}: {e}", file=sys.stderr)
    
    async def _ensure_sdk_db_ready(self):
        """Ensure the SDK vector database is fully initialized"""
        # Trigger lazy loading by accessing the property  
        _ = self.sdk_integration
        
        # Initialize if not already done
        if hasattr(self.sdk_integration, 'initialize'):
            try:
                await self.sdk_integration.initialize(force_rebuild=False)
            except Exception as e:
                print(f"Warning: Could not initialize SDK vector DB: {e}", file=sys.stderr)
        
    def _register_tools(self):
        """Register all MCP tools - lightweight, no vector DB initialization"""
        self.server.add_tool(
            "search_instructions",
            "Search for PLC instructions by name, category, or description. "
            "Optionally scope to a specific Logix Designer documentation version "
            "(see list_documentation_versions) if multiple are loaded.",
            self.search_instructions
        )

        self.server.add_tool(
            "get_instruction",
            "Get detailed information about a specific PLC instruction. "
            "Optionally scope to a specific Logix Designer documentation version.",
            self.get_instruction
        )

        self.server.add_tool(
            "list_categories",
            "List all available instruction categories. "
            "Optionally scope to a specific Logix Designer documentation version.",
            self.list_categories
        )

        self.server.add_tool(
            "list_instructions_by_category",
            "List all instructions in a specific category. "
            "Optionally scope to a specific Logix Designer documentation version.",
            self.list_instructions_by_category
        )

        self.server.add_tool(
            "get_instruction_syntax",
            "Get the syntax and parameters for a specific instruction. "
            "Optionally scope to a specific Logix Designer documentation version, "
            "since syntax/availability can differ between major revisions.",
            self.get_instruction_syntax
        )

        self.server.add_tool(
            "list_documentation_versions",
            "List the Logix Designer documentation versions currently loaded "
            "(e.g. v35, v37) and which one is the default, for use with the "
            "`version` argument on the instruction lookup tools.",
            self.list_documentation_versions
        )

        # Add new AI-powered code generation tools
        self.server.add_tool(
            "generate_ladder_logic",
            "Generate ladder logic from natural language specification",
            self.generate_ladder_logic
        )
        
        self.server.add_tool(
            "create_l5x_project",
            "Create complete L5X project file from specification",
            self.create_l5x_project
        )
        
        self.server.add_tool(
            "create_l5x_routine",
            "Create L5X routine export file that can be imported into existing ACD projects",
            self.create_l5x_routine
        )
        
        self.server.add_tool(
            "validate_ladder_logic", 
            "Fast and reliable validation of ladder logic using Studio 5000 documentation",
            self.validate_ladder_logic
        )
        
        self.server.add_tool(
            "create_acd_project",
            "Create real Studio 5000 .ACD project file using official SDK",
            self.create_acd_project
        )
        
        # Add SDK documentation search tools
        self.server.add_tool(
            "search_sdk_documentation",
            "Search Studio 5000 SDK documentation using natural language",
            self.search_sdk_documentation
        )
        
        self.server.add_tool(
            "get_sdk_operation_info",
            "Get detailed information about a specific SDK operation",
            self.get_sdk_operation_info
        )
        
        self.server.add_tool(
            "list_sdk_categories", 
            "List all SDK operation categories",
            self.list_sdk_categories
        )
        
        self.server.add_tool(
            "get_sdk_operations_by_category",
            "Get all SDK operations in a specific category",
            self.get_sdk_operations_by_category
        )
        
        self.server.add_tool(
            "get_logix_project_methods",
            "Get LogixProject methods, optionally filtered by category",
            self.get_logix_project_methods
        )
        
        self.server.add_tool(
            "suggest_sdk_operations",
            "Suggest relevant SDK operations based on context",
            self.suggest_sdk_operations
        )
        
        self.server.add_tool(
            "get_sdk_statistics",
            "Get SDK documentation statistics and overview",
            self.get_sdk_statistics
        )
        
        # Add L5X analyzer tools for production-scale L5X files
        self.server.add_tool(
            "index_exported_l5x_files", 
            "Index exported L5X files directly for semantic search",
            self.index_exported_l5x_files
        )
        
        self.server.add_tool(
            "index_acd_project",
            "Index ACD/L5K project for semantic search of routines and components",
            self.index_acd_project
        )
        
        self.server.add_tool(
            "search_l5x_content",
            "Semantic search within indexed L5X content",
            self.search_l5x_content
        )
        
        self.server.add_tool(
            "find_insertion_point",
            "Find optimal location to insert new ladder logic",
            self.find_insertion_point
        )
        
        self.server.add_tool(
            "smart_insert_logic",
            "Directly insert new ladder logic into L5X file at optimal location",
            self.smart_insert_logic
        )
        
        self.server.add_tool(
            "extract_routine_content",
            "Extract specific routine content for analysis",
            self.extract_routine_content
        )
        
        self.server.add_tool(
            "analyze_routine_structure",
            "Analyze structure and complexity of an indexed routine",
            self.analyze_routine_structure
        )
        
        self.server.add_tool(
            "find_related_components",
            "Find components related to a given component",
            self.find_related_components
        )
        
        self.server.add_tool(
            "get_project_overview",
            "Get comprehensive overview of project structure",
            self.get_project_overview
        )
        
        # Add PDF drawings tools
        self.server.add_tool(
            "index_pdf_drawings",
            "Index PDF technical drawings file for semantic search",
            self.index_pdf_drawings
        )
        
        self.server.add_tool(
            "search_drawings",
            "Search technical drawings using natural language",
            self.search_drawings
        )
        
        self.server.add_tool(
            "find_equipment_context",
            "Find all drawings and context related to specific equipment",
            self.find_equipment_context
        )
        
        self.server.add_tool(
            "get_drawing_details",
            "Get detailed information about a specific drawing",
            self.get_drawing_details
        )
        
        self.server.add_tool(
            "get_equipment_connections",
            "Get electrical connections and wiring info for equipment",
            self.get_equipment_connections
        )
        
        # Add tag analyzer tools for Studio 5000 tag CSV files
        self.server.add_tool(
            "index_tag_csv",
            "Index Studio 5000 tag CSV export for semantic search",
            self.index_tag_csv
        )
        
        self.server.add_tool(
            "search_tags",
            "Search through indexed tags using natural language",
            self.search_tags
        )
        
        self.server.add_tool(
            "find_device",
            "Find specific devices by description or function",
            self.find_device
        )
        
        self.server.add_tool(
            "get_module_tags",
            "Get all tags for a specific module (rack/slot)",
            self.get_module_tags
        )
        
        self.server.add_tool(
            "find_i_o_point",
            "Find specific I/O points by address or description",
            self.find_i_o_point
        )
        
        self.server.add_tool(
            "analyze_i_o_usage",
            "Analyze I/O usage and capacity across the system",
            self.analyze_i_o_usage
        )
        
        self.server.add_tool(
            "find_related_tags",
            "Find tags related to a given tag",
            self.find_related_tags
        )
        
        self.server.add_tool(
            "get_device_overview",
            "Get comprehensive overview of devices in the system",
            self.get_device_overview
        )
        
        self.server.add_tool(
            "get_safety_tags",
            "Get all safety-related tags",
            self.get_safety_tags
        )
        
        self.server.add_tool(
            "get_motor_tags",
            "Get all motor control tags",
            self.get_motor_tags
        )
        
        self.server.add_tool(
            "get_sensor_tags",
            "Get all sensor tags",
            self.get_sensor_tags
        )
        
        # Performance monitoring tools
        self.server.add_tool(
            "get_cache_performance",
            "Get vector database cache performance statistics",
            self.get_cache_performance
        )
    
    async def search_instructions(self, query: str, category: Optional[str] = None, version: Optional[str] = None) -> List[Dict]:
        """Enhanced search for instructions using vector database.

        version: optional Logix Designer documentation version label (e.g. "v35",
        "v37") - see list_documentation_versions for what's available. Defaults
        to the server's default version when omitted.
        """
        version = self._resolve_version(version)
        try:
            # Ensure vector database is ready
            await self._ensure_instruction_db_ready(version)

            # Use vector database for semantic search
            vector_results = await self.get_instruction_tools(version).search_instructions(query, category)
            if vector_results.get('success', False):
                results = vector_results.get('results', [])
            else:
                # Fallback to basic search if vector search fails
                import sys
                print(f"Vector search failed, using fallback: {vector_results.get('error', 'Unknown error')}", file=sys.stderr)
                results = self._basic_search_instructions(query, category, version)
        except Exception as e:
            # Fallback to basic search
            import sys
            print(f"Vector search error, using fallback: {e}", file=sys.stderr)
            results = self._basic_search_instructions(query, category, version)
        for r in results:
            r['doc_version'] = version
        return results

    def _basic_search_instructions(self, query: str, category: Optional[str] = None, version: Optional[str] = None) -> List[Dict]:
        """Fallback basic search for instructions (original implementation)"""
        version = self._resolve_version(version)
        results = []
        query_lower = query.lower()

        for name, instruction in self.instructions_by_version[version].items():
            match_score = 0

            # Name match (highest priority)
            if query_lower in instruction.name.lower():
                match_score += 10

            # Description match
            if instruction.description and query_lower in instruction.description.lower():
                match_score += 5

            # Category filter
            if category and instruction.category.lower() != category.lower():
                continue

            if match_score > 0:
                results.append({
                    'name': instruction.name,
                    'category': instruction.category,
                    'description': instruction.description,
                    'languages': instruction.languages,
                    'match_score': match_score,
                    'search_type': 'basic_fallback'
                })

        # Sort by match score
        results.sort(key=lambda x: x['match_score'], reverse=True)
        return results[:20]  # Limit to top 20 results

    async def get_instruction(self, name: str, version: Optional[str] = None) -> Optional[Dict]:
        """Get detailed information about a specific instruction using vector database.

        version: optional Logix Designer documentation version label - defaults
        to the server's default version when omitted.
        """
        version = self._resolve_version(version)
        try:
            # Ensure vector database is ready
            await self._ensure_instruction_db_ready(version)

            # Try vector database first
            vector_result = await self.get_instruction_tools(version).get_instruction(name)
            if vector_result.get('success', False):
                result = vector_result.get('instruction')
                if result is not None:
                    result['doc_version'] = version
                    result = self._backfill_syntax_from_reference(result, name, version)
                return result

            # Fallback to direct lookup
            instruction = self.instructions_by_version[version].get(name.upper())
            if not instruction:
                return None

            result = {
                'name': instruction.name,
                'category': instruction.category,
                'description': instruction.description,
                'languages': instruction.languages,
                'syntax': instruction.syntax,
                'parameters': instruction.parameters,
                'examples': instruction.examples,
                'file_path': instruction.file_path,
                'search_type': 'direct_fallback',
                'doc_version': version
            }
            return self._backfill_syntax_from_reference(result, name, version)
        except Exception as e:
            # Fallback to direct lookup
            instruction = self.instructions_by_version[version].get(name.upper())
            if not instruction:
                return None

            result = {
                'name': instruction.name,
                'category': instruction.category,
                'description': instruction.description,
                'languages': instruction.languages,
                'syntax': instruction.syntax,
                'parameters': instruction.parameters,
                'examples': instruction.examples,
                'file_path': instruction.file_path,
                'search_type': 'direct_fallback',
                'doc_version': version
            }
            return self._backfill_syntax_from_reference(result, name, version)

    async def list_categories(self, version: Optional[str] = None) -> List[str]:
        """List all available instruction categories using vector database"""
        version = self._resolve_version(version)
        try:
            # Ensure vector database is ready
            await self._ensure_instruction_db_ready(version)

            # Try vector database first
            vector_result = await self.get_instruction_tools(version).list_categories()
            if vector_result.get('success', False):
                return vector_result.get('categories', [])

            # Fallback to direct enumeration
            categories = set()
            for instruction in self.instructions_by_version[version].values():
                if instruction.category:
                    categories.add(instruction.category)
            return sorted(list(categories))
        except Exception as e:
            # Fallback to direct enumeration
            categories = set()
            for instruction in self.instructions_by_version[version].values():
                if instruction.category:
                    categories.add(instruction.category)
            return sorted(list(categories))

    async def list_instructions_by_category(self, category: str, version: Optional[str] = None) -> List[Dict]:
        """List all instructions in a specific category using vector database.

        version: optional Logix Designer documentation version label - defaults
        to the server's default version when omitted.
        """
        version = self._resolve_version(version)
        try:
            # Ensure vector database is ready
            await self._ensure_instruction_db_ready(version)

            # Try vector database first
            vector_result = await self.get_instruction_tools(version).get_instructions_by_category(category)
            if vector_result.get('success', False):
                return vector_result.get('instructions', [])

            # Fallback to direct enumeration
            results = []
            category_lower = category.lower()

            for instruction in self.instructions_by_version[version].values():
                if instruction.category.lower() == category_lower:
                    results.append({
                        'name': instruction.name,
                        'description': instruction.description,
                        'languages': instruction.languages,
                        'search_type': 'direct_fallback'
                    })

            return sorted(results, key=lambda x: x['name'])
        except Exception as e:
            # Fallback to direct enumeration
            results = []
            category_lower = category.lower()

            for instruction in self.instructions_by_version[version].values():
                if instruction.category.lower() == category_lower:
                    results.append({
                        'name': instruction.name,
                        'description': instruction.description,
                        'languages': instruction.languages,
                        'search_type': 'direct_fallback'
                    })

            return sorted(results, key=lambda x: x['name'])

    async def get_instruction_syntax(self, name: str, version: Optional[str] = None) -> Optional[Dict]:
        """Get syntax and parameter information for an instruction using vector database.

        version: optional Logix Designer documentation version label - defaults
        to the server's default version when omitted. Pass this explicitly when
        checking whether an instruction/parameter is valid on a specific
        version, since syntax can differ between major revisions.
        """
        version = self._resolve_version(version)
        try:
            # Ensure vector database is ready
            await self._ensure_instruction_db_ready(version)

            # Try vector database first
            vector_result = await self.get_instruction_tools(version).get_instruction_syntax(name)
            if vector_result.get('success', False):
                result = vector_result.get('syntax_info')
                if result is not None:
                    result['doc_version'] = version
                    result = self._backfill_syntax_from_reference(result, name, version)
                return result

            # Fallback to direct lookup
            instruction = self.instructions_by_version[version].get(name.upper())
            if not instruction:
                return None

            result = {
                'name': instruction.name,
                'syntax': instruction.syntax,
                'parameters': instruction.parameters,
                'languages': instruction.languages,
                'search_type': 'direct_fallback',
                'doc_version': version
            }
            return self._backfill_syntax_from_reference(result, name, version)
        except Exception as e:
            # Fallback to direct lookup
            instruction = self.instructions_by_version[version].get(name.upper())
            if not instruction:
                return None

            result = {
                'name': instruction.name,
                'syntax': instruction.syntax,
                'parameters': instruction.parameters,
                'languages': instruction.languages,
                'search_type': 'direct_fallback',
                'doc_version': version
            }
            return self._backfill_syntax_from_reference(result, name, version)

    async def list_documentation_versions(self) -> Dict[str, Any]:
        """List the Logix Designer documentation versions currently loaded and
        available to pass as the `version` argument to the instruction lookup
        tools (search_instructions, get_instruction, get_instruction_syntax,
        list_categories, list_instructions_by_category)."""
        return {
            'success': True,
            'available_versions': sorted(self.doc_roots.keys()),
            'default_version': self.default_version,
            'doc_roots': {v: str(p) for v, p in self.doc_roots.items()},
            'instruction_counts': {v: len(i) for v, i in self.instructions_by_version.items()}
        }
    
    # New AI-powered code generation methods
    async def generate_ladder_logic(self, specification: str) -> Dict[str, Any]:
        """Generate enhanced ladder logic from natural language specification"""
        try:
            # Use the enhanced assistant for better warehouse automation support
            result = await self.enhanced_assistant.generate_ladder_logic(specification)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate ladder logic from specification'
            }
    
    async def create_l5x_project(self, project_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Create complete L5X project file using enhanced code generation"""
        try:
            # Use the enhanced assistant for L5X project creation
            result = await self.enhanced_assistant.create_l5x_project(project_spec)
            return result
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to create L5X project'
            }
    
    async def create_l5x_routine(self, routine_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Create L5X routine export file that can be imported into existing ACD projects"""
        try:
            from code_generator.l5x_generator import L5XGenerator, Routine, LadderRung
            
            # Extract routine specification
            routine_name = routine_spec.get('name', 'SIMPLE_TEST')
            specification = routine_spec.get('specification', '')
            controller_name = routine_spec.get('controller_name', 'MTN6_MCM06')
            software_revision = routine_spec.get('software_revision', '36.02')
            save_path = routine_spec.get('save_path')
            language = routine_spec.get('language', 'RLL')

            # This generator only produces ladder (RLL). Previously any request
            # was silently forced to RLL with no indication ST wasn't actually
            # supported - reject explicitly instead so callers don't get ladder
            # logic back when they asked for Structured Text.
            if language.upper() not in ('RLL', 'LADDER'):
                return {
                    'success': False,
                    'error': f"language='{language}' is not supported - this generator only produces ladder (RLL). "
                             f"There is no Structured Text code generation path in this tool yet.",
                    'message': 'Unsupported routine language requested'
                }

            # Generate ladder logic using enhanced assistant
            ladder_result = await self.enhanced_assistant.generate_ladder_logic(specification)

            if not ladder_result.get('success', False):
                return {
                    'success': False,
                    'error': ladder_result.get('error', 'Failed to generate ladder logic'),
                    'message': 'Failed to generate ladder logic for routine'
                }

            # Parse the generated ladder logic into rungs
            ladder_logic = ladder_result.get('ladder_logic', '')
            ladder_lines = [line.strip() for line in ladder_logic.split('\n') if line.strip()]

            # Create rungs from ladder logic
            rungs = []
            rung_number = 0
            current_comment = None

            for line in ladder_lines:
                if line.startswith('//'):
                    # This is a comment for the next rung
                    current_comment = line[2:].strip()
                elif line and not line.startswith('//'):
                    # This is ladder logic
                    rung = LadderRung(
                        number=rung_number,
                        logic=line,
                        comment=current_comment
                    )
                    rungs.append(rung)
                    rung_number += 1
                    current_comment = None

            # If nothing usable came out of generation, fail honestly instead of
            # silently substituting a canned demo routine while still reporting
            # success:true - a caller had no way to tell a real request apart
            # from this fallback ever having fired.
            if not rungs:
                return {
                    'success': False,
                    'error': "Generation produced no usable ladder rungs for this specification. "
                             "The underlying generator matches a small fixed library of warehouse-automation "
                             "patterns by keyword - it does not synthesize new logic from an arbitrary "
                             "specification, so specs that don't match one of those patterns produce nothing.",
                    'message': 'Failed to generate ladder logic for routine',
                    'specification_echo': specification[:200]
                }

            # Create the routine
            routine = Routine(
                name=routine_name,
                type="RLL",
                rungs=rungs,
                description=f"Generated routine: {specification[:100]}..."
            )
            
            # Extract tags from the ladder result
            tags = []
            if 'tags' in ladder_result:
                for tag in ladder_result['tags']:
                    tags.append({
                        'name': tag['name'],
                        'data_type': tag['data_type'],
                        'description': tag.get('description', '')
                    })
            else:
                # Default tags for the simple test routine
                tags = [
                    {'name': 'Start_Test', 'data_type': 'BOOL', 'description': 'Start test button'},
                    {'name': 'Stop_Test', 'data_type': 'BOOL', 'description': 'Stop test button'},
                    {'name': 'Test_Running', 'data_type': 'BOOL', 'description': 'Test running status'},
                    {'name': 'Test_Timer', 'data_type': 'TIMER', 'description': '5 second test timer', 'preset_value': 5000},
                    {'name': 'Test_Output', 'data_type': 'BOOL', 'description': 'Test output'}
                ]
            
            # Generate the routine export L5X
            generator = L5XGenerator()
            l5x_content = generator.generate_routine_export(
                routine=routine,
                controller_name=controller_name,
                tags=tags,
                software_revision=software_revision
            )
            
            # Save to file if path provided
            file_saved = False
            if save_path:
                file_saved = generator.save_routine_export(
                    routine=routine,
                    file_path=save_path,
                    controller_name=controller_name,
                    tags=tags,
                    software_revision=software_revision
                )
            
            return {
                'success': True,
                'routine_name': routine_name,
                'controller_name': controller_name,
                'l5x_content': l5x_content,
                'ladder_logic': ladder_logic,
                'tags_created': len(tags),
                'rungs_created': len(rungs),
                'instructions_used': ladder_result.get('instructions_used', []),
                'file_saved': file_saved,
                'save_path': save_path,
                'export_type': 'routine_export'
            }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to create L5X routine export'
            }
    
    async def validate_ladder_logic(self, logic_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ladder logic using enhanced validation with Studio 5000 documentation"""
        try:
            # Use the enhanced assistant for comprehensive validation
            result = await self.enhanced_assistant.validate_ladder_logic(logic_spec)
            return result
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'message': 'Failed to validate ladder logic'
            }
    
    async def create_acd_project(self, project_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Create real Studio 5000 .ACD project file using enhanced assistant and official SDK"""
        try:
            # Use the enhanced assistant for ACD project creation
            result = await self.enhanced_assistant.create_acd_project(project_spec)
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to create .ACD project using Studio 5000 SDK'
            }
    
    # New SDK Documentation Search Methods
    async def search_sdk_documentation(self, query: str, limit: Optional[int] = 10) -> Dict[str, Any]:
        """Search Studio 5000 SDK documentation using natural language"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.search_sdk_documentation(query, limit)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'query': query,
                'message': 'Failed to search SDK documentation'
            }
    
    async def get_sdk_operation_info(self, name: str, operation_type: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed information about a specific SDK operation"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.get_sdk_operation_info(name, operation_type)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'name': name,
                'message': 'Failed to get SDK operation info'
            }
    
    async def list_sdk_categories(self) -> Dict[str, Any]:
        """List all SDK operation categories"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.list_sdk_categories()
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to list SDK categories'
            }
    
    async def get_sdk_operations_by_category(self, category: str) -> Dict[str, Any]:
        """Get all SDK operations in a specific category"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.get_sdk_operations_by_category(category)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'category': category,
                'message': 'Failed to get SDK operations by category'
            }
    
    async def get_logix_project_methods(self, method_category: Optional[str] = None) -> Dict[str, Any]:
        """Get LogixProject methods, optionally filtered by category"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.get_logix_project_methods(method_category)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'method_category': method_category,
                'message': 'Failed to get LogixProject methods'
            }
    
    async def suggest_sdk_operations(self, context: str) -> Dict[str, Any]:
        """Suggest relevant SDK operations based on context"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.suggest_sdk_operations(context)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'context': context,
                'message': 'Failed to suggest SDK operations'
            }
    
    async def get_sdk_statistics(self) -> Dict[str, Any]:
        """Get SDK documentation statistics and overview"""
        try:
            await self._ensure_sdk_db_ready()  # Ensure SDK database is initialized
            result = await self.sdk_tools.get_sdk_statistics()
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to get SDK statistics'
            }
    
    # L5X Analyzer Tools for Production-Scale L5X Files
    
    async def index_exported_l5x_files(self, l5x_directory: str, force_rebuild: bool = False) -> Dict[str, Any]:
        """Index exported L5X files directly for semantic search"""
        try:
            if not hasattr(self, 'l5x_integration') or self.l5x_integration is None:
                await self._ensure_l5x_tools_initialized()
            
            result = self.l5x_integration.index_exported_l5x_files(l5x_directory, force_rebuild)
            return result
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to index exported L5X files'
            }

    async def index_acd_project(self, acd_path: str, routines_to_index: Optional[List[str]] = None, 
                               force_rebuild: bool = False) -> Dict[str, Any]:
        """Index ACD/L5K project for semantic search"""
        return await self.l5x_integration.index_acd_project(
            acd_path, routines_to_index, force_rebuild
        )
    
    async def search_l5x_content(self, query: str, file_filter: Optional[str] = None,
                               component_type: Optional[str] = None, project_name: Optional[str] = None,
                               limit: int = 20) -> Dict[str, Any]:
        """Semantic search within indexed L5X content. Pass project_name to restrict
        results to one indexed project when more than one is indexed."""
        return await self.l5x_integration.search_l5x_content(
            query, file_filter, component_type, project_name, limit
        )
    
    async def find_insertion_point(self, new_logic_description: str, target_routine: str,
                                 target_file: Optional[str] = None) -> Dict[str, Any]:
        """Find optimal location to insert new ladder logic"""
        return await self.l5x_integration.find_insertion_point(
            new_logic_description, target_routine, target_file
        )
    
    async def smart_insert_logic(self, l5x_file_path: str, routine_name: str, 
                               logic_description: str, program_name: str = "MainProgram",
                               insertion_mode: str = "optimal") -> Dict[str, Any]:
        """Directly insert new ladder logic into L5X file at optimal location"""
        return await self.l5x_integration.smart_insert_logic(
            l5x_file_path, routine_name, logic_description, program_name, insertion_mode
        )
    
    async def extract_routine_content(self, acd_path: str, routine_name: str,
                                    program_name: str = "MainProgram", 
                                    output_format: str = "summary") -> Dict[str, Any]:
        """Extract specific routine content for analysis"""
        return await self.l5x_integration.extract_routine_content(
            acd_path, routine_name, program_name, output_format
        )
    
    async def analyze_routine_structure(self, routine_name: str, acd_path: Optional[str] = None) -> Dict[str, Any]:
        """Analyze structure and complexity of an indexed routine. Pass acd_path to
        disambiguate when the same routine name exists in more than one indexed project."""
        return await self.l5x_integration.analyze_routine_structure(routine_name, acd_path)
    
    async def find_related_components(self, component_name: str, project_filter: Optional[str] = None,
                                    relationship_type: str = "usage") -> Dict[str, Any]:
        """Find components related to a given component"""
        return await self.l5x_integration.find_related_components(
            component_name, project_filter, relationship_type
        )
    
    async def get_project_overview(self, acd_path: str) -> Dict[str, Any]:
        """Get comprehensive overview of project structure"""
        return await self.l5x_integration.get_project_overview(acd_path)
    
    # PDF Drawings Tool Handlers
    async def index_pdf_drawings(self, pdf_file_path: str, force_rebuild: bool = False, 
                               use_vision_ai: bool = False, max_pages: Optional[int] = None) -> Dict[str, Any]:
        """Index PDF technical drawings file for semantic search"""
        return await self.pdf_integration.index_pdf_drawings(
            pdf_file_path, force_rebuild, use_vision_ai, max_pages
        )
    
    async def search_drawings(self, query: str, limit: int = 10, score_threshold: float = 0.3,
                            drawing_type_filter: Optional[str] = None, 
                            equipment_filter: Optional[str] = None) -> Dict[str, Any]:
        """Search technical drawings using natural language"""
        return await self.pdf_integration.search_drawings(
            query, limit, score_threshold, drawing_type_filter, equipment_filter
        )
    
    async def find_equipment_context(self, equipment_tag: str, context_type: Optional[str] = None) -> Dict[str, Any]:
        """Find all drawings and context related to specific equipment"""
        return await self.pdf_integration.find_equipment_context(equipment_tag, context_type)
    
    async def get_drawing_details(self, drawing_number: Optional[str] = None, 
                                page_number: Optional[int] = None) -> Dict[str, Any]:
        """Get detailed information about a specific drawing"""
        return await self.pdf_integration.get_drawing_details(drawing_number, page_number)
    
    async def get_equipment_connections(self, equipment_tag: str) -> Dict[str, Any]:
        """Get electrical connections and wiring info for equipment"""
        return await self.pdf_integration.get_equipment_connections(equipment_tag)
    
    # Tag Analyzer Tool Handlers
    async def index_tag_csv(self, csv_path: str, force_rebuild: bool = False) -> Dict[str, Any]:
        """Index Studio 5000 tag CSV export for semantic search"""
        return await self.tag_integration.index_tag_csv(csv_path, force_rebuild)
    
    async def search_tags(self, query: str, category_filter: str = None, 
                         chunk_type_filter: str = None, limit: int = 20) -> Dict[str, Any]:
        """Search through indexed tags using natural language"""
        return await self.tag_integration.search_tags(query, category_filter, chunk_type_filter, limit)
    
    async def find_device(self, device_description: str, device_type: str = None) -> Dict[str, Any]:
        """Find specific devices by description or function"""
        return await self.tag_integration.find_device(device_description, device_type)
    
    async def get_module_tags(self, rack: int, slot: int) -> Dict[str, Any]:
        """Get all tags for a specific module (rack/slot)"""
        return await self.tag_integration.get_module_tags(rack, slot)
    
    async def find_i_o_point(self, address_pattern: str = None, description: str = None) -> Dict[str, Any]:
        """Find specific I/O points by address or description"""
        return await self.tag_integration.find_i_o_point(address_pattern, description)
    
    async def analyze_i_o_usage(self) -> Dict[str, Any]:
        """Analyze I/O usage and capacity across the system"""
        return await self.tag_integration.analyze_i_o_usage()
    
    async def find_related_tags(self, tag_name: str, relationship_type: str = "all") -> Dict[str, Any]:
        """Find tags related to a given tag"""
        return await self.tag_integration.find_related_tags(tag_name, relationship_type)
    
    async def get_device_overview(self, category_filter: str = None) -> Dict[str, Any]:
        """Get comprehensive overview of devices in the system"""
        return await self.tag_integration.get_device_overview(category_filter)
    
    async def get_safety_tags(self) -> Dict[str, Any]:
        """Get all safety-related tags"""
        return await self.tag_integration.get_safety_tags()
    
    async def get_motor_tags(self) -> Dict[str, Any]:
        """Get all motor control tags"""
        return await self.tag_integration.get_motor_tags()
    
    async def get_sensor_tags(self) -> Dict[str, Any]:
        """Get all sensor tags"""
        return await self.tag_integration.get_sensor_tags()
    
    async def get_cache_performance(self) -> Dict[str, Any]:
        """Get vector database cache performance statistics"""
        try:
            stats = shared_cache_manager.get_cache_statistics()
            
            # Add some additional system info
            stats['system_info'] = {
                'instruction_count': len(self.instructions),
                'instruction_counts_by_version': {v: len(i) for v, i in self.instructions_by_version.items()},
                'default_doc_version': self.default_version,
                'loaded_systems': []
            }
            
            # Check which systems are loaded
            if self._sdk_integration is not None:
                stats['system_info']['loaded_systems'].append('SDK Documentation')
            if self._instruction_integrations:
                stats['system_info']['loaded_systems'].append('Instruction Documentation')
                stats['system_info']['instruction_doc_versions_loaded'] = sorted(self._instruction_integrations.keys())
            if self._l5x_integration is not None:
                stats['system_info']['loaded_systems'].append('L5X Analyzer')
            if self._pdf_integration is not None:
                stats['system_info']['loaded_systems'].append('PDF Drawings')
            if self._tag_integration is not None:
                stats['system_info']['loaded_systems'].append('Tag Analyzer')
            
            return {
                'success': True,
                'cache_statistics': stats,
                'performance_tips': [
                    'Cache hit rates above 80% indicate good performance',
                    'Vector databases load automatically when first accessed',
                    'Shared model reduces memory usage across all vector databases',
                    'Cache files are valid for 30 days by default'
                ]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to get cache statistics: {str(e)}"
            }

# JSON-RPC 2.0 MCP Protocol Implementation
async def handle_mcp_request(server: Studio5000MCPServer, request: Dict) -> Optional[Dict]:
    """Handle an MCP request"""
    method = request.get('method')
    params = request.get('params', {})
    request_id = request.get('id')
    
    # Handle notifications (requests without ID) by returning None
    is_notification = 'id' not in request
    
    # Initialize response with JSON-RPC 2.0 format
    response = {
        "jsonrpc": "2.0"
    }
    
    # Only include ID in response if this is not a notification
    if not is_notification:
        response["id"] = request_id
    
    if method == 'initialize':
        response["result"] = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "studio5000-ai-assistant",
                "version": "2.0.0"
            }
        }
        return response
    
    elif method == 'tools/list':
        tools = []
        for name, tool in server.server.tools.items():
            # Build properties and required fields based on tool name
            properties = {}
            required = []
            
            if name == 'search_instructions':
                properties = {
                    'query': {'type': 'string', 'description': 'Search query'},
                    'category': {'type': 'string', 'description': 'Optional category filter'},
                    'version': {'type': 'string', 'description': 'Optional Logix Designer documentation version (e.g. "v35", "v37") - see list_documentation_versions. Defaults to the server default version.'}
                }
                required = ['query']
            elif name in ['get_instruction', 'get_instruction_syntax']:
                properties = {
                    'name': {'type': 'string', 'description': 'Instruction name'},
                    'version': {'type': 'string', 'description': 'Optional Logix Designer documentation version (e.g. "v35", "v37") - see list_documentation_versions. Defaults to the server default version.'}
                }
                required = ['name']
            elif name == 'list_instructions_by_category':
                properties = {
                    'category': {'type': 'string', 'description': 'Category name'},
                    'version': {'type': 'string', 'description': 'Optional Logix Designer documentation version (e.g. "v35", "v37") - see list_documentation_versions. Defaults to the server default version.'}
                }
                required = ['category']
            elif name == 'list_categories':
                properties = {
                    'version': {'type': 'string', 'description': 'Optional Logix Designer documentation version (e.g. "v35", "v37") - see list_documentation_versions. Defaults to the server default version.'}
                }
                required = []
            elif name == 'list_documentation_versions':
                properties = {}
                required = []
            elif name == 'generate_ladder_logic':
                properties = {
                    'specification': {'type': 'string', 'description': 'Natural language specification for PLC logic'}
                }
                required = ['specification']
            elif name == 'create_l5x_project':
                properties = {
                    'project_spec': {
                        'type': 'object',
                        'description': 'Project specification',
                        'properties': {
                            'name': {'type': 'string', 'description': 'Project name'},
                            'controller_type': {'type': 'string', 'description': 'Controller type (e.g., 1756-L83E)'},
                            'specification': {'type': 'string', 'description': 'Natural language specification'},
                            'save_path': {'type': 'string', 'description': 'Optional file path to save L5X file'}
                        }
                    }
                }
                required = ['project_spec']
            elif name == 'create_l5x_routine':
                properties = {
                    'routine_spec': {
                        'type': 'object',
                        'description': 'Routine specification for export',
                        'properties': {
                            'name': {'type': 'string', 'description': 'Routine name'},
                            'controller_name': {'type': 'string', 'description': 'Existing controller name (e.g., MTN6_MCM06)'},
                            'specification': {'type': 'string', 'description': 'Natural language specification for routine logic'},
                            'software_revision': {'type': 'string', 'description': 'Studio 5000 software revision (default: 36.02)'},
                            'save_path': {'type': 'string', 'description': 'File path to save routine L5X export'}
                        }
                    }
                }
                required = ['routine_spec']
            elif name == 'validate_ladder_logic':
                properties = {
                    'logic_spec': {
                        'type': 'object',
                        'description': 'Ladder logic specification to validate using fast, reliable validation',
                        'properties': {
                            'ladder_logic': {'type': 'string', 'description': 'Ladder logic code to validate'},
                            'instructions_used': {'type': 'array', 'description': 'List of instructions used (optional)'},
                            'controller_type': {'type': 'string', 'description': 'Controller type for validation (optional, default: 1756-L83E)'},
                            'language': {'type': 'string', 'description': "Routine language: 'RLL' (default) or 'ST'. For ST, only documentation-level instruction validation runs - the SDK build check is skipped because it treats ST control-flow syntax (IF/FOR/END_IF/...) as invalid ladder rungs."}
                        }
                    }
                }
                required = ['logic_spec']
            elif name == 'create_acd_project':
                properties = {
                    'project_spec': {
                        'type': 'object',
                        'description': 'ACD project specification',
                        'properties': {
                            'name': {'type': 'string', 'description': 'Project name'},
                            'controller_type': {'type': 'string', 'description': 'Controller type (e.g., 1756-L83E)'},
                            'major_revision': {'type': 'integer', 'description': 'Studio 5000 major revision (default 35)'},
                            'save_path': {'type': 'string', 'description': 'File path to save .ACD file'}
                        }
                    }
                }
                required = ['project_spec']
            elif name == 'search_sdk_documentation':
                properties = {
                    'query': {'type': 'string', 'description': 'Natural language query to search SDK documentation'},
                    'limit': {'type': 'integer', 'description': 'Maximum number of results to return (default: 10)'}
                }
                required = ['query']
            elif name == 'get_sdk_operation_info':
                properties = {
                    'name': {'type': 'string', 'description': 'Name of the SDK operation to get details for'},
                    'operation_type': {'type': 'string', 'description': 'Optional operation type filter (method, class, enum, example)'}
                }
                required = ['name']
            elif name == 'list_sdk_categories':
                properties = {}
                required = []
            elif name == 'get_sdk_operations_by_category':
                properties = {
                    'category': {'type': 'string', 'description': 'SDK operation category name'}
                }
                required = ['category']
            elif name == 'get_logix_project_methods':
                properties = {
                    'method_category': {'type': 'string', 'description': 'Optional category to filter LogixProject methods by'}
                }
                required = []
            elif name == 'suggest_sdk_operations':
                properties = {
                    'context': {'type': 'string', 'description': 'Context or description of what you want to accomplish'}
                }
                required = ['context']
            elif name == 'get_sdk_statistics':
                properties = {}
                required = []
            # L5X Analyzer Tools  
            elif name == 'index_exported_l5x_files':
                properties = {
                    'l5x_directory': {'type': 'string', 'description': 'Directory containing exported L5X files'},
                    'force_rebuild': {'type': 'boolean', 'description': 'Force rebuild even if cached (default: false)'}
                }
                required = ['l5x_directory']
            elif name == 'index_acd_project':
                properties = {
                    'acd_path': {'type': 'string', 'description': 'Path to ACD or L5K file to index'},
                    'routines_to_index': {'type': 'array', 'description': 'Optional list of specific routines to index (null for all)'},
                    'force_rebuild': {'type': 'boolean', 'description': 'Force rebuild even if cached (default: false)'}
                }
                required = ['acd_path']
            elif name == 'search_l5x_content':
                properties = {
                    'query': {'type': 'string', 'description': 'Natural language search query'},
                    'file_filter': {'type': 'string', 'description': 'Optional filter by project file name'},
                    'component_type': {'type': 'string', 'description': 'Optional filter by component type (routine, rung, udt, etc.)'},
                    'project_name': {'type': 'string', 'description': 'Optional - restrict results to one indexed project (see get_project_overview / indexed_projects). Omit to search across every indexed project.'},
                    'limit': {'type': 'integer', 'description': 'Maximum results to return (default: 20)'}
                }
                required = ['query']
            elif name == 'find_insertion_point':
                properties = {
                    'new_logic_description': {'type': 'string', 'description': 'Description of logic to insert'},
                    'target_routine': {'type': 'string', 'description': 'Target routine name'},
                    'target_file': {'type': 'string', 'description': 'Optional target file filter'}
                }
                required = ['new_logic_description', 'target_routine']
            elif name == 'smart_insert_logic':
                properties = {
                    'l5x_file_path': {'type': 'string', 'description': 'Path to L5X file to modify'},
                    'routine_name': {'type': 'string', 'description': 'Target routine name'},
                    'logic_description': {'type': 'string', 'description': 'Natural language description of logic to generate and insert'},
                    'program_name': {'type': 'string', 'description': 'Parent program name (default: MainProgram)'},
                    'insertion_mode': {'type': 'string', 'description': 'Insertion mode: optimal or end (default: optimal)'}
                }
                required = ['l5x_file_path', 'routine_name', 'logic_description']
            elif name == 'extract_routine_content':
                properties = {
                    'acd_path': {'type': 'string', 'description': 'Path to ACD/L5K file'},
                    'routine_name': {'type': 'string', 'description': 'Routine to extract'},
                    'program_name': {'type': 'string', 'description': 'Parent program name (default: MainProgram)'},
                    'output_format': {'type': 'string', 'description': 'Output format: summary, full, or rungs_only (default: summary)'}
                }
                required = ['acd_path', 'routine_name']
            elif name == 'analyze_routine_structure':
                properties = {
                    'routine_name': {'type': 'string', 'description': 'Name of routine to analyze'},
                    'acd_path': {'type': 'string', 'description': 'Optional - which indexed project to look in, if the same routine name exists in more than one indexed project. Without this, an ambiguous routine name returns an error listing the candidate projects.'}
                }
                required = ['routine_name']
            elif name == 'find_related_components':
                properties = {
                    'component_name': {'type': 'string', 'description': 'Name of component to find relationships for'},
                    'project_filter': {'type': 'string', 'description': 'Optional project file filter'},
                    'relationship_type': {'type': 'string', 'description': 'Type of relationship: usage, dependency, or similar (default: usage)'}
                }
                required = ['component_name']
            elif name == 'get_project_overview':
                properties = {
                    'acd_path': {'type': 'string', 'description': 'Path to ACD/L5K file'}
                }
                required = ['acd_path']
            
            # PDF Drawings Tool Parameters
            elif name == 'index_pdf_drawings':
                properties = {
                    'pdf_file_path': {'type': 'string', 'description': 'Path to PDF file containing technical drawings'},
                    'force_rebuild': {'type': 'boolean', 'description': 'Force re-indexing even if cached (default: false)'},
                    'use_vision_ai': {'type': 'boolean', 'description': 'Enable advanced vision AI analysis (default: false)'},
                    'max_pages': {'type': 'integer', 'description': 'Limit processing to first N pages for testing (optional)'}
                }
                required = ['pdf_file_path']
            elif name == 'search_drawings':
                properties = {
                    'query': {'type': 'string', 'description': 'Natural language search query'},
                    'limit': {'type': 'integer', 'description': 'Maximum number of results (default: 10)'},
                    'score_threshold': {'type': 'number', 'description': 'Minimum relevance score 0.0-1.0 (default: 0.3)'},
                    'drawing_type_filter': {'type': 'string', 'description': 'Filter by type: electrical, pid, layout, control_logic, etc.'},
                    'equipment_filter': {'type': 'string', 'description': 'Filter by equipment tag'}
                }
                required = ['query']
            elif name == 'find_equipment_context':
                properties = {
                    'equipment_tag': {'type': 'string', 'description': 'Equipment identifier (e.g., MCM01, PDP01, M001)'},
                    'context_type': {'type': 'string', 'description': 'Context type: electrical, process, safety, control (optional)'}
                }
                required = ['equipment_tag']
            elif name == 'get_drawing_details':
                properties = {
                    'drawing_number': {'type': 'string', 'description': 'Drawing reference number (optional)'},
                    'page_number': {'type': 'integer', 'description': 'Page number to retrieve (optional)'}
                }
                required = []  # At least one parameter required, but handled in logic
            elif name == 'get_equipment_connections':
                properties = {
                    'equipment_tag': {'type': 'string', 'description': 'Equipment identifier to find connections for'}
                }
                required = ['equipment_tag']
            
            # Tag Analyzer Tool Parameters
            elif name == 'index_tag_csv':
                properties = {
                    'csv_path': {'type': 'string', 'description': 'Path to Studio 5000 tag CSV export file'},
                    'force_rebuild': {'type': 'boolean', 'description': 'Force rebuild even if cached (default: false)'}
                }
                required = ['csv_path']
            elif name == 'search_tags':
                properties = {
                    'query': {'type': 'string', 'description': 'Natural language search query'},
                    'category_filter': {'type': 'string', 'description': 'Filter by device category (VFD, Safety, DI, DO, etc.)'},
                    'chunk_type_filter': {'type': 'string', 'description': 'Filter by chunk type (safety_tag, motor_tag, sensor_tag, etc.)'},
                    'limit': {'type': 'integer', 'description': 'Maximum results to return (default: 20)'}
                }
                required = ['query']
            elif name == 'find_device':
                properties = {
                    'device_description': {'type': 'string', 'description': 'Description of device to find'},
                    'device_type': {'type': 'string', 'description': 'Optional device type filter'}
                }
                required = ['device_description']
            elif name == 'get_module_tags':
                properties = {
                    'rack': {'type': 'integer', 'description': 'Rack number'},
                    'slot': {'type': 'integer', 'description': 'Slot number'}
                }
                required = ['rack', 'slot']
            elif name == 'find_i_o_point':
                properties = {
                    'address_pattern': {'type': 'string', 'description': 'I/O address pattern to search for (optional)'},
                    'description': {'type': 'string', 'description': 'Description to search for (optional)'}
                }
                required = []  # At least one parameter required, handled in logic
            elif name == 'analyze_i_o_usage':
                properties = {}
                required = []
            elif name == 'find_related_tags':
                properties = {
                    'tag_name': {'type': 'string', 'description': 'Tag name to find relationships for'},
                    'relationship_type': {'type': 'string', 'description': 'Type of relationship (all, functional, physical)'}
                }
                required = ['tag_name']
            elif name == 'get_device_overview':
                properties = {
                    'category_filter': {'type': 'string', 'description': 'Optional category filter'}
                }
                required = []
            elif name in ['get_safety_tags', 'get_motor_tags', 'get_sensor_tags']:
                properties = {}
                required = []
            
            tools.append({
                'name': name,
                'description': tool['description'],
                'inputSchema': {
                    'type': 'object',
                    'properties': properties,
                    'required': required
                }
            })
        
        response["result"] = {'tools': tools}
        return response
    
    elif method == 'tools/call':
        tool_name = params.get('name')
        arguments = params.get('arguments', {})
        
        if tool_name in server.server.tools:
            handler = server.server.tools[tool_name]['handler']
            try:
                result = await handler(**arguments)
                response["result"] = {
                    'content': [
                        {
                            'type': 'text',
                            'text': json.dumps(result, indent=2)
                        }
                    ]
                }
                return response
            except Exception as e:
                if is_notification:
                    return None
                response["error"] = {
                    'code': -32603,
                    'message': f"Internal error: {str(e)}"
                }
                return response
        else:
            if is_notification:
                return None
            response["error"] = {
                'code': -32601,
                'message': f"Unknown tool: {tool_name}"
            }
            return response
    
    else:
        # Don't send error responses for notifications
        if is_notification:
            return None
            
        response["error"] = {
            'code': -32601,
            'message': f"Unknown method: {method}"
        }
        return response

def _resolve_configured_doc_roots(cli_doc_roots: Optional[List[str]]) -> Union[str, Dict[str, str]]:
    """Figure out which documentation root(s) to load, in priority order:
    1. One or more --doc-root CLI args (repeatable, so multiple versions can
       be loaded side by side in a single server instance).
    2. STUDIO5000_DOC_PATHS env var - multiple paths separated by ';' or ',',
       for when the MCP client config can only set env vars (e.g. Claude
       Desktop/Code's mcpServers.env block) rather than repeat a CLI flag.
    3. STUDIO5000_DOC_PATH env var (singular, original/backward-compatible).
    4. The v35 install path, as before.

    Each path is auto-tagged with the version segment found in it
    (".../ENU/v37/Bin/Help/..." -> "v37"); paths with no discoverable version
    fall back to "default".
    """
    default_doc_path = r'C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000'

    if cli_doc_roots:
        paths = cli_doc_roots
    else:
        multi = os.environ.get('STUDIO5000_DOC_PATHS')
        if multi:
            paths = [p.strip() for p in re.split(r'[;,]', multi) if p.strip()]
        else:
            paths = [os.environ.get('STUDIO5000_DOC_PATH', default_doc_path)]

    if len(paths) == 1:
        return paths[0]

    doc_roots: Dict[str, str] = {}
    for path in paths:
        match = re.search(r'[\\/](v\d+)[\\/]', path)
        version = match.group(1) if match else "default"
        if version in doc_roots:
            # Two paths mapped to the same version label - keep both by
            # disambiguating rather than silently dropping one.
            version = f"{version}_{len(doc_roots)}"
        doc_roots[version] = path
    return doc_roots


async def main():
    """Main server entry point"""
    parser = argparse.ArgumentParser(description='Studio 5000 AI-Powered PLC Programming Assistant MCP Server')

    parser.add_argument('--doc-root',
                       action='append',
                       help='Path to a Studio 5000 documentation root directory. Repeat this flag to load '
                            'multiple Logix Designer versions (e.g. v35 and v37) side by side. Can also be '
                            'set via STUDIO5000_DOC_PATHS (multiple paths, ";" or "," separated) or the '
                            'original single-path STUDIO5000_DOC_PATH env var.')
    parser.add_argument('--test',
                       action='store_true',
                       help='Run in test mode with sample queries')

    args = parser.parse_args()
    doc_root = _resolve_configured_doc_roots(args.doc_root)

    # Initialize the server
    try:
        mcp_server = Studio5000MCPServer(doc_root)
    except Exception as e:
        import sys
        print(f"Error initializing server: {e}", file=sys.stderr)
        return 1
    
    if args.test:
        # Test mode - run some sample queries
        print("\n=== Testing Studio 5000 MCP Server ===\n")
        
        # Test search
        print("1. Searching for 'timer' instructions:")
        results = await mcp_server.search_instructions("timer")
        for result in results[:5]:
            print(f"  - {result['name']}: {result['description']}")
        
        print("\n2. Getting details for ALMD instruction:")
        almd_info = await mcp_server.get_instruction("ALMD")
        if almd_info:
            print(f"  Name: {almd_info['name']}")
            print(f"  Category: {almd_info['category']}")
            print(f"  Languages: {', '.join(almd_info['languages'])}")
            print(f"  Description: {almd_info['description'][:100]}...")
        
        print("\n3. Listing categories:")
        categories = await mcp_server.list_categories()
        for cat in categories[:10]:
            print(f"  - {cat}")
        
        print(f"\n4. Testing AI code generation:")
        test_spec = "Start the motor when the start button is pressed and stop it when the stop button is pressed"
        result = await mcp_server.generate_ladder_logic(test_spec)
        if result['success']:
            print(f"  Generated logic: {result['ladder_logic']}")
            print(f"  Tags created: {len(result['tags'])}")
            print(f"  Instructions used: {', '.join(result['instructions_used'])}")
        else:
            print(f"  Error: {result.get('error', 'Unknown error')}")
        
        print(f"\n5. Testing L5X project creation:")
        project_spec = {
            'name': 'TestMotorControl',
            'specification': test_spec
        }
        l5x_result = await mcp_server.create_l5x_project(project_spec)
        if l5x_result.get('success'):
            print(f"  L5X Project Creation Success!")
            # Print actual keys to see the structure
            print(f"  Available keys: {list(l5x_result.keys())}")
            if 'project_info' in l5x_result:
                info = l5x_result['project_info']
                print(f"  Project: {info.get('name', 'N/A')}")
                print(f"  Controller: {info.get('controller', 'N/A')}")
                print(f"  Programs: {info.get('programs', 'N/A')}")
                print(f"  Tags: {info.get('tags', 'N/A')}")
            elif 'project_name' in l5x_result:
                print(f"  Project: {l5x_result['project_name']}")
            elif 'name' in l5x_result:
                print(f"  Project: {l5x_result['name']}")
        else:
            print(f"  Error: {l5x_result.get('error', 'Unknown error')}")

        print(f"\n🎉 AI-Powered Studio 5000 Assistant initialized successfully!")
        print(f"📊 Features ready:")
        print(f"  • {len(mcp_server.instructions)} Studio 5000 instructions indexed")
        print(f"  • AI-powered natural language to ladder logic conversion")
        print(f"  • L5X project file generation")
        print(f"  • Instruction validation using official documentation")
        return 0
    
    else:
        # Real MCP server mode - JSON-RPC 2.0 via stdin/stdout
        import sys
        print("Studio 5000 MCP Server starting...", file=sys.stderr)
        print("Ready to handle MCP requests via stdin/stdout", file=sys.stderr)
        
        # JSON-RPC 2.0 stdin/stdout protocol handler
        #
        # Reads stdin via run_in_executor instead of a blocking input() call so
        # the asyncio event loop keeps running (servicing SDK async callbacks,
        # timers, etc.) while idle between requests, instead of freezing the
        # whole process on a synchronous read.
        loop = asyncio.get_running_loop()
        while True:
            try:
                raw_line = await loop.run_in_executor(None, sys.stdin.readline)

                # readline() returns '' only at true EOF (stream closed).
                # A blank/whitespace-only line is NOT EOF - it must be skipped,
                # not treated as a shutdown signal, or a stray blank line
                # (e.g. a keep-alive) would silently kill the server.
                if raw_line == '':
                    break

                line = raw_line.strip()
                if not line:
                    continue

                request = json.loads(line)
                response = await handle_mcp_request(mcp_server, request)

                # Only print response if it's not None (notifications return None)
                if response is not None:
                    print(json.dumps(response), flush=True)

            except EOFError:
                break
            except json.JSONDecodeError as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    }
                }
                print(json.dumps(error_response), flush=True)
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0", 
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
                print(json.dumps(error_response), flush=True)

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
