#!/usr/bin/env python3
"""
L5X Vector Database

Creates and manages a vector database for semantic search of L5X content
extracted using the Studio 5000 SDK. Handles production-scale projects by
indexing only relevant extracted sections.
"""

import json
import os
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging
import time

from .l5x_chunk import L5XChunk, L5XChunkType, L5XLocation
from .sdk_powered_analyzer import SDKPoweredL5XAnalyzer
from .l5x_xref import L5XTagXref, TagXrefIndex

# sentence_transformers import moved to lazy load in initialize_model()
# faiss import moved to lazy load (see _ensure_faiss) - importing it eagerly at
# module load time adds several seconds to MCP server startup and can push it
# past the client's connection timeout.
faiss = None
FAISS_AVAILABLE = None

def _ensure_faiss():
    global faiss, FAISS_AVAILABLE
    if FAISS_AVAILABLE is None:
        try:
            import faiss as _faiss
            faiss = _faiss
            FAISS_AVAILABLE = True
        except ImportError:
            FAISS_AVAILABLE = False
            logging.warning("FAISS not available - falling back to text-based search")
    return FAISS_AVAILABLE

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reuses the server's shared lock (so a concurrent tools/call can't build the
# xref twice, or read it mid-rebuild while build_vector_database reassigns
# chunks_data), but not its storage - SharedCacheManager only has file-
# validity/staleness helpers, no key/value store, so xref caching below is a
# plain in-memory dict. Falls back to a private lock if mcp_server isn't on
# the path (e.g. this module imported in isolation), so l5x_analyzer never
# hard-depends on mcp_server - mcp_server already depends on l5x_analyzer,
# and a two-way dependency would be a cycle.
try:
    from mcp_server.cache_manager import shared_cache_manager
except ImportError:
    import threading as _threading

    class _FallbackCacheManager:
        def get_cache_lock(self, name):
            return _threading.Lock()

    shared_cache_manager = _FallbackCacheManager()

@dataclass
class L5XSearchResult:
    """Represents a search result from L5X content"""
    chunk_id: str
    chunk_type: L5XChunkType
    name: str
    description: str
    score: float
    content: str
    location: L5XLocation
    file_path: str
    insertion_hints: List[str] = None
    
    def __post_init__(self):
        if self.insertion_hints is None:
            self.insertion_hints = []

class L5XVectorDatabase:
    """Vector database for L5X content with SDK integration"""
    
    def __init__(self, cache_dir: str = "l5x_vector_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize sentence transformer for embeddings
        self.model = None
        self.index = None
        self.chunks_data = []
        self.embeddings = None
        
        # SDK analyzer for content extraction
        self.sdk_analyzer = None
        
        # Cache file paths
        self.index_cache = self.cache_dir / "l5x_index.faiss"
        self.embeddings_cache = self.cache_dir / "l5x_embeddings.pkl"
        self.data_cache = self.cache_dir / "l5x_chunks.pkl"
        self.metadata_cache = self.cache_dir / "l5x_metadata.json"
        
        # Project indexing status
        self.indexed_projects = {}

        # Exact-match tag cross-reference (see l5x_xref.py). Cached per
        # project_name (None = all indexed projects combined), rebuilt from
        # chunks_data on first request after any (re-)index - see
        # invalidate_xref() and get_xref().
        self._xref_builder = L5XTagXref()
        self._xref_cache: Dict[Optional[str], "TagXrefIndex"] = {}
    
    def initialize_model(self):
        """Initialize the sentence transformer model"""
        if self.model is None:
            logger.info("Loading sentence transformer model...")
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load sentence transformer: {e}")
                self.model = None
    
    def index_exported_l5x_files(self, l5x_directory: str, force_rebuild: bool = False) -> bool:
        """
        Index EXPORTED L5X files directly (no SDK opening required)
        
        Args:
            l5x_directory: Directory containing exported L5X files
            force_rebuild: Force rebuild even if cached
            
        Returns:
            True if indexing successful
        """
        l5x_dir = Path(l5x_directory)
        if not l5x_dir.exists():
            logger.error(f"L5X directory not found: {l5x_directory}")
            return False
        
        # Find all L5X files in directory. Deduplicate by resolved path: on
        # case-insensitive filesystems (Windows, default macOS) glob("*.L5X")
        # and glob("*.l5x") match the identical file, which previously double-
        # counted (and double-indexed) every file - every chunk/rung count in
        # get_project_overview/analyze_routine_structure came out exactly 2x.
        l5x_files = list({
            f.resolve() for f in list(l5x_dir.glob("*.L5X")) + list(l5x_dir.glob("*.l5x"))
        })
        if not l5x_files:
            logger.error(f"No L5X files found in: {l5x_directory}")
            return False
        
        logger.info(f"Found {len(l5x_files)} L5X files to index")
        
        # Initialize SDK analyzer for parsing only (no opening)
        if not self.sdk_analyzer:
            self.sdk_analyzer = SDKPoweredL5XAnalyzer()
        
        # Parse all L5X files directly
        all_chunks = []
        for l5x_file in l5x_files:
            logger.info(f"Parsing L5X file: {l5x_file.name}")
            chunks = self.sdk_analyzer.parse_routine_l5x(str(l5x_file))
            all_chunks.extend(chunks)
        
        logger.info(f"Parsed {len(all_chunks)} chunks from {len(l5x_files)} L5X files")

        # Tag every chunk with which project it belongs to, then merge into the
        # full multi-project chunk store (replacing only this project's own old
        # chunks, if any) instead of wiping out every other indexed project.
        project_name = l5x_dir.name
        for chunk in all_chunks:
            chunk.project_name = project_name
        merged_chunks = self._merge_project_chunks(project_name, all_chunks)

        # Build vector database from the full merged chunk set
        self.build_vector_database(merged_chunks, force_rebuild=True)

        # Update indexing status
        self.indexed_projects[project_name] = {
            'path': l5x_directory,
            'indexed_at': time.time(),
            'file_count': len(l5x_files),
            'chunk_count': len(all_chunks)
        }
        self._save_metadata()

        logger.info(f"✅ Successfully indexed {len(l5x_files)} L5X files with {len(all_chunks)} chunks")
        return True

    def _merge_project_chunks(self, project_name: str, new_chunks: List["L5XChunk"]) -> List["L5XChunk"]:
        """
        Merge newly-indexed chunks for one project into the full multi-project
        chunk store, replacing only that project's own previous chunks (if this
        is a re-index) and leaving every other project's chunks untouched.

        This is the fix for the chunks_data/indexed_projects mismatch: chunks_data
        used to be replaced wholesale (self.chunks_data = l5x_chunks) on every
        index call, silently discarding every other project ever indexed while
        indexed_projects kept listing them as present.
        """
        other_projects_chunks = [
            c for c in self.chunks_data if getattr(c, 'project_name', None) != project_name
        ]
        return other_projects_chunks + new_chunks

    async def index_acd_project(self, acd_path: str, routines_to_index: List[str] = None,
                              force_rebuild: bool = False) -> bool:
        """
        Index ACD/L5K project by extracting routines via SDK
        
        Args:
            acd_path: Path to ACD or L5K file
            routines_to_index: Specific routines to index (if None, discovers all)
            force_rebuild: Force rebuild even if cached
            
        Returns:
            True if indexing successful
        """
        project_name = Path(acd_path).stem
        
        # Check if already indexed and not forcing rebuild
        if not force_rebuild and self._is_project_indexed(project_name):
            logger.info(f"Project {project_name} already indexed")
            return True
        
        try:
            # Initialize SDK analyzer if needed
            if not self.sdk_analyzer:
                self.sdk_analyzer = SDKPoweredL5XAnalyzer()
            
            # Open project via the Logix Designer SDK
            opened = await self.sdk_analyzer.open_project(acd_path)
            if not opened:
                logger.error(f"Failed to open project: {acd_path}")
                return False

            # Discover project structure
            project_structure = await self.sdk_analyzer.discover_project_structure()
            
            # Determine which routines to index
            if routines_to_index is None:
                routines_to_index = [r['name'] for r in project_structure['routines']]
            
            logger.info(f"Indexing {len(routines_to_index)} routines from {project_name}")
            
            # Extract and parse each routine
            all_chunks = []
            for routine_info in project_structure['routines']:
                routine_name = routine_info['name']
                program_name = routine_info.get('program', 'MainProgram')
                
                if routine_name in routines_to_index:
                    chunks = await self._extract_and_parse_routine(
                        routine_name, program_name, acd_path
                    )
                    all_chunks.extend(chunks)
            
            # Tag every chunk with which project it belongs to, then merge into
            # the full multi-project chunk store instead of wiping out every
            # other indexed project (see _merge_project_chunks for why).
            for chunk in all_chunks:
                chunk.project_name = project_name
            merged_chunks = self._merge_project_chunks(project_name, all_chunks)

            # Build vector database from the full merged chunk set
            self.build_vector_database(merged_chunks, force_rebuild=True)

            # Update project indexing status
            self.indexed_projects[project_name] = {
                'path': acd_path,
                'indexed_at': time.time(),
                'routine_count': len(routines_to_index),
                'chunk_count': len(all_chunks)
            }
            self._save_metadata()
            
            logger.info(f"Successfully indexed {len(all_chunks)} chunks from {project_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index project {acd_path}: {e}")
            return False
        finally:
            if self.sdk_analyzer:
                self.sdk_analyzer.close_project()
    
    async def _extract_and_parse_routine(self, routine_name: str, program_name: str, 
                                       acd_path: str) -> List[L5XChunk]:
        """Extract and parse a single routine into chunks"""
        try:
            # Extract routine using SDK
            l5x_path = await self.sdk_analyzer.extract_routine_for_analysis(
                routine_name, program_name
            )
            
            if not l5x_path:
                logger.warning(f"Failed to extract routine {routine_name}")
                return []
            
            # Parse extracted L5X into chunks
            chunks = self.sdk_analyzer.parse_routine_l5x(l5x_path)
            
            # Update file path in chunks
            for chunk in chunks:
                chunk.location.file_path = acd_path
            
            logger.debug(f"Extracted {len(chunks)} chunks from routine {routine_name}")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to extract/parse routine {routine_name}: {e}")
            return []
    
    def build_vector_database(self, l5x_chunks: List[L5XChunk], force_rebuild: bool = False):
        """Build or load the vector database from L5X chunks"""
        _ensure_faiss()

        # Check if cached version exists and is recent
        if not force_rebuild and self._cache_exists() and self._cache_is_recent():
            logger.info("Loading cached L5X vector database...")
            self._load_from_cache()
            return

        logger.info(f"Building vector database for {len(l5x_chunks)} L5X chunks...")

        self.chunks_data = l5x_chunks
        self.invalidate_xref()
        self.initialize_model()
        
        if self.model is None or not FAISS_AVAILABLE:
            logger.warning("Vector search not available, using text-only search")
            self._save_to_cache()
            return
        
        # Create embeddings for all chunks
        texts_to_embed = []
        for chunk in l5x_chunks:
            text = chunk.searchable_text
            texts_to_embed.append(text)
        
        logger.info("Creating embeddings...")
        start_time = time.time()
        self.embeddings = self.model.encode(texts_to_embed, show_progress_bar=True)
        embedding_time = time.time() - start_time
        logger.info(f"Created {len(self.embeddings)} embeddings in {embedding_time:.2f} seconds")
        
        # Build FAISS index for fast similarity search
        logger.info("Building FAISS index...")
        dimension = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
        
        # Normalize embeddings for cosine similarity
        faiss.normalize_L2(self.embeddings)
        self.index.add(self.embeddings.astype(np.float32))
        
        # Save to cache
        self._save_to_cache()
        logger.info("L5X vector database built and cached successfully")
    
    def search_l5x_content(self, query: str, limit: int = 20, score_threshold: float = 0.1,
                          chunk_types: List[L5XChunkType] = None,
                          project_name: Optional[str] = None) -> List[L5XSearchResult]:
        """
        Search L5X content using vector similarity

        Args:
            query: Search query
            limit: Maximum results to return
            score_threshold: Minimum similarity score
            chunk_types: Filter by specific chunk types
            project_name: Optional - restrict results to one indexed project (see
                indexed_projects). Omit to search across every indexed project.

        Returns:
            List of search results ranked by similarity
        """
        if not self.chunks_data:
            logger.warning("No L5X content has been indexed")
            return []

        if not self.model or not self.index:
            logger.warning("Vector search not available, falling back to text search")
            return self._text_search(query, limit, chunk_types)

        try:
            # Create embedding for the query
            _ensure_faiss()
            query_embedding = self.model.encode([query])
            faiss.normalize_L2(query_embedding)

            # Search the index - get more results initially for better coverage
            search_limit = min(limit * 5, len(self.chunks_data), 1000)  # Search more broadly
            scores, indices = self.index.search(query_embedding.astype(np.float32), search_limit)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if score >= score_threshold and idx < len(self.chunks_data):
                    chunk = self.chunks_data[idx]

                    # Apply chunk type filter
                    if chunk_types and chunk.chunk_type not in chunk_types:
                        continue

                    # Apply project scope filter
                    if project_name and getattr(chunk, 'project_name', None) != project_name:
                        continue

                    result = L5XSearchResult(
                        chunk_id=chunk.id,
                        chunk_type=chunk.chunk_type,
                        name=chunk.name,
                        description=chunk.description,
                        score=float(score),
                        content=chunk.content,
                        location=chunk.location,
                        file_path=chunk.location.file_path,
                        insertion_hints=self._generate_insertion_hints(chunk)
                    )
                    results.append(result)
                    
                    if len(results) >= limit:
                        break
            
            logger.info(f"Found {len(results)} results for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._text_search(query, limit, chunk_types)
    
    def get_xref(self, project_name: Optional[str] = None):
        """
        Get the exact-match tag cross-reference index, building and caching
        it on first request. Complements search_l5x_content's semantic
        search with guaranteed recall for "every reference to tag X" - see
        l5x_xref.py for why a regex index and semantic search are both
        needed rather than one replacing the other.

        Args:
            project_name: Optional - restrict to one indexed project. Omit
                to build a combined index over every indexed project's chunks.

        Returns:
            A TagXrefIndex, or a dict with an 'error' key if the request
            can't be satisfied right now (no content indexed yet, no
            content for that project, or a stale pre-project_name cache
            that needs re-indexing - see the check below).
        """
        if project_name in self._xref_cache:
            return self._xref_cache[project_name]

        if not self.chunks_data:
            return {'error': 'No L5X content has been indexed yet. '
                              'Use index_acd_project or index_exported_l5x_files first.'}

        if project_name:
            scoped_chunks = [c for c in self.chunks_data if getattr(c, 'project_name', None) == project_name]
            if not scoped_chunks:
                # Distinguish "this project genuinely has zero chunks" from
                # "the cached chunk data predates project_name and needs a
                # re-index" - silently returning an empty index for the
                # latter would read as "this tag is unused", which is a
                # worse wrong answer than no answer at all.
                any_attributed = any(getattr(c, 'project_name', None) is not None for c in self.chunks_data)
                if not any_attributed:
                    return {
                        'error': "Indexed chunk data has no project_name attribution (this is a stale "
                                 "cache from before per-project scoping was added). Re-index with "
                                 "force_rebuild=True before requesting a specific project_name.",
                        'stale_cache': True,
                    }
                return {
                    'error': f"No indexed content found for project '{project_name}'.",
                    'indexed_projects': sorted(self.indexed_projects.keys()),
                }
        else:
            scoped_chunks = self.chunks_data

        with shared_cache_manager.get_cache_lock('l5x_xref'):
            if project_name in self._xref_cache:  # re-check after acquiring the lock
                return self._xref_cache[project_name]
            index = self._xref_builder.build(scoped_chunks, project_scope=project_name)
            self._xref_cache[project_name] = index
            return index

    def invalidate_xref(self) -> None:
        """Clear every cached cross-reference index. Called from the two
        places chunks_data is (re)assigned - build_vector_database() and
        _load_from_cache(). _merge_project_chunks already rebuilds the whole
        cross-project chunk list on every index call, so per-project
        surgical invalidation would buy nothing; just clear everything."""
        self._xref_cache.clear()

    def find_optimal_insertion_point(self, query: str, routine_name: str) -> Tuple[int, float]:
        """
        Find the best rung position to insert new logic based on semantic similarity
        
        Args:
            query: Description of logic to insert
            routine_name: Target routine name
            
        Returns:
            Tuple of (rung_position, confidence_score)
        """
        # Search for similar logic patterns in the target routine
        routine_chunks = [chunk for chunk in self.chunks_data 
                         if chunk.location.parent_routine == routine_name 
                         and chunk.chunk_type == L5XChunkType.LADDER_RUNG]
        
        if not routine_chunks:
            logger.warning(f"No indexed rungs found for routine {routine_name}")
            return 0, 0.0
        
        # Find most similar rung
        search_results = self.search_l5x_content(
            f"{query} in {routine_name}",
            limit=5,
            chunk_types=[L5XChunkType.LADDER_RUNG]
        )
        
        best_position = 0
        best_confidence = 0.0
        
        for result in search_results:
            if result.location.parent_routine == routine_name:
                # Suggest inserting after the similar logic
                position = result.location.rung_number + 1 if result.location.rung_number else 0
                confidence = result.score
                
                if confidence > best_confidence:
                    best_position = position
                    best_confidence = confidence
                    break
        
        # If no similar logic found in routine, insert at end
        if best_confidence == 0.0:
            max_rung = max([chunk.location.rung_number for chunk in routine_chunks 
                          if chunk.location.rung_number is not None], default=0)
            best_position = max_rung + 1
        
        logger.info(f"Optimal insertion point for '{query}' in {routine_name}: "
                   f"rung {best_position} (confidence: {best_confidence:.3f})")
        
        return best_position, best_confidence
    
    def find_related_components(self, chunk_id: str, relationship_types: List[str] = None) -> List[L5XSearchResult]:
        """Find components related to a given chunk"""
        chunk = next((c for c in self.chunks_data if c.id == chunk_id), None)
        if not chunk:
            return []
        
        related_results = []
        
        # Find chunks that reference the same tags/UDTs
        for dependency in chunk.dependencies:
            dependency_results = self.search_l5x_content(
                f"uses {dependency}",
                limit=10,
                score_threshold=0.2
            )
            related_results.extend(dependency_results)
        
        # Remove duplicates and the original chunk
        seen_ids = {chunk_id}
        unique_results = []
        for result in related_results:
            if result.chunk_id not in seen_ids:
                unique_results.append(result)
                seen_ids.add(result.chunk_id)
        
        return unique_results[:20]  # Limit results
    
    def get_routine_analysis(self, routine_name: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get comprehensive analysis of a routine.

        Args:
            routine_name: Name of the routine to analyze
            project_name: Optional - which indexed project to look in (see
                indexed_projects). If omitted and the routine name exists in more
                than one indexed project, returns an 'ambiguous' error listing the
                candidates instead of silently blending their chunks together -
                routine names are not unique across projects.
        """
        candidates = [chunk for chunk in self.chunks_data
                     if chunk.location.parent_routine == routine_name]

        if not candidates:
            return {'error': f'No data found for routine {routine_name}'}

        if project_name:
            routine_chunks = [c for c in candidates if getattr(c, 'project_name', None) == project_name]
            if not routine_chunks:
                found_in = sorted({getattr(c, 'project_name', None) for c in candidates} - {None})
                return {
                    'error': f"No data found for routine {routine_name} in project {project_name}",
                    'routine_found_in_other_projects': found_in
                }
        else:
            distinct_projects = sorted({getattr(c, 'project_name', None) for c in candidates} - {None})
            if len(distinct_projects) > 1:
                return {
                    'error': f"Routine name '{routine_name}' is ambiguous - it exists in {len(distinct_projects)} indexed projects",
                    'ambiguous': True,
                    'candidate_projects': distinct_projects,
                    'hint': 'Pass project_name to disambiguate.'
                }
            routine_chunks = candidates

        # Analyze rung distribution
        rung_chunks = [c for c in routine_chunks if c.chunk_type == L5XChunkType.LADDER_RUNG]
        rung_numbers = [c.location.rung_number for c in rung_chunks if c.location.rung_number is not None]
        
        # Collect all dependencies
        all_dependencies = set()
        for chunk in routine_chunks:
            all_dependencies.update(chunk.dependencies)
        
        analysis = {
            'routine_name': routine_name,
            'total_chunks': len(routine_chunks),
            'rung_count': len(rung_chunks),
            'rung_range': (min(rung_numbers), max(rung_numbers)) if rung_numbers else (0, 0),
            'dependencies': list(all_dependencies),
            'complexity_score': self._calculate_complexity_score(routine_chunks),
            'available_insertion_points': [r + 1 for r in rung_numbers] if rung_numbers else [0]
        }
        
        return analysis
    
    def _generate_insertion_hints(self, chunk: L5XChunk) -> List[str]:
        """Generate hints for where logic could be inserted relative to this chunk"""
        hints = []
        
        if chunk.chunk_type == L5XChunkType.LADDER_RUNG:
            hints.append(f"Insert after rung {chunk.location.rung_number}")
            if chunk.location.rung_number > 0:
                hints.append(f"Insert before rung {chunk.location.rung_number}")
        
        if chunk.chunk_type == L5XChunkType.ROUTINE:
            hints.append(f"Add rungs to routine {chunk.name}")
        
        # Add semantic hints based on content
        content_lower = chunk.content.lower()
        if 'start' in content_lower or 'enable' in content_lower:
            hints.append("Good location for initialization logic")
        if 'stop' in content_lower or 'disable' in content_lower:
            hints.append("Good location for shutdown logic")
        if 'alarm' in content_lower or 'fault' in content_lower:
            hints.append("Good location for safety/alarm logic")
        
        return hints
    
    def _calculate_complexity_score(self, chunks: List[L5XChunk]) -> float:
        """Calculate a complexity score for a set of chunks"""
        if not chunks:
            return 0.0
        
        total_content_length = sum(len(chunk.content) for chunk in chunks)
        total_dependencies = sum(len(chunk.dependencies) for chunk in chunks)
        rung_count = len([c for c in chunks if c.chunk_type == L5XChunkType.LADDER_RUNG])
        
        # Simple complexity calculation
        complexity = (total_content_length / 1000) + (total_dependencies * 0.5) + (rung_count * 0.1)
        return min(complexity, 10.0)  # Cap at 10
    
    def _text_search(self, query: str, limit: int, chunk_types: List[L5XChunkType] = None) -> List[L5XSearchResult]:
        """Enhanced fallback text-based search with fuzzy matching"""
        results = []
        query_lower = query.lower()
        
        for chunk in self.chunks_data:
            if chunk_types and chunk.chunk_type not in chunk_types:
                continue
            
            searchable = chunk.searchable_text.lower()
            name_lower = chunk.name.lower()
            desc_lower = chunk.description.lower() if chunk.description else ""
            
            # Multi-level scoring for better matching
            score = 0.0
            query_words = query_lower.split()
            
            # Exact phrase match (highest score)
            if query_lower in searchable:
                score += 2.0
            
            # Name contains query (high score)
            if query_lower in name_lower:
                score += 1.5
                
            # Description contains query
            if query_lower in desc_lower:
                score += 1.0
            
            # Individual word matching with partial support
            word_matches = 0
            for word in query_words:
                if len(word) >= 3:  # Only check words with 3+ characters
                    # Exact word match
                    if word in searchable:
                        word_matches += 1
                    # Partial word match (for technical terms)
                    elif any(word in search_word for search_word in searchable.split() if len(search_word) >= 4):
                        word_matches += 0.5
                        
            if word_matches > 0:
                score += word_matches / len(query_words)
            
            # Add small score for any match to ensure broad coverage
            if score > 0:
                result = L5XSearchResult(
                    chunk_id=chunk.id,
                    chunk_type=chunk.chunk_type,
                    name=chunk.name,
                    description=chunk.description,
                    score=score,
                    content=chunk.content,
                    location=chunk.location,
                    file_path=chunk.location.file_path,
                    insertion_hints=self._generate_insertion_hints(chunk)
                )
                results.append(result)
        
        # Sort by score and return top results
        results.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"Text search found {len(results)} results for query: {query}")
        return results[:limit]
    
    def _is_project_indexed(self, project_name: str) -> bool:
        """Check if project is already indexed"""
        self._load_metadata()
        return project_name in self.indexed_projects
    
    def _cache_exists(self) -> bool:
        """Check if cache files exist"""
        _ensure_faiss()
        return (self.data_cache.exists() and
                (not FAISS_AVAILABLE or self.index_cache.exists()))
    
    def _cache_is_recent(self, max_age_hours: int = 24) -> bool:
        """Check if cache is recent enough"""
        if not self.data_cache.exists():
            return False
        
        cache_age = time.time() - self.data_cache.stat().st_mtime
        return cache_age < (max_age_hours * 3600)
    
    def _save_to_cache(self):
        """Save vector database to cache files"""
        _ensure_faiss()
        try:
            # Save chunks data
            with open(self.data_cache, 'wb') as f:
                pickle.dump(self.chunks_data, f)

            if FAISS_AVAILABLE and self.index is not None:
                # Save FAISS index
                faiss.write_index(self.index, str(self.index_cache))
                
                # Save embeddings
                with open(self.embeddings_cache, 'wb') as f:
                    pickle.dump(self.embeddings, f)
            
            logger.info("Vector database cached successfully")
            
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _load_from_cache(self):
        """Load vector database from cache files"""
        _ensure_faiss()
        try:
            # Load chunks data
            with open(self.data_cache, 'rb') as f:
                self.chunks_data = pickle.load(f)
            self.invalidate_xref()

            if FAISS_AVAILABLE and self.index_cache.exists():
                # Load FAISS index
                self.index = faiss.read_index(str(self.index_cache))
                
                # Load embeddings
                if self.embeddings_cache.exists():
                    with open(self.embeddings_cache, 'rb') as f:
                        self.embeddings = pickle.load(f)
            
            # Initialize model for new searches
            self.initialize_model()
            
            logger.info(f"Loaded {len(self.chunks_data)} chunks from cache")
            
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            self.chunks_data = []
    
    def _save_metadata(self):
        """Save project indexing metadata"""
        try:
            with open(self.metadata_cache, 'w') as f:
                json.dump(self.indexed_projects, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def _load_metadata(self):
        """Load project indexing metadata"""
        try:
            if self.metadata_cache.exists():
                with open(self.metadata_cache, 'r') as f:
                    self.indexed_projects = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            self.indexed_projects = {}
