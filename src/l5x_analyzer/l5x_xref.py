#!/usr/bin/env python3
"""
L5X Tag Cross-Reference - exact-match symbol index

Every existing L5X search path (search_l5x_content, find_related_components,
find_related_tags) is FAISS + sentence-transformer semantic similarity. That
ranks results by meaning, which is the wrong tool for "list every rung that
references tag X" - similarity search can rank a genuinely relevant rung
below its score threshold and silently drop it. This module builds a plain
regex-based symbol index instead: no embeddings, guaranteed recall, answers
instantly. It is meant to complement semantic search, not replace it.

The approach - tokenizing NeutralText/Structured Text and classifying each
call as an instruction vs. a tag reference - is adapted from the symbol
extraction in nodeblue-ai/studio5000-mcp-server's parsers/xref.py (MIT
License, Copyright (c) 2026 Nodeblue). What's different here, and why:

- Source of data: nodeblue re-parses a single exported .L5X file per call.
  This module instead builds from the L5XChunk objects already produced by
  SDKPoweredL5XAnalyzer.parse_routine_l5x, so it covers ACD-sourced projects
  identically to L5X-sourced ones (index_acd_project never writes an L5X
  file to disk that could be re-parsed independently) and inherits
  project_name scoping for free.
- Instruction/tag distinction: nodeblue filters against a ~40-mnemonic
  hardcoded blacklist. This module instead detects a CALL structurally - in
  NeutralText/ST, an instruction or AOI invocation is always an identifier
  immediately followed by '(', and a tag operand never is - which needs no
  dictionary at all for the primary distinction, and sidesteps a real
  problem with using this project's parsed instruction documentation as a
  blacklist: 323 of its 577 v35 entries are glossary/acronym topics with an
  empty category (PV, IO, TIMER, AXIS, REG, HSC...) that are also extremely
  common real tag names (see plc_language.mnemonics for the full story).
  plc_language.instruction_mnemonics.reserved_mnemonics() (curated-only, no
  parsed documentation) is still used, but only as a secondary signal: to
  tell a CALL that's a known instruction apart from one that's an AOI
  instance (for aoi_calls reporting), and to filter ST keywords.
- Addressing: handles Logix bit addresses (Tag.3), array indices
  (Arr[Idx].Bit - plus indexing Idx itself as a separate read reference),
  and colon-qualified I/O and program-scoped tags (Local:1:I.Data,
  Program:Other.Tag), none of which nodeblue's regex preserves correctly.
  Two-dimensional array indices (Arr[1,2]) are not fully captured - a
  narrow, documented gap rather than a full expression parser.
- Read/write classification: derived from the parsed CALL's mnemonic and
  operand position (see _INSTRUCTION_ACCESS below) - nodeblue does not
  classify access at all.

Coverage is bounded by what SDKPoweredL5XAnalyzer.parse_routine_l5x actually
chunks: AOI internal logic and FBD/SFC routines are never indexed (see
skipped_chunks/aoi_calls on TagXrefIndex), and controller/program tag
*declarations* aren't indexed at all, so "declared but never referenced"
stays undecidable. Every caller-facing tool built on this module must
surface those gaps rather than let "no references found" read as "this tag
is definitely unused".
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .l5x_chunk import L5XChunk, L5XChunkType
from plc_language import instruction_mnemonics

# ---------------------------------------------------------------------------
# Tokenizing
# ---------------------------------------------------------------------------

# A Logix tag/member reference: an identifier, optionally followed by more
# ":segment" qualifiers (Local:1:I, Program:OtherTag), then any number of
# .member or [index] segments (Tag.3 - a bit address, member names are also
# allowed after a dot - or Arr[Idx].Bit).
_SYMBOL_RE = re.compile(
    r"""
    [A-Za-z_][A-Za-z0-9_]*                              # first segment
    (?: : (?: \d+ | [A-Za-z_][A-Za-z0-9_]* ) )*          # :N or :Name qualifiers
    (?: (?:\.(?:[A-Za-z_][A-Za-z0-9_]*|\d+))             # .member or .N (bit address)
      | (?:\[[A-Za-z0-9_]+\])                            # [index] (1-D only)
    )*
    """,
    re.VERBOSE,
)

# A bracketed array index that is itself an identifier (not a numeric
# literal) - e.g. the `Idx` in `Arr[Idx]`. Captured so it can be indexed as
# its own read reference even when the whole operand isn't a clean match
# (2-D indices, expressions, etc.).
_ARRAY_INDEX_IDENT_RE = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")

# A string literal, e.g. inside CONCAT('some text', Tag) - must not be
# indexed as a tag reference.
_STRING_LITERAL_RE = re.compile(r"'[^']*'")

# A CALL in NeutralText/ST: an identifier immediately followed by '(' - this
# is what distinguishes an instruction/AOI invocation from a bare tag
# reference, with no mnemonic list required for the primary distinction.
_CALL_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(')


@dataclass(frozen=True)
class TagReference:
    """One occurrence of a tag/member being referenced in indexed logic."""
    symbol: str                       # as written, e.g. "Motor_1.Running" or "Arr[Idx].Bit"
    base_tag: str                     # "Motor_1" / "Arr"
    access: str                       # "read" | "write" | "unknown"
    instruction: Optional[str]        # enclosing mnemonic, e.g. "OTE" - None for a bare reference
    operand_index: Optional[int]      # which operand position this was, 0-based
    program: Optional[str]
    routine: Optional[str]
    rung_number: Optional[int]        # RLL only
    line_number: Optional[int]        # ST only
    chunk_id: str
    xpath: str
    project_name: Optional[str]


@dataclass
class TagXrefIndex:
    """The built cross-reference for one project, or for 'all indexed
    projects' when project_scope is None."""
    project_scope: Optional[str]
    by_symbol: Dict[str, List[TagReference]] = field(default_factory=dict)
    # lowercased symbol -> real (case-preserved) keys in by_symbol. Logix is
    # case-insensitive but case-preserving, so `motor_1` and `Motor_1` must
    # resolve to the same entry without collapsing the stored spelling.
    _ci_alias: Dict[str, List[str]] = field(default_factory=dict)
    aoi_calls: Dict[str, List[str]] = field(default_factory=dict)   # CALL name -> routines it appears in
    skipped_chunks: Dict[str, int] = field(default_factory=dict)    # {'fbd': n, ...}
    chunk_count: int = 0
    reference_count: int = 0
    built_at: float = 0.0

    def _add(self, ref: TagReference) -> None:
        self.by_symbol.setdefault(ref.symbol, []).append(ref)
        aliases = self._ci_alias.setdefault(ref.symbol.lower(), [])
        if ref.symbol not in aliases:
            aliases.append(ref.symbol)
        self.reference_count += 1

    def _record_aoi_call(self, name: str, routine: Optional[str]) -> None:
        routines = self.aoi_calls.setdefault(name, [])
        if routine not in routines:
            routines.append(routine)

    def lookup(self, symbol: str, *, include_members: bool = True,
               access: Optional[str] = None) -> List[TagReference]:
        """Exact (case-insensitive) lookup. With include_members, also
        returns references to members/elements of `symbol` (e.g. asking for
        "Motor_1" also returns "Motor_1.Running", "Motor_1[0]", ...)."""
        results: List[TagReference] = []
        symbol_lower = symbol.lower()

        for real_key in self._ci_alias.get(symbol_lower, []):
            results.extend(self.by_symbol[real_key])

        if include_members:
            for key_lower, real_keys in self._ci_alias.items():
                if key_lower == symbol_lower:
                    continue
                if key_lower.startswith(symbol_lower + ".") or key_lower.startswith(symbol_lower + "["):
                    for real_key in real_keys:
                        results.extend(self.by_symbol[real_key])

        if access:
            results = [r for r in results if r.access == access]
        return results

    def search(self, pattern: str, *, regex: bool = True, limit: int = 50) -> Dict[str, List[TagReference]]:
        """Find symbols whose NAME matches `pattern`, grouped by symbol.
        Falls back to a literal substring match if `pattern` isn't valid
        regex, matching nodeblue's fallback behavior."""
        if regex:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                matcher = compiled.search
            except re.error:
                pattern_lower = pattern.lower()
                matcher = lambda s: pattern_lower in s.lower()
        else:
            pattern_lower = pattern.lower()
            matcher = lambda s: pattern_lower in s.lower()

        matched: Dict[str, List[TagReference]] = {}
        for symbol, refs in self.by_symbol.items():
            if matcher(symbol):
                matched[symbol] = refs
                if len(matched) >= limit:
                    break
        return matched


def _split_top_level_commas(operand_text: str) -> List[str]:
    """Split an operand list on top-level commas only - a nested call's own
    commas (e.g. the inner CONCAT in CONCAT(A, CONCAT(B, C))), or a 2-D
    array index's comma (Arr[1,2]), must not be treated as this call's
    operand separators."""
    parts = []
    depth = 0
    current = []
    for ch in operand_text:
        if ch in '([':
            depth += 1
            current.append(ch)
        elif ch in ')]':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    parts.append(''.join(current))
    return parts


def _find_matching_paren(text: str, open_idx: int) -> int:
    """Given the index of an opening '(' in text, find its matching ')'."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _mask_string_literals(text: str) -> str:
    """Blank out 'quoted text' (same length, so positions stay aligned) so
    it's never mistaken for a tag reference."""
    return _STRING_LITERAL_RE.sub(lambda m: ' ' * len(m.group()), text)


# Per-instruction operand access classification. Each entry is either:
#   'all_read'        - every operand is a read
#   ('write_at', i)    - operand at index i (negative allowed, e.g. -1 for
#                        last) is a write, every other operand is a read
# Anything not listed here is 'unknown' - honest, not guessed.
_INSTRUCTION_ACCESS: Dict[str, object] = {
    # Bit instructions
    'OTE': ('write_at', 0), 'OTL': ('write_at', 0), 'OTU': ('write_at', 0), 'CLR': ('write_at', 0),
    'XIC': 'all_read', 'XIO': 'all_read', 'ONS': 'all_read', 'OSR': 'all_read',
    'OSF': 'all_read', 'AFI': 'all_read', 'NOP': 'all_read',
    # Move/logical/math - last operand is the destination
    'MOV': ('write_at', -1), 'MVM': ('write_at', -1), 'COP': ('write_at', -1), 'CPS': ('write_at', -1),
    'SWPB': ('write_at', -1), 'BTD': ('write_at', -1), 'TOD': ('write_at', -1), 'FRD': ('write_at', -1),
    'DEG': ('write_at', -1), 'RAD': ('write_at', -1), 'ABS': ('write_at', -1), 'NEG': ('write_at', -1),
    'SQR': ('write_at', -1), 'SQRT': ('write_at', -1),
    'ADD': ('write_at', -1), 'SUB': ('write_at', -1), 'MUL': ('write_at', -1), 'DIV': ('write_at', -1),
    'MOD': ('write_at', -1), 'AND': ('write_at', -1), 'OR': ('write_at', -1), 'XOR': ('write_at', -1),
    'BAND': ('write_at', -1), 'BOR': ('write_at', -1), 'BXOR': ('write_at', -1),
    # Compare - all read
    'EQU': 'all_read', 'NEQ': 'all_read', 'LES': 'all_read', 'LEQ': 'all_read',
    'GRT': 'all_read', 'GEQ': 'all_read', 'CMP': 'all_read', 'LIM': 'all_read', 'MEQ': 'all_read',
    # Timer/Counter - operand 0 (the structure) is written
    'TON': ('write_at', 0), 'TOF': ('write_at', 0), 'RTO': ('write_at', 0),
    'CTU': ('write_at', 0), 'CTD': ('write_at', 0), 'RES': ('write_at', 0),
    # GSV/SSV
    'GSV': ('write_at', -1), 'SSV': ('write_at', -1),
}

# Instructions whose first operand is a routine/label name, not a tag at
# all - excluded from the symbol index entirely rather than classified with
# any access.
_NON_TAG_OPERAND_0 = {'JSR', 'SBR', 'JMP', 'LBL'}


def _find_unrecognized_calls(text: str, *, is_st: bool, mnemonics) -> Set[str]:
    """Names of CALLs in `text` that aren't a recognized built-in
    instruction - i.e. AOI/UDT instance invocations. Used only for the
    aoi_calls visibility report, kept separate from the main extraction pass
    so extract_from_neutral_text/extract_from_st_lines stay simple, pure
    functions of their own."""
    masked = _mask_string_literals(text)
    names: Set[str] = set()
    for call_match in _CALL_RE.finditer(masked):
        name = call_match.group(1)
        open_paren = call_match.end() - 1
        close_paren = _find_matching_paren(masked, open_paren)
        if close_paren == -1:
            continue
        name_upper = name.upper()
        if is_st and name_upper in mnemonics.st_keywords():
            continue
        if name_upper in _NON_TAG_OPERAND_0:
            continue
        if name_upper not in mnemonics.reserved_mnemonics():
            names.add(name_upper)
    return names


class L5XTagXref:
    """Builds and queries an exact-match TagXrefIndex from indexed L5XChunks."""

    def __init__(self, mnemonics=instruction_mnemonics):
        self._mnemonics = mnemonics

    def build(self, chunks: List[L5XChunk], project_scope: Optional[str] = None) -> TagXrefIndex:
        idx = TagXrefIndex(project_scope=project_scope)
        idx.chunk_count = len(chunks)

        for chunk in chunks:
            loc = chunk.location
            common = dict(
                program=loc.parent_program,
                routine=loc.parent_routine,
                chunk_id=chunk.id,
                xpath=loc.xpath,
                project_name=getattr(chunk, 'project_name', None),
            )

            if chunk.chunk_type is L5XChunkType.LADDER_RUNG:
                # chunk.content is already NeutralText - the <Text> CDATA
                # payload for this rung, nothing to unwrap.
                for ref in self.extract_from_neutral_text(chunk.content, rung_number=loc.rung_number, **common):
                    idx._add(ref)
                for name in _find_unrecognized_calls(chunk.content, is_st=False, mnemonics=self._mnemonics):
                    idx._record_aoi_call(name, loc.parent_routine)

            elif chunk.chunk_type is L5XChunkType.ROUTINE:
                routine_type = chunk.metadata.get('routine_type')
                if routine_type == 'RLL':
                    # This routine's rungs are already indexed individually
                    # as their own LADDER_RUNG chunks above - chunk.content
                    # here is ET.tostring() of the WHOLE routine element, so
                    # scanning it too would double-count every rung.
                    continue
                elif routine_type == 'ST':
                    lines = list(self._st_lines_from_routine_xml(chunk.content))
                    for ref in self.extract_from_st_lines(lines, **common):
                        idx._add(ref)
                    for _, line_text in lines:
                        for name in _find_unrecognized_calls(line_text, is_st=True, mnemonics=self._mnemonics):
                            idx._record_aoi_call(name, loc.parent_routine)
                else:
                    # FBD/SFC (or anything else) is not NeutralText/ST - don't
                    # guess at it, just report it was skipped so a caller
                    # never mistakes "not indexed" for "definitely no writers".
                    key = routine_type or 'unknown'
                    idx.skipped_chunks[key] = idx.skipped_chunks.get(key, 0) + 1

        idx.built_at = time.time()
        return idx

    def _st_lines_from_routine_xml(self, routine_xml: str) -> List[Tuple[Optional[int], str]]:
        """A ROUTINE chunk's content is ET.tostring() of the <Routine>
        element; pull out its STContent/Line children as (number, text)."""
        try:
            root = ET.fromstring(routine_xml)
        except ET.ParseError:
            return []
        lines = []
        for line_el in root.findall('.//STContent/Line'):
            number = line_el.get('Number')
            text = line_el.text or ''
            lines.append((int(number) if number is not None else None, text))
        return lines

    # -- extraction (pure functions of their input text) -----------------

    def extract_from_neutral_text(self, text: str, *, program: Optional[str] = None,
                                   routine: Optional[str] = None, rung_number: Optional[int] = None,
                                   chunk_id: str = '', xpath: str = '',
                                   project_name: Optional[str] = None) -> List[TagReference]:
        """Extract tag references from one rung's NeutralText."""
        return self._extract(text, is_st=False, rung_number=rung_number, line_number=None,
                              program=program, routine=routine, chunk_id=chunk_id,
                              xpath=xpath, project_name=project_name)

    def extract_from_st_lines(self, lines: List[Tuple[Optional[int], str]], *,
                               program: Optional[str] = None, routine: Optional[str] = None,
                               chunk_id: str = '', xpath: str = '',
                               project_name: Optional[str] = None) -> List[TagReference]:
        """Extract tag references from a Structured Text routine's lines,
        as (line_number, text) pairs (see _st_lines_from_routine_xml)."""
        refs: List[TagReference] = []
        for line_number, line_text in lines:
            refs.extend(self._extract(line_text, is_st=True, rung_number=None, line_number=line_number,
                                       program=program, routine=routine, chunk_id=chunk_id,
                                       xpath=xpath, project_name=project_name))
        return refs

    def _extract(self, text: str, *, is_st: bool, rung_number: Optional[int], line_number: Optional[int],
                 program: Optional[str], routine: Optional[str], chunk_id: str, xpath: str,
                 project_name: Optional[str]) -> List[TagReference]:
        if not text:
            return []

        masked = _mask_string_literals(text)
        refs: List[TagReference] = []
        # Positions already attributed to a CALL's name+operands, so the
        # trailing bare-reference pass doesn't re-scan them.
        consumed = [False] * len(masked)

        for call_match in _CALL_RE.finditer(masked):
            name = call_match.group(1)
            name_upper = name.upper()
            open_paren = call_match.end() - 1
            close_paren = _find_matching_paren(masked, open_paren)

            if close_paren == -1:
                # Unbalanced - not this module's job to flag (the ladder
                # syntax validator does that), but at least don't let the
                # bare mnemonic itself be picked up as a tag reference below.
                for i in range(call_match.start(), call_match.end()):
                    consumed[i] = True
                continue

            if is_st and name_upper in self._mnemonics.st_keywords():
                # IF (condition), WHILE (condition), etc. are not calls -
                # leave the "(condition)" text unconsumed so any tags inside
                # it are still picked up by the bare-reference pass below.
                continue

            for i in range(call_match.start(), close_paren + 1):
                consumed[i] = True

            if name_upper in _NON_TAG_OPERAND_0:
                # JSR/SBR/JMP/LBL - operand 0 is a routine/label name, not a
                # tag. Nothing here to index.
                continue

            operand_text = masked[open_paren + 1:close_paren]
            operands = _split_top_level_commas(operand_text) if operand_text.strip() else []
            access_rule = _INSTRUCTION_ACCESS.get(name_upper)

            for op_index, operand in enumerate(operands):
                access = 'unknown'
                if access_rule == 'all_read':
                    access = 'read'
                elif isinstance(access_rule, tuple) and access_rule[0] == 'write_at':
                    write_index = access_rule[1]
                    normalized = write_index if write_index >= 0 else len(operands) + write_index
                    access = 'write' if op_index == normalized else 'read'

                for symbol, base_tag in self._symbols_in_operand(operand):
                    refs.append(TagReference(
                        symbol=symbol, base_tag=base_tag, access=access,
                        instruction=name_upper, operand_index=op_index,
                        program=program, routine=routine,
                        rung_number=rung_number, line_number=line_number,
                        chunk_id=chunk_id, xpath=xpath, project_name=project_name,
                    ))

        # Bare references: anything left unconsumed that looks like a
        # symbol and isn't itself a CALL name / reserved keyword.
        for sym_match in _SYMBOL_RE.finditer(masked):
            start, end = sym_match.span()
            if any(consumed[start:end]):
                continue
            token = sym_match.group()
            if not token or token[0].isdigit():
                continue
            base = re.split(r'[.\[:]', token, 1)[0]
            base_upper = base.upper()
            if base_upper in _NON_TAG_OPERAND_0:
                continue
            if is_st and base_upper in self._mnemonics.st_keywords():
                continue
            refs.append(TagReference(
                symbol=token, base_tag=base, access='unknown', instruction=None,
                operand_index=None, program=program, routine=routine,
                rung_number=rung_number, line_number=line_number,
                chunk_id=chunk_id, xpath=xpath, project_name=project_name,
            ))

        return refs

    def _symbols_in_operand(self, operand: str):
        """Yield (symbol, base_tag) pairs found in one operand's text -
        normally exactly one (the operand itself), plus one more per
        array-index identifier found inside it (e.g. Arr[Idx] also yields
        Idx as its own reference)."""
        operand = operand.strip()
        if not operand:
            return

        match = _SYMBOL_RE.match(operand)
        if not match or match.group() != operand:
            # Not a clean single symbol (a numeric literal, an arithmetic
            # expression, a 2-D array index, ...) - still surface any
            # array-index identifiers inside it before giving up on the
            # operand as a whole.
            for idx_match in _ARRAY_INDEX_IDENT_RE.finditer(operand):
                yield idx_match.group(1), idx_match.group(1)
            return

        if operand[0].isdigit():
            return
        base = re.split(r'[.\[:]', operand, 1)[0]
        if base.upper() in _NON_TAG_OPERAND_0:
            return

        yield operand, base

        for idx_match in _ARRAY_INDEX_IDENT_RE.finditer(operand):
            index_ident = idx_match.group(1)
            if not index_ident[0].isdigit():
                yield index_ident, index_ident
