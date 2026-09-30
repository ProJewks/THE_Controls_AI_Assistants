#!/usr/bin/env python3
"""
L5X MCP Integration

Integrates the L5X Vector Database and SDK-powered analyzer with the MCP server,
providing tools for semantic search and intelligent modification of large L5X files.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from enum import Enum

from .l5x_vector_db import L5XVectorDatabase, L5XSearchResult
from .sdk_powered_analyzer import SDKPoweredL5XAnalyzer
from .l5x_chunk import L5XChunkType

logger = logging.getLogger(__name__)

class L5XMCPTools(Enum):
    """Enumeration of available L5X analysis MCP tools"""
    INDEX_EXPORTED_L5X_FILES = "index_exported_l5x_files"  # NEW: Direct L5X file indexing
    INDEX_ACD_PROJECT = "index_acd_project"  # OLD: Disabled ACD indexing
    SEARCH_L5X_CONTENT = "search_l5x_content"
    FIND_INSERTION_POINT = "find_insertion_point"
    SMART_INSERT_LOGIC = "smart_insert_logic"
    EXTRACT_ROUTINE_CONTENT = "extract_routine_content"
    ANALYZE_ROUTINE_STRUCTURE = "analyze_routine_structure"
    FIND_RELATED_COMPONENTS = "find_related_components"
    GET_PROJECT_OVERVIEW = "get_project_overview"
    BATCH_ROUTINE_ANALYSIS = "batch_routine_analysis"
    FIND_TAG_REFERENCES = "find_tag_references"
    SEARCH_TAG_REFERENCES = "search_tag_references"

class L5XSDKMCPIntegration:
    """
    MCP integration for L5X analysis tools combining vector database 
    with SDK-powered operations for production-scale L5X files
    """
    
    def __init__(self, vector_db: L5XVectorDatabase = None):
        self.vector_db = vector_db or L5XVectorDatabase()
        self.sdk_analyzer = SDKPoweredL5XAnalyzer()
        self.initialized = False
        
        # Import AI assistant for logic generation
        self._code_assistant = None
    
    def _get_code_assistant(self):
        """Lazy load code assistant to avoid circular imports"""
        if self._code_assistant is None:
            try:
                from ..ai_assistant.code_assistant import CodeAssistant
                self._code_assistant = CodeAssistant()
            except ImportError:
                logger.warning("Code assistant not available - logic generation disabled")
        return self._code_assistant
    
    async def initialize(self, force_rebuild: bool = False):
        """Initialize the L5X analysis system"""
        if self.initialized and not force_rebuild:
            return
        
        try:
            logger.info("Initializing L5X SDK MCP integration...")
            
            # Load any cached vector database
            if not force_rebuild:
                self.vector_db._load_from_cache()
            
            self.initialized = True
            logger.info("L5X SDK MCP integration initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize L5X MCP integration: {e}")
            raise
    
    def index_exported_l5x_files(self, l5x_directory: str, force_rebuild: bool = False) -> Dict[str, Any]:
        """
        Index EXPORTED L5X files directly (no ACD/SDK opening needed)
        
        Args:
            l5x_directory: Directory containing exported L5X files
            force_rebuild: Force rebuild even if cached
            
        Returns:
            Dictionary with indexing results
        """
        try:
            logger.info(f"Indexing exported L5X files from: {l5x_directory}")
            
            if not Path(l5x_directory).exists():
                return {
                    'success': False,
                    'error': f'L5X directory not found: {l5x_directory}'
                }
            
            # Index the exported L5X files directly
            success = self.vector_db.index_exported_l5x_files(l5x_directory, force_rebuild)
            
            if success:
                # Get indexing statistics
                project_name = Path(l5x_directory).name
                stats = self.vector_db.indexed_projects.get(project_name, {})
                
                return {
                    'success': True,
                    'project_name': project_name,
                    'files_indexed': stats.get('file_count', 0),
                    'chunks_created': stats.get('chunk_count', 0),
                    'message': f'✅ Successfully indexed exported L5X files from {project_name}'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to index L5X files - check logs for details'
                }
                
        except Exception as e:
            logger.error(f"Error indexing L5X files from {l5x_directory}: {e}")
            return {
                'success': False,
                'error': f'Exception during L5X indexing: {str(e)}'
            }

    async def index_acd_project(self, acd_path: str, routines_to_index: List[str] = None,
                              force_rebuild: bool = False) -> Dict[str, Any]:
        """
        Index ACD/L5K project for semantic search
        
        Args:
            acd_path: Path to ACD or L5K file
            routines_to_index: Specific routines to index (None for all)
            force_rebuild: Force rebuild even if cached
            
        Returns:
            Dictionary with indexing results
        """
        try:
            logger.info(f"Starting indexing of project: {acd_path}")
            
            if not Path(acd_path).exists():
                return {
                    'success': False,
                    'error': f'Project file not found: {acd_path}'
                }
            
            # Index the project
            success = await self.vector_db.index_acd_project(
                acd_path, routines_to_index, force_rebuild
            )
            
            if success:
                # Get indexing statistics
                project_name = Path(acd_path).stem
                stats = self.vector_db.indexed_projects.get(project_name, {})
                
                return {
                    'success': True,
                    'project_name': project_name,
                    'routines_indexed': stats.get('routine_count', 0),
                    'chunks_created': stats.get('chunk_count', 0),
                    'message': f'Successfully indexed {project_name}'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to index project - check logs for details'
                }
                
        except Exception as e:
            logger.error(f"Error indexing project {acd_path}: {e}")
            return {
                'success': False,
                'error': f'Exception during indexing: {str(e)}'
            }
    
    async def search_l5x_content(self, query: str, file_filter: str = None,
                               component_type: str = None, project_name: str = None,
                               limit: int = 20) -> Dict[str, Any]:
        """
        Semantic search within indexed L5X content

        Args:
            query: Search query
            file_filter: Filter by project file name
            component_type: Filter by component type (routine, rung, udt, etc.)
            project_name: Optional - restrict results to one indexed project (see
                indexed_projects). Omit to search across every indexed project.
            limit: Maximum results to return

        Returns:
            Dictionary with search results
        """
        try:
            # Convert component_type string to enum if provided
            chunk_types = None
            if component_type:
                try:
                    chunk_types = [L5XChunkType(component_type.lower())]
                except ValueError:
                    return {
                        'success': False,
                        'error': f'Invalid component type: {component_type}'
                    }

            # Perform search with lower threshold for broader results
            results = self.vector_db.search_l5x_content(
                query, limit, score_threshold=0.05, chunk_types=chunk_types,
                project_name=project_name
            )
            
            # Filter by file if requested
            if file_filter:
                results = [r for r in results if file_filter.lower() in r.file_path.lower()]
            
            # Convert results to serializable format
            search_results = []
            for result in results:
                search_results.append({
                    'chunk_id': result.chunk_id,
                    'type': result.chunk_type.value,
                    'name': result.name,
                    'description': result.description,
                    'score': result.score,
                    'content_preview': result.content[:200] + '...' if len(result.content) > 200 else result.content,
                    'location': {
                        'file_path': result.location.file_path,
                        'xpath': result.location.xpath,
                        'routine': result.location.parent_routine,
                        'program': result.location.parent_program,
                        'rung_number': result.location.rung_number
                    },
                    'insertion_hints': result.insertion_hints
                })
            
            return {
                'success': True,
                'query': query,
                'results_count': len(search_results),
                'results': search_results
            }
            
        except Exception as e:
            logger.error(f"Error searching L5X content: {e}")
            return {
                'success': False,
                'error': f'Search failed: {str(e)}'
            }
    
    async def find_insertion_point(self, new_logic_description: str, target_routine: str,
                                 target_file: str = None) -> Dict[str, Any]:
        """
        Find optimal location to insert new ladder logic
        
        Args:
            new_logic_description: Description of logic to insert
            target_routine: Target routine name
            target_file: Optional target file filter
            
        Returns:
            Dictionary with insertion recommendations
        """
        try:
            # Find optimal insertion point
            position, confidence = self.vector_db.find_optimal_insertion_point(
                new_logic_description, target_routine
            )
            
            # Get related context
            context_search = f"similar to {new_logic_description} in {target_routine}"
            context_results = self.vector_db.search_l5x_content(
                context_search, limit=3, 
                chunk_types=[L5XChunkType.LADDER_RUNG]
            )
            
            # Get routine analysis
            routine_analysis = self.vector_db.get_routine_analysis(target_routine)
            
            return {
                'success': True,
                'recommended_position': position,
                'confidence_score': confidence,
                'target_routine': target_routine,
                'reasoning': f'Insert at rung {position} based on semantic similarity analysis',
                'context_rungs': [
                    {
                        'rung_number': r.location.rung_number,
                        'description': r.description,
                        'similarity_score': r.score
                    }
                    for r in context_results if r.location.parent_routine == target_routine
                ],
                'routine_info': routine_analysis
            }
            
        except Exception as e:
            logger.error(f"Error finding insertion point: {e}")
            return {
                'success': False,
                'error': f'Failed to find insertion point: {str(e)}'
            }
    
    async def smart_insert_logic(self, l5x_file_path: str, routine_name: str, 
                               logic_description: str, program_name: str = "MainProgram",
                               insertion_mode: str = "optimal") -> Dict[str, Any]:
        """
        Generate ladder logic and directly insert it into L5X file
        
        Args:
            l5x_file_path: Path to L5X file to modify
            routine_name: Target routine name
            logic_description: Description of logic to generate
            program_name: Parent program name
            insertion_mode: 'optimal' or 'end'
            
        Returns:
            Dictionary with insertion results
        """
        try:
            logger.info(f"Directly inserting logic into L5X file: {l5x_file_path}")
            
            # Verify L5X file exists
            from pathlib import Path
            import xml.etree.ElementTree as ET
            import shutil
            import time
            
            l5x_path = Path(l5x_file_path)
            if not l5x_path.exists():
                return {
                    'success': False,
                    'error': f'L5X file not found: {l5x_file_path}'
                }
            
            # Create backup of original file
            backup_path = l5x_path.with_suffix(f'.backup_{int(time.time())}.L5X')
            shutil.copy2(l5x_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            
            # Generate ladder logic using AI assistant
            code_assistant = self._get_code_assistant()
            if not code_assistant:
                return {
                    'success': False,
                    'error': 'Code generation not available - AI assistant not loaded'
                }
            
            generated_logic = code_assistant.generate_ladder_logic(logic_description)
            if not generated_logic or 'ladder_logic' not in generated_logic:
                return {
                    'success': False,
                    'error': 'Failed to generate ladder logic - check logic description'
                }
            
            logic_text = generated_logic['ladder_logic']
            logger.info(f"Generated logic: {logic_text}")
            
            # Parse L5X file and find target routine
            tree = ET.parse(l5x_path)
            root = tree.getroot()
            
            # Find the target routine
            routine_xpath = f".//Program[@Name='{program_name}']//Routine[@Name='{routine_name}']"
            routine_elem = root.find(routine_xpath)
            
            if routine_elem is None:
                return {
                    'success': False,
                    'error': f'Routine {routine_name} not found in program {program_name}'
                }
            
            # Find RLLContent section
            rll_content = routine_elem.find('RLLContent')
            if rll_content is None:
                return {
                    'success': False,
                    'error': f'Routine {routine_name} is not a ladder logic routine (no RLLContent)'
                }
            
            # Find insertion point
            existing_rungs = rll_content.findall('Rung')
            if insertion_mode == "optimal":
                # Try to find optimal insertion point using vector database
                try:
                    insertion_point, confidence = self.vector_db.find_optimal_insertion_point(
                        logic_description, routine_name
                    )
                except Exception as e:
                    logger.warning(f"Could not find optimal insertion point: {e}")
                    insertion_point = len(existing_rungs)  # Insert at end
                    confidence = 0.0
            else:
                # Insert at end
                insertion_point = len(existing_rungs)
                confidence = 1.0
            
            # Split generated logic into individual rungs
            logic_lines = [line.strip() for line in logic_text.split('\n') if line.strip()]
            rung_texts = []
            current_rung = ""
            
            for line in logic_lines:
                if line.startswith('//'):
                    continue  # Skip comments for now
                current_rung += line
                if line.endswith(';'):
                    rung_texts.append(current_rung.strip())
                    current_rung = ""
                else:
                    current_rung += " "
            
            # Add any remaining logic as a rung
            if current_rung.strip():
                rung_texts.append(current_rung.strip())
            
            # Splice the new rungs into the raw file text. Re-saving through ElementTree would
            # drop every CDATA wrapper in the file and make Logix reject it on import.
            from .l5x_editor import splice_rungs, L5XEditError
            raw_text = l5x_path.read_bytes().decode('utf-8')
            try:
                new_text, edit_info = splice_rungs(
                    raw_text, routine_name,
                    [{'text': t, 'comment': f"Generated: {logic_description}"} for t in rung_texts],
                    position=insertion_point, program=program_name)
            except L5XEditError as edit_error:
                return {'success': False, 'error': f'Could not insert logic: {edit_error}',
                        'backup_created': str(backup_path)}
            l5x_path.write_bytes(new_text.encode('utf-8'))
            inserted_rungs = edit_info['added']
            
            return {
                'success': True,
                'file_modified': str(l5x_path),
                'backup_created': str(backup_path),
                'insertion_details': {
                    'position': insertion_point,
                    'rungs_inserted': inserted_rungs,
                    'insertion_mode': insertion_mode,
                    'confidence_score': confidence
                },
                'generated_content': {
                    'logic_text': logic_text,
                    'rung_count': len(rung_texts),
                    'tags_referenced': generated_logic.get('tags', [])
                },
                'target_info': {
                    'routine_name': routine_name,
                    'program_name': program_name,
                    'description': logic_description
                },
                'message': f'✅ Successfully inserted {inserted_rungs} rungs at position {insertion_point} in {routine_name}'
            }
                
        except Exception as e:
            logger.error(f"Error during smart logic generation: {e}")
            return {
                'success': False,
                'error': f'Logic generation failed: {str(e)}'
            }
    
    @staticmethod
    def _output_paths():
        """output_paths helper (sdk_interface is a sibling of l5x_analyzer under src/)."""
        try:
            from sdk_interface import output_paths
        except ImportError:
            from ..sdk_interface import output_paths
        return output_paths

    async def _convert(self, source: Path, dest: Path, detailed_l5x: bool = False) -> Dict[str, Any]:
        """Protected-target check, then SDK conversion (dest is always a brand-new path)."""
        op = self._output_paths()
        reason = op.is_protected_target(dest)
        if reason:
            return {'success': False, 'error': f'Refusing to write output: {reason}'}
        analyzer = self.vector_db.sdk_analyzer or SDKPoweredL5XAnalyzer()
        result = await analyzer.convert_project(str(source), str(dest), detailed_l5x=detailed_l5x)
        if not result.get('success'):
            # Don't leave empty output folders behind after a failed run (rmdir only removes empty dirs).
            for folder in (dest.parent, dest.parent.parent):
                try:
                    folder.rmdir()
                except OSError:
                    break
        return result

    async def export_acd_to_l5x(self, acd_path: str, output_dir: Optional[str] = None,
                                detailed_l5x: bool = False) -> Dict[str, Any]:
        """
        Export an ACD to a new L5X file via the Logix Designer SDK.

        Output: <acd_dir>/L5X_Exports/<ProjectName>/<ProjectName>_<timestamp>.L5X (or output_dir).
        Never overwrites - every export gets its own timestamped file. The ACD is only opened,
        never modified (safe on a live project unless Studio 5000 holds the file lock).
        """
        try:
            src = Path(acd_path)
            if src.suffix.lower() != '.acd':
                return {'success': False, 'error': f'export_acd_to_l5x expects an .ACD file, got: {src.name}'}
            if not src.exists():
                return {'success': False, 'error': f'Project file not found: {acd_path}'}
            dest = self._output_paths().versioned_l5x_path(src, output_dir)
            result = await self._convert(src, dest, detailed_l5x)
            if result.get('success'):
                result['message'] = f'Exported {src.name} -> {dest}'
            return result
        except Exception as e:
            logger.error(f"export_acd_to_l5x failed: {e}")
            return {'success': False, 'error': f'Export failed: {e}'}

    async def import_l5x_to_acd(self, l5x_path: str, output_dir: Optional[str] = None,
                                project_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Build a new ACD from a whole-controller L5X via the SDK.

        Output: <l5x_dir>/ACD_Revisions/<Name>/<Name>_rNNN.ACD - a fresh revision every time;
        existing ACDs (including the live THD_LG_CP2.ACD) are never written to.
        """
        try:
            src = Path(l5x_path)
            if src.suffix.lower() != '.l5x':
                return {'success': False, 'error': f'import_l5x_to_acd expects an .L5X file, got: {src.name}'}
            if not src.exists():
                return {'success': False, 'error': f'L5X file not found: {l5x_path}'}
            op = self._output_paths()
            renamed_from = None
            if project_name:
                problems = op.project_name_problems(project_name)
                if problems:
                    # Studio 5000 rejects these names - say so instead of quietly producing a different one.
                    return {'success': False,
                            'error': f"project_name {project_name!r} is not a valid Studio 5000 project name: "
                                     + "; ".join(problems),
                            'suggested_name': op.sanitize_project_name(project_name),
                            'hint': 'Names must start with a letter or underscore, use only letters, digits and '
                                    'underscores, and have no consecutive underscores.'}
            dest = op.versioned_acd_path(src, output_dir, project_name)
            if not project_name and op.derive_base_name(src.stem)[1]:
                renamed_from = src.stem  # name derived from the L5X file name had to be cleaned up
            result = await self._convert(src, dest)
            if result.get('success'):
                result['message'] = f'Created new revision {dest.name}. Open it in Studio 5000 to review before use.'
                if renamed_from:
                    result['renamed_from'] = renamed_from
            return result
        except Exception as e:
            logger.error(f"import_l5x_to_acd failed: {e}")
            return {'success': False, 'error': f'Import failed: {e}'}

    async def compare_l5x_projects(self, path_a: str, path_b: str, write_report: bool = True,
                                   include_details: bool = False) -> Dict[str, Any]:
        """
        Compare two projects (.L5X or .ACD; ACDs are exported to L5X_Exports/ first).

        A is the baseline, B the other side. Live values (tag data, module I/O) are ignored.
        The markdown/JSON reports go to <A dir>/Compare_Reports/<A stem>/ with a timestamp.
        """
        import json
        from .l5x_compare import compare_l5x_files, render_markdown

        try:
            resolved = []
            exported = []
            for label, raw in (('A', path_a), ('B', path_b)):
                p = Path(raw)
                if not p.exists():
                    return {'success': False, 'error': f'File not found ({label}): {raw}'}
                if p.suffix.lower() == '.acd':
                    exp = await self.export_acd_to_l5x(str(p))
                    if not exp.get('success'):
                        return {'success': False, 'error': f"Could not export {label} ({p.name}) to L5X: {exp.get('error')}",
                                'hint': exp.get('hint')}
                    exported.append(exp['output'])
                    p = Path(exp['output'])
                elif p.suffix.lower() != '.l5x':
                    return {'success': False, 'error': f'Unsupported file type for {label}: {p.name} (use .L5X or .ACD)'}
                resolved.append(p)

            result = compare_l5x_files(str(resolved[0]), str(resolved[1]))
            markdown = render_markdown(result, Path(path_a).name, Path(path_b).name)
            response: Dict[str, Any] = {
                'success': True,
                'summary': result['summary'],
                'exported_l5x': exported,
                'markdown': markdown,
            }
            if include_details:
                response['details'] = result
            if write_report:
                op = self._output_paths()
                md_path = op.versioned_compare_path(resolved[0], resolved[1], 'md')
                json_path = md_path.with_suffix('.json')
                md_path.write_text(markdown, encoding='utf-8')
                json_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
                response['report_markdown'] = str(md_path)
                response['report_json'] = str(json_path)
            return response
        except Exception as e:
            logger.error(f"compare_l5x_projects failed: {e}")
            return {'success': False, 'error': f'Comparison failed: {e}'}

    # ------------------------------------------------------------------ staged ACD workflow
    # open_acd_workspace -> edit_l5x_rungs / add_l5x_tags -> validate_l5x_changes -> commit_l5x_to_acd
    # No ACD is created until commit_l5x_to_acd is called with confirm=True.

    @staticmethod
    def _read_l5x(path) -> str:
        return Path(path).read_bytes().decode('utf-8')  # keep BOM/CRLF/CDATA exactly as they are

    @staticmethod
    def _write_l5x(path, text: str) -> None:
        Path(path).write_bytes(text.encode('utf-8'))

    def _work_and_baseline(self, l5x_path: str, baseline_l5x_path: Optional[str] = None):
        """Validate that l5x_path is a working copy and find its baseline. Returns (work, baseline, error)."""
        op = self._output_paths()
        work = Path(l5x_path)
        if not work.exists():
            return None, None, {'success': False, 'error': f'File not found: {l5x_path}'}
        if work.suffix.lower() != '.l5x':
            return None, None, {'success': False, 'error': f'Expected an .L5X working copy, got: {work.name}'}
        if not op.is_work_file(work):
            return None, None, {'success': False,
                                'error': f'{work.name} is not a working copy. Edit tools only change files ending in '
                                         f'"_work.L5X" so the baseline export stays untouched.',
                                'hint': 'Call open_acd_workspace first - it creates the baseline and the working copy.'}
        baseline = Path(baseline_l5x_path) if baseline_l5x_path else op.baseline_for_work(work)
        if not baseline.exists():
            return None, None, {'success': False, 'error': f'Baseline L5X not found: {baseline}',
                                'hint': 'Pass baseline_l5x_path, or re-open the workspace.'}
        return work, baseline, None

    def _edit_result(self, work: Path, baseline: Path, info: Dict[str, Any]) -> Dict[str, Any]:
        """Common tail of the edit tools: quick validation so problems surface immediately."""
        from .l5x_validate import validate_changes
        try:
            report = validate_changes(str(baseline), str(work))
        except Exception as e:  # never let a reporting problem hide a successful edit
            report = {'ok': None, 'summary': f'validation could not run: {e}'}
        result = {'success': True, 'working_copy': str(work), 'edit': info,
                  'validation': {k: report.get(k) for k in ('ok', 'summary', 'introduced_errors', 'warnings')},
                  'note': 'Working copy changed. No ACD has been created.'}
        if report.get('introduced_errors'):
            result['warning'] = 'This edit introduced validation errors - fix them before committing.'
        return result

    async def open_acd_workspace(self, source_path: str, output_dir: Optional[str] = None,
                                 detailed_l5x: bool = False) -> Dict[str, Any]:
        """
        Stage 1. Turn an ACD (or an L5X) into an editable workspace - no ACD is created.

        Creates, in <source folder>/L5X_Exports/<name>/:
          <name>_<ts>.L5X        baseline export - never edited, used to validate and diff
          <name>_<ts>_work.L5X   working copy    - the only file the edit tools will change
        """
        import shutil
        try:
            op = self._output_paths()
            src = Path(source_path)
            if not src.exists():
                return {'success': False, 'error': f'File not found: {source_path}'}
            ext = src.suffix.lower()
            if ext == '.acd':
                exp = await self.export_acd_to_l5x(str(src), output_dir, detailed_l5x)
                if not exp.get('success'):
                    return exp
                baseline = Path(exp['output'])
                origin = 'exported from the ACD'
            elif ext == '.l5x':
                if op.is_work_file(src):
                    return {'success': False, 'error': f'{src.name} is already a working copy.'}
                in_workspace = (src.parent.parent.name == op.KIND_FOLDERS['l5x'] and op._TS_RE.search(src.stem))
                if in_workspace and not output_dir:
                    baseline, origin = src, 'existing export used as the baseline'
                else:
                    baseline = op.versioned_l5x_path(src, output_dir)
                    shutil.copyfile(src, baseline)
                    origin = 'copied from the L5X'
            else:
                return {'success': False, 'error': f'Expected an .ACD or .L5X file, got: {src.name}'}

            work = op.work_path_for_baseline(baseline)
            if work.exists():
                return {'success': False, 'error': f'Working copy already exists: {work}'}
            shutil.copyfile(baseline, work)
            return {
                'success': True,
                'source': str(src),
                'baseline_l5x': str(baseline),
                'working_l5x': str(work),
                'origin': origin,
                'overview': self._workspace_overview(baseline),
                'next_steps': ['Read/analyse the baseline or working L5X as needed.',
                               'Edit only the working copy: edit_l5x_rungs / add_l5x_tags.',
                               'validate_l5x_changes to review the diff and checks (no ACD is created).',
                               'commit_l5x_to_acd (dry run first, then confirm=true) creates the new ACD revision.'],
            }
        except Exception as e:
            logger.error(f"open_acd_workspace failed: {e}")
            return {'success': False, 'error': f'Could not open workspace: {e}'}

    @staticmethod
    def _workspace_overview(l5x: Path) -> Dict[str, Any]:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(Path(l5x).read_bytes().lstrip(b'\xef\xbb\xbf'))
        c = root.find('Controller')
        programs = {}
        for prog in c.findall('Programs/Program'):
            programs[prog.get('Name')] = [
                {'routine': r.get('Name'), 'type': r.get('Type', 'RLL'),
                 'rungs': len(r.findall('RLLContent/Rung')) if r.get('Type', 'RLL') == 'RLL' else None}
                for r in prog.findall('Routines/Routine')]
        return {
            'controller': c.get('Name'), 'processor': c.get('ProcessorType'),
            'revision': f"{c.get('MajorRev')}.{c.get('MinorRev')}",
            'controller_tags': len(c.findall('Tags/Tag')),
            'modules': len(c.findall('Modules/Module')),
            'data_types': len(c.findall('DataTypes/DataType')),
            'add_on_instructions': [a.get('Name') for a in c.findall('AddOnInstructionDefinitions/AddOnInstructionDefinition')],
            'programs': programs,
        }

    async def edit_l5x_rungs(self, l5x_path: str, routine_name: str, operation: str,
                             program_name: str = "MainProgram", position: Optional[int] = None,
                             rungs: Optional[List[Dict[str, Any]]] = None, count: Optional[int] = None,
                             aoi_name: Optional[str] = None,
                             baseline_l5x_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Stage 2. Insert, replace or delete ladder rungs in a WORKING COPY (byte-preserving).

        operation: 'insert' (rungs at position, default end), 'replace' (count existing rungs at
        position, default len(rungs), are replaced by rungs) or 'delete' (count rungs, default 1, at position).
        rungs: [{'text': 'XIC(a)OTE(b);', 'comment': 'optional'}]. Rung numbers after the edit are renumbered.
        Only the working copy changes - never the baseline, never an ACD.
        """
        from .l5x_editor import splice_rungs, list_rungs, L5XEditError
        import xml.etree.ElementTree as ET
        try:
            work, baseline, err = self._work_and_baseline(l5x_path, baseline_l5x_path)
            if err:
                return err
            op = (operation or '').lower()
            rungs = rungs or []
            if op not in ('insert', 'replace', 'delete'):
                return {'success': False, 'error': "operation must be 'insert', 'replace' or 'delete'"}
            if op in ('insert', 'replace') and not rungs:
                return {'success': False, 'error': f"'{op}' needs at least one rung in 'rungs'"}
            if op in ('replace', 'delete') and position is None:
                return {'success': False, 'error': f"'{op}' needs a 'position'"}
            remove = 0 if op == 'insert' else (count if count is not None else (len(rungs) if op == 'replace' else 1))
            if op == 'delete':
                rungs = []
            text = self._read_l5x(work)
            try:
                new_text, info = splice_rungs(text, routine_name, rungs, position=position, remove_count=remove,
                                              program=program_name, aoi=aoi_name)
                ET.fromstring(new_text.encode('utf-8').lstrip(b'\xef\xbb\xbf'))  # refuse to write broken XML
            except L5XEditError as e:
                return {'success': False, 'error': str(e)}
            except ET.ParseError as e:
                return {'success': False, 'error': f'Edit would produce invalid XML ({e}); nothing was written.'}
            self._write_l5x(work, new_text)
            after = list_rungs(new_text, routine_name, program_name, aoi_name)
            lo = max(0, info['position'] - 1)
            info['rungs_around_edit'] = [{'number': r['number'], 'text': r['text'][:160], 'comment': r['comment']}
                                         for r in after[lo: info['position'] + info['added'] + 1]]
            return self._edit_result(work, baseline, info)
        except Exception as e:
            logger.error(f"edit_l5x_rungs failed: {e}")
            return {'success': False, 'error': f'Edit failed: {e}'}

    async def add_l5x_tags(self, l5x_path: str, tags: List[Dict[str, Any]], program_name: Optional[str] = None,
                           baseline_l5x_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Stage 2. Add simple tags to a WORKING COPY (controller scope, or program scope with program_name).

        tags: [{'name': 'Pulse_Count', 'data_type': 'DINT', 'initial_value': 0, 'description': '...', 'preset': 0}]
        Supported types: BOOL, SINT, INT, DINT, REAL, TIMER, COUNTER (preset for TIMER/COUNTER).
        UDT, AOI, string and array tags must be created in Studio 5000.
        """
        from .l5x_editor import add_tags, L5XEditError
        import xml.etree.ElementTree as ET
        try:
            work, baseline, err = self._work_and_baseline(l5x_path, baseline_l5x_path)
            if err:
                return err
            text = self._read_l5x(work)
            try:
                new_text, info = add_tags(text, tags, program=program_name)
                ET.fromstring(new_text.encode('utf-8').lstrip(b'\xef\xbb\xbf'))
            except L5XEditError as e:
                return {'success': False, 'error': str(e)}
            except ET.ParseError as e:
                return {'success': False, 'error': f'Edit would produce invalid XML ({e}); nothing was written.'}
            self._write_l5x(work, new_text)
            return self._edit_result(work, baseline, info)
        except Exception as e:
            logger.error(f"add_l5x_tags failed: {e}")
            return {'success': False, 'error': f'Edit failed: {e}'}

    async def validate_l5x_changes(self, l5x_path: str, baseline_l5x_path: Optional[str] = None,
                                   include_diff: bool = True) -> Dict[str, Any]:
        """
        Stage 3. Check a working copy against its baseline and show what changed. Creates no ACD.

        Reports errors the edits introduced (these block a commit), problems already in the baseline,
        warnings (e.g. tags that aren't defined), and a routine/tag/module diff.
        """
        from .l5x_validate import validate_changes
        from .l5x_compare import compare_l5x_files, render_markdown
        try:
            work, baseline, err = self._work_and_baseline(l5x_path, baseline_l5x_path)
            if err:
                return err
            report = validate_changes(str(baseline), str(work))
            result = {'success': True, 'ready_to_commit': bool(report['ok']), 'validation': report}
            if include_diff:
                diff = compare_l5x_files(str(baseline), str(work))
                result['diff_summary'] = diff['summary']
                result['diff_markdown'] = render_markdown(diff, 'baseline', 'working copy')
            result['note'] = 'Nothing was written and no ACD was created.'
            return result
        except Exception as e:
            logger.error(f"validate_l5x_changes failed: {e}")
            return {'success': False, 'error': f'Validation failed: {e}'}

    async def commit_l5x_to_acd(self, l5x_path: str, baseline_l5x_path: Optional[str] = None,
                                confirm: bool = False, project_name: Optional[str] = None,
                                verify: bool = True) -> Dict[str, Any]:
        """
        Stage 4. Create the new ACD revision from a validated working copy.

        confirm=False (default) is a dry run: validates, shows the diff and the ACD that WOULD be
        created, and writes nothing. confirm=True creates <name>_rNNN.ACD under ACD_Revisions/ and,
        with verify=True, re-exports it and checks it matches the working copy.
        """
        import shutil
        import tempfile
        from .l5x_validate import validate_changes
        from .l5x_compare import compare_l5x_files
        try:
            work, baseline, err = self._work_and_baseline(l5x_path, baseline_l5x_path)
            if err:
                return err
            op = self._output_paths()
            if project_name:
                problems = op.project_name_problems(project_name)
                if problems:
                    return {'success': False, 'error': f'project_name {project_name!r} is not a valid Studio 5000 '
                            'project name: ' + '; '.join(problems), 'suggested_name': op.sanitize_project_name(project_name)}

            report = validate_changes(str(baseline), str(work))
            if not report['ok']:
                return {'success': False, 'blocked': True,
                        'error': 'Validation found errors introduced by the edits; no ACD was created.',
                        'validation': report}
            diff = compare_l5x_files(str(baseline), str(work))
            dest = op.versioned_acd_path(work, None, project_name, create=False)
            if not confirm:
                return {'success': True, 'dry_run': True, 'would_create': str(dest),
                        'validation': {k: report[k] for k in ('summary', 'warnings', 'preexisting_errors')},
                        'diff_summary': diff['summary'],
                        'message': 'Dry run - no ACD was created. Review the diff, then call again with confirm=true.'}

            result = await self.import_l5x_to_acd(str(work), project_name=project_name)
            if not result.get('success'):
                result['validation'] = {k: report[k] for k in ('summary', 'warnings')}
                return result
            result['validation'] = {k: report[k] for k in ('summary', 'warnings', 'preexisting_errors')}
            result['diff_summary'] = diff['summary']
            if verify:
                result['verification'] = await self._verify_acd_matches(result['output'], work)
            return result
        except Exception as e:
            logger.error(f"commit_l5x_to_acd failed: {e}")
            return {'success': False, 'error': f'Commit failed: {e}'}

    async def _verify_acd_matches(self, acd_path: str, l5x_path) -> Dict[str, Any]:
        """Re-export the new ACD and compare it with the L5X it was built from."""
        import shutil
        import tempfile
        from .l5x_compare import compare_l5x_files
        tmp = Path(tempfile.mkdtemp(prefix='acd_verify_'))
        try:
            analyzer = self.vector_db.sdk_analyzer or SDKPoweredL5XAnalyzer()
            exp = await analyzer.convert_project(acd_path, str(tmp / 'verify.L5X'))
            if not exp.get('success'):
                return {'verified': False, 'error': f"could not re-export the new ACD to verify it: {exp.get('error')}"}
            d = compare_l5x_files(str(l5x_path), str(tmp / 'verify.L5X'))
            issues = []
            for key in ('datatypes', 'aois', 'tasks', 'controller_tags'):
                c = d[key]
                if c['only_in_a'] or c['only_in_b'] or c['changed']:
                    issues.append({'section': key, 'only_in_working_copy': c['only_in_a'],
                                   'only_in_new_acd': c['only_in_b'], 'changed': [x['name'] for x in c['changed']]})
            for pname, p in d['programs']['programs'].items():
                if p['routines_changed'] or p['routines_only_in_a'] or p['routines_only_in_b']:
                    issues.append({'section': f'program {pname}', 'routines_changed': list(p['routines_changed']),
                                   'only_in_working_copy': p['routines_only_in_a'], 'only_in_new_acd': p['routines_only_in_b']})
            module_notes = [c['name'] for c in d['modules']['changed']
                            if all('<public>' in line for line in c['diff'])]
            module_issues = [c['name'] for c in d['modules']['changed'] if c['name'] not in module_notes]
            if module_issues or d['modules']['only_in_a'] or d['modules']['only_in_b']:
                issues.append({'section': 'modules', 'changed': module_issues,
                               'only_in_working_copy': d['modules']['only_in_a'], 'only_in_new_acd': d['modules']['only_in_b']})
            return {'verified': not issues, 'differences': issues,
                    'benign_notes': ([f"{len(module_notes)} module(s) gained EDS-derived vendor metadata on import (harmless)"]
                                     if module_notes else []),
                    'message': ('The new ACD matches the working copy.' if not issues
                                else 'The new ACD differs from the working copy - review before using it.')}
        except Exception as e:
            return {'verified': False, 'error': f'verification failed: {e}'}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def extract_routine_content(self, acd_path: str, routine_name: str,
                                    program_name: str = "MainProgram", 
                                    output_format: str = "summary") -> Dict[str, Any]:
        """
        Extract specific routine content for analysis using vector database
        
        Args:
            acd_path: Path to ACD/L5K file (not opened - its file stem selects which indexed
                project to read from, so identically named routines in two projects don't mix)
            routine_name: Routine to extract
            program_name: Parent program name  
            output_format: 'summary', 'full', or 'rungs_only'
            
        Returns:
            Dictionary with extracted content
        """
        try:
            logger.info(f"Extracting routine content for {routine_name} using vector database")
            
            # Exact lookup straight from the chunk store - NOT a semantic search. A search
            # returns only the top-N ranked chunks across the whole project, which silently
            # dropped rungs of long routines; this returns every rung that was indexed.
            project_name = Path(acd_path).stem if acd_path else None
            scope = project_name if project_name in self.vector_db.indexed_projects else None

            routine_chunks = []
            rung_chunks = []

            for chunk in self.vector_db.chunks_data:
                if chunk.chunk_type not in (L5XChunkType.ROUTINE, L5XChunkType.LADDER_RUNG):
                    continue
                if scope is not None and getattr(chunk, 'project_name', None) != scope:
                    continue
                loc = chunk.location
                if loc is None or (loc.parent_program and loc.parent_program != program_name):
                    continue
                if chunk.chunk_type == L5XChunkType.ROUTINE and chunk.name == routine_name:
                    routine_chunks.append(chunk)
                elif chunk.chunk_type == L5XChunkType.LADDER_RUNG and loc.parent_routine == routine_name:
                    rung_chunks.append(chunk)
            
            if not routine_chunks and not rung_chunks:
                return {
                    'success': False,
                    'error': f'Routine {routine_name} not found in program {program_name} of '
                             f'{scope or "any indexed project"}. Make sure the project is indexed first.',
                    'indexed_projects': sorted(self.vector_db.indexed_projects.keys())
                }

            if scope is None:
                # acd_path didn't match an indexed project, so results came from everywhere -
                # refuse to silently blend several projects' copies of the same routine.
                found_in = sorted({getattr(r, 'project_name', None) for r in routine_chunks + rung_chunks} - {None})
                if len(found_in) > 1:
                    return {
                        'success': False,
                        'error': f'Routine {routine_name} exists in several indexed projects and '
                                 f'{acd_path!r} does not match any of them.',
                        'candidates': found_in,
                        'hint': 'Pass the acd_path of one of the candidate projects.'
                    }
            
            # Sort rungs by rung number
            rung_chunks.sort(key=lambda x: x.location.rung_number or 0)
            
            # Format output based on requested format
            if output_format == "summary":
                return {
                    'success': True,
                    'routine_name': routine_name,
                    'program_name': program_name,
                    'rung_count': len(rung_chunks),
                    'description': routine_chunks[0].description if routine_chunks else 'No description available',
                    'dependencies': sorted(set().union(*[set(c.dependencies or []) for c in routine_chunks + rung_chunks])),
                    'complexity_info': {
                        'total_rungs': len(rung_chunks),
                        'has_routine_metadata': len(routine_chunks) > 0
                    },
                    'file_location': routine_chunks[0].location.file_path if routine_chunks else (rung_chunks[0].location.file_path if rung_chunks else 'Unknown')
                }
            
            elif output_format == "rungs_only":
                rungs = []
                
                for result in rung_chunks:
                    rungs.append({
                        'rung_number': result.location.rung_number,
                        'logic': result.content,
                        'comment': result.description,
                        'file_path': result.location.file_path
                    })
                
                return {
                    'success': True,
                    'routine_name': routine_name,
                    'rungs': rungs,
                    'total_rungs': len(rungs)
                }
            
            else:  # full
                all_chunks = routine_chunks + rung_chunks
                chunks_data = []
                
                for result in all_chunks:
                    chunks_data.append({
                        'id': result.id,
                        'type': result.chunk_type.value,
                        'name': result.name,
                        'content': result.content,
                        'description': result.description,
                        'location': {
                            'file_path': result.location.file_path,
                            'xpath': result.location.xpath,
                            'routine': result.location.parent_routine,
                            'program': result.location.parent_program,
                            'rung_number': result.location.rung_number
                        }
                    })
                
                return {
                    'success': True,
                    'routine_name': routine_name,
                    'chunks': chunks_data,
                    'total_chunks': len(chunks_data)
                }
                
        except Exception as e:
            logger.error(f"Error extracting routine content: {e}")
            return {
                'success': False,
                'error': f'Extraction failed: {str(e)}'
            }
    
    async def analyze_routine_structure(self, routine_name: str, acd_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze structure and complexity of an indexed routine

        Args:
            routine_name: Name of routine to analyze
            acd_path: Optional - which indexed project to look in, if the same
                routine name exists in more than one indexed project. Without
                this, an ambiguous routine name returns an error listing the
                candidate projects rather than silently blending/picking one.

        Returns:
            Dictionary with analysis results
        """
        try:
            project_name = Path(acd_path).stem if acd_path else None
            analysis = self.vector_db.get_routine_analysis(routine_name, project_name=project_name)
            
            if 'error' in analysis:
                return {
                    'success': False,
                    'error': analysis['error']
                }
            
            return {
                'success': True,
                'analysis': analysis
            }
            
        except Exception as e:
            logger.error(f"Error analyzing routine structure: {e}")
            return {
                'success': False,
                'error': f'Analysis failed: {str(e)}'
            }
    
    async def find_related_components(self, component_name: str, project_filter: str = None,
                                    relationship_type: str = "usage") -> Dict[str, Any]:
        """
        Find components related to a given component
        
        Args:
            component_name: Name of component to find relationships for
            project_filter: Optional project file filter
            relationship_type: Type of relationship ('usage', 'dependency', 'similar')
            
        Returns:
            Dictionary with related components
        """
        try:
            # Search for the component first
            component_results = self.vector_db.search_l5x_content(
                component_name, limit=5
            )
            
            if not component_results:
                return {
                    'success': False,
                    'error': f'Component {component_name} not found in indexed content'
                }
            
            # Get the best match
            primary_component = component_results[0]
            
            # Find related components
            related_results = self.vector_db.find_related_components(
                primary_component.chunk_id
            )
            
            # Filter by project if requested
            if project_filter:
                related_results = [r for r in related_results 
                                 if project_filter.lower() in r.file_path.lower()]
            
            # Format results
            related_components = []
            for result in related_results:
                related_components.append({
                    'name': result.name,
                    'type': result.chunk_type.value,
                    'description': result.description,
                    'score': result.score,
                    'location': {
                        'file_path': result.location.file_path,
                        'routine': result.location.parent_routine,
                        'program': result.location.parent_program
                    }
                })
            
            return {
                'success': True,
                'primary_component': {
                    'name': primary_component.name,
                    'type': primary_component.chunk_type.value,
                    'description': primary_component.description
                },
                'related_components': related_components,
                'relationship_type': relationship_type,
                'total_found': len(related_components)
            }
            
        except Exception as e:
            logger.error(f"Error finding related components: {e}")
            return {
                'success': False,
                'error': f'Search for related components failed: {str(e)}'
            }
    
    async def get_project_overview(self, acd_path: str) -> Dict[str, Any]:
        """
        Get project overview from indexed vector database content

        Args:
            acd_path: Path to the ACD/L5K file, or the directory passed to
                index_exported_l5x_files - its filename/directory stem must match
                a key in indexed_projects (i.e. this project must actually have
                been indexed already under this same path).

        Returns:
            Dictionary with project overview from indexed data
        """
        try:
            logger.info(f"Getting project overview from vector database for {acd_path}")

            # Get overview from vector database indexed projects
            project_name = Path(acd_path).stem
            indexed_projects = self.vector_db.indexed_projects

            # Check if we have data for this exact project. Previously this fell
            # back to "use first available indexed project" when the name didn't
            # match - silently returning a different, unrelated project's data
            # with no indication a substitution happened. Fail clearly instead.
            if project_name not in indexed_projects:
                if not indexed_projects:
                    return {
                        'success': False,
                        'error': 'No L5X data indexed. Use index_acd_project or index_exported_l5x_files first.'
                    }
                return {
                    'success': False,
                    'error': f"Project '{project_name}' has not been indexed.",
                    'indexed_projects': sorted(indexed_projects.keys()),
                    'hint': 'Call index_acd_project or index_exported_l5x_files with this exact path first, '
                            'or pass one of the paths already listed in indexed_projects above.'
                }

            project_stats = indexed_projects[project_name]

            # Get all chunks to analyze structure - scoped to this project only.
            # Previously unscoped, so this always reflected whatever project was
            # indexed most recently rather than the one actually requested.
            all_chunks = []
            try:
                structure_results = self.vector_db.search_l5x_content(
                    "routine program tag", limit=1000,  # Get lots of results for overview
                    project_name=project_name
                )
                all_chunks = structure_results
            except Exception as e:
                logger.warning(f"Could not retrieve structure details: {e}")
            
            # Analyze the chunks to build overview
            programs = set()
            routines = set()
            udts = set()
            tags = set()
            
            for result in all_chunks:
                if result.location.parent_program:
                    programs.add(result.location.parent_program)
                if result.location.parent_routine:
                    routines.add(result.location.parent_routine)
                if result.chunk_type.value == 'udt':
                    udts.add(result.name)
                # Tags would need additional parsing
            
            return {
                'success': True,
                'project_path': acd_path,
                'project_name': project_name,
                'indexing_stats': {
                    'files_indexed': project_stats.get('file_count', 0),
                    'chunks_created': project_stats.get('chunk_count', 0),
                    'last_indexed': project_stats.get('last_indexed', 'Unknown')
                },
                'overview': {
                    'program_count': len(programs),
                    'routine_count': len(routines),
                    'udt_count': len(udts),
                    'total_chunks': len(all_chunks)
                },
                'programs': list(programs),
                'routines': list(routines),
                'udts': list(udts),
                'note': 'Overview generated from indexed L5X data. Results may vary based on what L5X files were exported and indexed.'
            }
            
        except Exception as e:
            logger.error(f"Error getting project overview: {e}")
            return {
                'success': False,
                'error': f'Failed to get project overview: {str(e)}'
            }

    async def find_tag_references(self, tag_name: str, project_name: Optional[str] = None,
                                   access: Optional[str] = None, include_members: bool = True,
                                   limit: int = 200) -> Dict[str, Any]:
        """
        Exact (non-semantic) cross-reference: every rung/ST line in indexed
        content that references tag_name, with read/write classification
        where it can be derived. Complements search_l5x_content's semantic
        search - guaranteed recall for a specific tag, rather than
        similarity ranking that can drop a genuinely relevant rung below
        its score threshold.

        Args:
            tag_name: Exact tag or dotted member reference, e.g. "Motor_1"
                or "Motor_1.Running". Case-insensitive (Logix is
                case-insensitive, case-preserving).
            project_name: Optional - restrict to one indexed project. Omit
                to search every indexed project.
            access: Optional filter - "read", "write", or "unknown".
            include_members: Also return references to members of
                tag_name (e.g. Motor_1.Running when asked for Motor_1).
                Default True.
            limit: Maximum references to return (default 200).

        Returns:
            Dictionary with matching references and coverage limitations.
        """
        try:
            xref = self.vector_db.get_xref(project_name=project_name)
            if isinstance(xref, dict):
                return {'success': False, **xref}

            matches = xref.lookup(tag_name, include_members=include_members, access=access)
            total_found = len(matches)

            return {
                'success': True,
                'tag_name': tag_name,
                'project_scope': project_name or 'all indexed projects',
                'total_found': total_found,
                'references': [self._serialize_reference(r) for r in matches[:limit]],
                'truncated': total_found > limit,
                'limitations': self._xref_limitations(xref),
            }

        except Exception as e:
            logger.error(f"Error finding tag references for {tag_name}: {e}")
            return {
                'success': False,
                'error': f'Tag reference lookup failed: {str(e)}'
            }

    async def search_tag_references(self, pattern: str, project_name: Optional[str] = None,
                                     regex: bool = True, limit: int = 50,
                                     refs_per_symbol: int = 10) -> Dict[str, Any]:
        """
        Find indexed tag/member NAMES matching a pattern (not logic text),
        and list where each is referenced.

        Args:
            pattern: Pattern matched against symbol names, e.g. "^Conv3_".
                An invalid regex falls back to a literal substring match.
            project_name: Optional - restrict to one indexed project.
            regex: Treat pattern as a regular expression (default True);
                False forces literal substring matching.
            limit: Maximum distinct symbols to return (default 50).
            refs_per_symbol: Maximum references listed per symbol
                (default 10).

        Returns:
            Dictionary mapping matched symbol names to their references.
        """
        try:
            xref = self.vector_db.get_xref(project_name=project_name)
            if isinstance(xref, dict):
                return {'success': False, **xref}

            matched = xref.search(pattern, regex=regex, limit=limit)
            symbols = {
                symbol: [self._serialize_reference(r) for r in refs[:refs_per_symbol]]
                for symbol, refs in matched.items()
            }

            return {
                'success': True,
                'pattern': pattern,
                'project_scope': project_name or 'all indexed projects',
                'symbols_found': len(symbols),
                'symbols': symbols,
                'limitations': self._xref_limitations(xref),
            }

        except Exception as e:
            logger.error(f"Error searching tag references for pattern {pattern}: {e}")
            return {
                'success': False,
                'error': f'Tag reference search failed: {str(e)}'
            }

    @staticmethod
    def _serialize_reference(ref) -> Dict[str, Any]:
        return {
            'symbol': ref.symbol,
            'base_tag': ref.base_tag,
            'access': ref.access,
            'instruction': ref.instruction,
            'operand_index': ref.operand_index,
            'program': ref.program,
            'routine': ref.routine,
            'rung_number': ref.rung_number,
            'line_number': ref.line_number,
            'project_name': ref.project_name,
        }

    @staticmethod
    def _xref_limitations(xref) -> Dict[str, Any]:
        return {
            'note': 'This index covers indexed ladder (RLL) rungs and Structured Text lines only. '
                    'AOI internal logic, FBD/SFC routines, and controller/program tag declarations '
                    'are not indexed - "no references found" means none were found in what was '
                    'indexed, not that the tag is definitely unused.',
            'skipped_chunks': dict(xref.skipped_chunks),
            'possible_aoi_calls': dict(xref.aoi_calls),
        }

    def get_available_tools(self) -> Dict[str, str]:
        """Get list of available MCP tools"""
        return {
            tool.value: f"L5X analysis tool: {tool.value.replace('_', ' ').title()}"
            for tool in L5XMCPTools
        }
