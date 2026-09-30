#!/usr/bin/env python3
"""
SDK-Powered L5X Analyzer

Leverages the Studio 5000 SDK for extracting, analyzing, and modifying L5X content
in production-scale ACD/L5K projects.
"""

import asyncio
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging

from .l5x_chunk import L5XChunk, L5XChunkType, L5XLocation, create_ladder_rung_chunk, create_routine_chunk, create_udt_chunk

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from logix_designer_sdk import LogixProject
    _LOGIX_PROJECT_IMPORT_ERROR = None
except ImportError as e:
    LogixProject = None
    _LOGIX_PROJECT_IMPORT_ERROR = e

def conversion_hint(error_text: str) -> str:
    """Plain-language next step for an SDK conversion failure (the raw SDK text is often cryptic)."""
    low = error_text.lower()
    if "import_aborted" in low or "import was cancelled" in low:
        return ("The SDK could not import this L5X as a whole project (usually hardware/module profiles "
                "or add-on definitions that aren't installed on this machine, or a revision mismatch). "
                "Open the L5X in Studio 5000 (File > Open) to see the import error log. "
                "ACD -> L5X export is unaffected.")
    if any(w in low for w in ("lock", "in use", "being used by another process", "access is denied")):
        return "The file looks locked - it may be open in Studio 5000. Close it, or export manually from Studio 5000."
    if "revision" in low or "version" in low:
        return "The project may need a different Logix Designer revision than the one installed."
    return "See the SDK error above; try opening the file in Studio 5000 to confirm it is healthy."


class SDKPoweredL5XAnalyzer:
    """
    Uses Studio 5000 SDK for L5X analysis and modification operations.
    Handles large ACD/L5K files by extracting only needed sections.
    """
    
    def __init__(self, temp_dir: Optional[str] = None):
        self.sdk_project = None
        self.project_path = None
        self.is_project_open = False
        
        # Temporary directory for L5X extractions
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "l5x_analyzer"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Cache of extracted content
        self.extraction_cache = {}
        
        # Check SDK availability
        self.sdk_available = self._check_sdk_availability()
        
    def _check_sdk_availability(self) -> bool:
        """Check if Studio 5000 SDK is available"""
        try:
            import logix_designer_sdk
            logger.info("Studio 5000 SDK is available")
            return True
        except ImportError:
            logger.warning("Studio 5000 SDK not available - falling back to XML parsing only")
            return False
    
    async def open_project(self, project_path: str) -> bool:
        """
        Open an ACD/L5K project file via the Logix Designer SDK.

        This launches (or attaches to) the Logix Designer engine in the
        background through the SDK's gRPC bridge, so the first call can take
        a while for large projects - that is expected, not a hang.

        Args:
            project_path: Path to ACD or L5K file

        Returns:
            True if the project was opened successfully
        """
        if not self.sdk_available or LogixProject is None:
            logger.error(f"Cannot open project - Logix Designer SDK not available: {_LOGIX_PROJECT_IMPORT_ERROR}")
            self.is_project_open = False
            return False

        try:
            logger.info(f"Opening project via Logix Designer SDK: {project_path}")
            self.sdk_project = await LogixProject.open_logix_project(project_path)
            self.project_path = project_path
            self.is_project_open = True
            logger.info(f"Project opened successfully: {project_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to open project {project_path}: {e}")
            self.sdk_project = None
            self.project_path = None
            self.is_project_open = False
            return False
    
    def close_project(self):
        """Close the currently open project"""
        if self.sdk_project:
            try:
                self.sdk_project.close()
                logger.info("Project closed successfully")
            except Exception as e:
                logger.warning(f"Error closing project: {e}")
            finally:
                self.sdk_project = None
                self.project_path = None
                self.is_project_open = False
                self.extraction_cache.clear()
    
    async def discover_project_structure(self) -> Dict[str, Any]:
        """
        Discover the structure of the open project
        
        Returns:
            Dictionary containing project structure information
        """
        if not self.is_project_open:
            raise RuntimeError("No project is currently open")
        
        structure = {
            'project_path': self.project_path,
            'programs': [],
            'routines': [],
            'udts': [],
            'tags': [],
            'modules': []
        }
        
        try:
            # "Controller" alone is not a valid export XPath for this SDK version -
            # export its Programs/Tags/DataTypes children separately and merge.
            for section, filename in (
                ("Controller/Programs", "project_overview_programs.L5X"),
                ("Controller/Tags", "project_overview_tags.L5X"),
                ("Controller/DataTypes", "project_overview_datatypes.L5X"),
            ):
                section_path = self.temp_dir / filename
                if section_path.exists():
                    section_path.unlink()
                await self.sdk_project.partial_export_to_xml_file(section, str(section_path))

                section_structure = self._parse_project_overview(section_path)
                structure['programs'].extend(section_structure['programs'])
                structure['routines'].extend(section_structure['routines'])
                structure['udts'].extend(section_structure['udts'])
                structure['tags'].extend(section_structure['tags'])

            structure['project_path'] = self.project_path

            logger.info(f"Discovered project structure: {len(structure['programs'])} programs, "
                       f"{len(structure['routines'])} routines, {len(structure['udts'])} UDTs")

        except Exception as e:
            logger.error(f"Failed to discover project structure: {e}")

        return structure
    
    async def extract_routine_for_analysis(self, routine_name: str, program_name: str = "MainProgram") -> Optional[str]:
        """
        Extract specific routine to L5X file for analysis
        
        Args:
            routine_name: Name of routine to extract
            program_name: Name of parent program
            
        Returns:
            Path to extracted L5X file or None if failed
        """
        if not self.is_project_open:
            raise RuntimeError("No project is currently open")
        
        cache_key = f"{program_name}_{routine_name}"
        if cache_key in self.extraction_cache:
            return self.extraction_cache[cache_key]
        
        try:
            # Generate XPath for the specific routine
            xpath = f"Controller/Programs/Program[@Name='{program_name}']/Routines/Routine[@Name='{routine_name}']"
            
            # Create output file path
            output_path = self.temp_dir / f"{program_name}_{routine_name}_routine.L5X"
            if output_path.exists():
                output_path.unlink()

            # Extract routine using SDK
            await self.sdk_project.partial_export_to_xml_file(xpath, str(output_path))
            
            # Cache the result
            self.extraction_cache[cache_key] = str(output_path)
            
            logger.info(f"Extracted routine {routine_name} to {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to extract routine {routine_name}: {e}")
            return None
    
    async def extract_routine_rungs(self, routine_name: str, program_name: str = "MainProgram", 
                                  rung_range: Optional[Tuple[int, int]] = None) -> Optional[str]:
        """
        Extract specific rungs from a routine
        
        Args:
            routine_name: Name of routine
            program_name: Name of parent program  
            rung_range: Tuple of (start_rung, end_rung) or None for all rungs
            
        Returns:
            Path to extracted L5X file with rungs
        """
        if not self.is_project_open:
            raise RuntimeError("No project is currently open")
        
        try:
            if rung_range:
                start_rung, end_rung = rung_range
                xpath = f"Controller/Programs/Program[@Name='{program_name}']/Routines/Routine[@Name='{routine_name}']/RLLContent/Rung[@Number>='{start_rung}'][@Number<='{end_rung}']"
                output_name = f"{routine_name}_rungs_{start_rung}_{end_rung}.L5X"
            else:
                xpath = f"Controller/Programs/Program[@Name='{program_name}']/Routines/Routine[@Name='{routine_name}']/RLLContent"
                output_name = f"{routine_name}_all_rungs.L5X"
            
            output_path = self.temp_dir / output_name
            if output_path.exists():
                output_path.unlink()

            await self.sdk_project.partial_export_to_xml_file(xpath, str(output_path))

            logger.info(f"Extracted rungs from {routine_name} to {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to extract rungs from {routine_name}: {e}")
            return None
    
    async def insert_ladder_logic_surgically(self, routine_name: str, insert_position: int, 
                                           new_logic_l5x: str, program_name: str = "MainProgram",
                                           replace_count: int = 0) -> bool:
        """
        Insert ladder logic at exact rung position using SDK
        
        Args:
            routine_name: Target routine name
            insert_position: Rung number to insert at
            new_logic_l5x: Path to L5X file containing new logic
            program_name: Parent program name
            replace_count: Number of existing rungs to replace (0 = insert only)
            
        Returns:
            True if insertion successful
        """
        if not self.is_project_open:
            raise RuntimeError("No project is currently open")
        
        try:
            from logix_designer_sdk import PartialImportOption
            
            # Generate XPath for the routine's RLL content
            xpath = f"Controller/Programs/Program[@Name='{program_name}']/Routines/Routine[@Name='{routine_name}']/RLLContent"
            
            # Use SDK to insert rungs at specific position
            await self.sdk_project.partial_import_rungs_from_xml_file(
                xpath,
                insert_position,
                replace_count, 
                new_logic_l5x,
                PartialImportOption.IMPORT_OFFLINE
            )
            
            logger.info(f"Successfully inserted logic at rung {insert_position} in {routine_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert logic in {routine_name} at position {insert_position}: {e}")
            return False
    
    async def save_project(self, save_path: Optional[str] = None) -> bool:
        """
        Save the current project
        
        Args:
            save_path: Optional path to save to (if None, saves to current path)
            
        Returns:
            True if save successful
        """
        if not self.is_project_open:
            raise RuntimeError("No project is currently open")
        
        try:
            if save_path:
                await self.sdk_project.save_as(save_path, True)
                logger.info(f"Project saved to: {save_path}")
            else:
                await self.sdk_project.save()
                logger.info("Project saved successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save project: {e}")
            return False
    
    async def convert_project(self, source_path: str, dest_path: str,
                              detailed_l5x: bool = False, timeout_s: float = 600) -> Dict[str, Any]:
        """
        Convert a project between formats via the SDK (ACD -> L5X or L5X -> ACD).

        The SDK's save_as picks the output format from dest_path's extension. Uses its own
        SDK handle, so it does not disturb a project opened for indexing. dest_path must not
        exist - save_as is called with force=False so nothing is ever overwritten.
        """
        import time

        if not self.sdk_available or LogixProject is None:
            return {'success': False, 'error': f"Logix Designer SDK not available: {_LOGIX_PROJECT_IMPORT_ERROR}"}
        dest = Path(dest_path)
        if dest.exists():
            return {'success': False, 'error': f"Refusing to overwrite existing file: {dest}"}

        started = time.monotonic()
        project = None

        async def _run():
            nonlocal project
            project = await LogixProject.open_logix_project(str(source_path))
            await project.save_as(str(dest), False, detailed_l5x)

        try:
            await asyncio.wait_for(_run(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return {'success': False, 'error': f"Timed out after {timeout_s:.0f}s converting {source_path}"}
        except Exception as e:
            msg = str(e)
            return {'success': False, 'error': f"Conversion failed: {msg}", 'hint': conversion_hint(msg)}
        finally:
            if project is not None:
                try:
                    project.close()  # synchronous in the SDK
                except Exception as e:
                    logger.warning(f"Error closing project after conversion: {e}")

        if not dest.exists():
            return {'success': False, 'error': f"SDK reported success but {dest} was not created"}
        return {
            'success': True,
            'source': str(source_path),
            'output': str(dest),
            'size_bytes': dest.stat().st_size,
            'elapsed_s': round(time.monotonic() - started, 1),
        }

    def parse_routine_l5x(self, l5x_file_path: str, program_name: Optional[str] = None) -> List[L5XChunk]:
        """
        Parse an extracted routine L5X file into chunks

        Args:
            l5x_file_path: Path to extracted L5X file
            program_name: Parent program the file was exported from. ElementTree can't walk
                to a parent element, so the caller (which built the export XPath) supplies it.

        Returns:
            List of L5X chunks representing the routine content
        """
        chunks = []
        
        try:
            tree = ET.parse(l5x_file_path)
            root = tree.getroot()
            
            # ElementTree has no parent links - build them so each routine's owning Program
            # (or AOI) can be found from the XML itself, for routine exports and whole-controller
            # exports alike.
            parents = {child: parent for parent in root.iter() for child in parent}

            def _ancestor(elem, tag):
                while elem in parents:
                    elem = parents[elem]
                    if elem.tag == tag:
                        return elem
                return None

            fallback_program = program_name or 'MainProgram'

            for routine in root.findall(".//Routine"):
                # AOI-embedded routines (Logic/Prescan/EnableInFalse) ride along as dependencies
                # of a routine export and aren't program routines.
                if _ancestor(routine, 'AddOnInstructionDefinition') is not None:
                    continue

                routine_name = routine.get('Name', 'Unknown')
                routine_type = routine.get('Type', 'RLL')
                program_elem = _ancestor(routine, 'Program')
                program_name = program_elem.get('Name', fallback_program) if program_elem is not None else fallback_program

                # Create routine chunk
                routine_content = ET.tostring(routine, encoding='unicode')
                routine_chunk = create_routine_chunk(
                    routine_name, program_name, routine_type, 
                    routine_content, file_path=l5x_file_path
                )
                chunks.append(routine_chunk)
                
                # Parse individual rungs if it's ladder logic
                if routine_type == 'RLL':
                    rll_content = routine.find('RLLContent')
                    if rll_content is not None:
                        rungs = rll_content.findall('Rung')
                        
                        for rung in rungs:
                            rung_number = int(rung.get('Number', 0))
                            
                            # Get rung text content
                            text_elem = rung.find('Text')
                            rung_logic = text_elem.text if text_elem is not None else ""
                            
                            # Get rung comment
                            comment_elem = rung.find('Comment')
                            rung_comment = comment_elem.text if comment_elem is not None else None
                            
                            # Create rung chunk
                            rung_chunk = create_ladder_rung_chunk(
                                routine_name, program_name, rung_number,
                                rung_logic, rung_comment, l5x_file_path
                            )
                            chunks.append(rung_chunk)
            
            logger.info(f"Parsed {len(chunks)} chunks from {l5x_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to parse routine L5X file {l5x_file_path}: {e}")
        
        return chunks
    
    def _parse_project_overview(self, overview_path: Path) -> Dict[str, Any]:
        """Parse project overview L5X to discover structure"""
        structure = {
            'programs': [],
            'routines': [],
            'udts': [],
            'tags': [],
            'modules': []
        }
        
        try:
            tree = ET.parse(overview_path)
            root = tree.getroot()
            
            # Discover programs
            programs = root.findall(".//Programs/Program")
            for program in programs:
                program_name = program.get('Name', 'Unknown')
                structure['programs'].append(program_name)
                
                # Discover routines within each program
                routines = program.findall(".//Routines/Routine")
                for routine in routines:
                    routine_name = routine.get('Name', 'Unknown')
                    routine_type = routine.get('Type', 'RLL')
                    structure['routines'].append({
                        'name': routine_name,
                        'type': routine_type,
                        'program': program_name
                    })
            
            # Discover UDTs
            data_types = root.findall(".//DataTypes/DataType[@Class='User']")
            for dt in data_types:
                udt_name = dt.get('Name', 'Unknown')
                structure['udts'].append(udt_name)
            
            # Discover tags
            tags = root.findall(".//Tags/Tag")
            for tag in tags:
                tag_name = tag.get('Name', 'Unknown')
                tag_type = tag.get('DataType', 'Unknown')
                structure['tags'].append({
                    'name': tag_name,
                    'data_type': tag_type
                })
            
        except Exception as e:
            logger.error(f"Failed to parse project overview: {e}")
        
        return structure
    
    def create_rung_l5x_fragment(self, ladder_logic: str, rung_comment: str = None) -> str:
        """
        Create a small L5X fragment containing new ladder logic rungs
        
        Args:
            ladder_logic: Ladder logic text (can be multiple rungs separated by semicolons)
            rung_comment: Optional comment for the rung(s)
            
        Returns:
            Path to created L5X fragment file
        """
        try:
            # Split logic into individual rungs
            rung_texts = [logic.strip() for logic in ladder_logic.split(';') if logic.strip()]
            
            # Create L5X fragment
            root = ET.Element("RSLogix5000Content")
            root.set("SchemaRevision", "1.0")
            root.set("SoftwareRevision", "36.02")
            
            controller = ET.SubElement(root, "Controller")
            controller.set("Use", "Context")
            controller.set("Name", "TempController")
            
            programs = ET.SubElement(controller, "Programs")
            programs.set("Use", "Context")
            
            program = ET.SubElement(programs, "Program")
            program.set("Use", "Context")
            program.set("Name", "TempProgram")
            
            routines = ET.SubElement(program, "Routines")
            routine = ET.SubElement(routines, "Routine")
            routine.set("Use", "Context")
            routine.set("Name", "TempRoutine")
            routine.set("Type", "RLL")
            
            rll_content = ET.SubElement(routine, "RLLContent")
            
            # Add each rung
            for i, rung_text in enumerate(rung_texts):
                rung = ET.SubElement(rll_content, "Rung")
                rung.set("Number", str(i))
                rung.set("Type", "N")
                
                if rung_comment:
                    comment = ET.SubElement(rung, "Comment")
                    comment.text = rung_comment
                
                text = ET.SubElement(rung, "Text")
                text.text = rung_text
            
            # Save to temporary file
            fragment_path = self.temp_dir / f"logic_fragment_{id(ladder_logic)}.L5X"
            
            tree = ET.ElementTree(root)
            tree.write(fragment_path, encoding='UTF-8', xml_declaration=True)
            
            logger.info(f"Created L5X fragment with {len(rung_texts)} rungs: {fragment_path}")
            return str(fragment_path)
            
        except Exception as e:
            logger.error(f"Failed to create L5X fragment: {e}")
            return None
    
    def cleanup_temp_files(self):
        """Clean up temporary extraction files"""
        try:
            for file_path in self.temp_dir.glob("*.L5X"):
                file_path.unlink()
            logger.info("Cleaned up temporary L5X files")
        except Exception as e:
            logger.warning(f"Error cleaning up temp files: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close_project()
        self.cleanup_temp_files()
