"""
Instruction mnemonic vocabulary, shared between the ladder-logic validator
(src/verification/sdk_verifier.py) and the L5X content indexer
(src/l5x_analyzer). See the package docstring in __init__.py for why this
lives in its own leaf package.

Two accessors, deliberately not one:

- known_instructions(version) - CURATED_MNEMONICS unioned with every
  instruction name Studio5000Parser has parsed out of the real Rockwell help
  files for the requested version(s) (or all registered versions, if none is
  given). This is meant to be permissive: a superset here only makes the
  *validator* accept more real instructions it didn't know about before
  (e.g. ALMD, MAOC, DCSTL), at the cost of also accepting a handful of
  glossary/acronym topics as if they were instructions. That's a good trade
  for a validator, whose job is "don't reject real logic."

- reserved_mnemonics() - CURATED_MNEMONICS only. This is never fed by the
  parsed documentation, on purpose. Direct inspection of
  src/mcp_server/instruction_index_cache_v35.json found 323 of its 577
  entries have an *empty* category - they are glossary/acronym topics, not
  instructions, and include names like PV, IO, TIMER, AXIS, REG and HSC that
  are extremely common real Studio 5000 tag/member names. Unioning those into
  anything that decides "is this token a tag reference" would silently
  delete real tag references from a cross-reference index. reserved_mnemonics
  is the accessor for that kind of consumer.

Neither accessor requires a server handle: instead of a consumer reaching
out for the parsed documentation, the MCP server *pushes* into this
registry once, at startup, via register_documented(). This keeps
SDKVerifier's no-argument, import-time singleton (src/verification/
sdk_verifier.py) working exactly as it does today, and keeps any future
consumer in src/l5x_analyzer equally decoupled from src/mcp_server.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, Optional

# Moved verbatim from the old src/verification/sdk_verifier.COMMON_INSTRUCTIONS.
# This is the floor: every mnemonic here was placed by hand, several of them
# (RES, DTOS, STOD) after a real false-positive UNKNOWN_INSTRUCTION rejection
# on real ladder logic. It must never shrink as a side effect of consulting
# the parsed documentation, since the documentation is neither a superset nor
# a trustworthy substitute for it (see module docstring above, and
# known_instructions()'s docstring for the specific counterexamples).
CURATED_MNEMONICS: FrozenSet[str] = frozenset({
    # Basic Instructions
    'XIC', 'XIO', 'OTE', 'OTL', 'OTU', 'ONS', 'OSR', 'OSF',

    # Timer Instructions
    'TON', 'TOF', 'RTO',

    # Counter Instructions
    'CTU', 'CTD', 'CTC',

    # Math Instructions
    'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'SQR', 'SQRT',
    'NEG', 'ABS', 'MIN', 'MAX', 'LIM', 'LIMIT', 'MUX',

    # Comparison Instructions
    'EQU', 'NEQ', 'LES', 'LEQ', 'GRT', 'GEQ', 'MEQ',
    # IEC 61131/PLCopen-style renames Rockwell's Studio 5000 v36+ online help
    # uses for the instructions above (EQU->EQ, NEQ->NE, LES->LT, LEQ->LE,
    # GRT->GT, GEQ->GE). Confirmed as a real, not just documentation-only,
    # rename: re-exporting THD_LG_CP2's SafetyProgram after the V35->V37
    # upgrade turned the same rung's GRT(...) into GT(...) verbatim. Both
    # spellings must stay accepted since older reference assets (Breakpack,
    # InboundSorter, etc.) still use the old ones.
    'EQ', 'NE', 'LT', 'LE', 'GT', 'GE',

    # Logical Instructions
    'AND', 'OR', 'XOR', 'NOT', 'BAND', 'BOR', 'BXOR',

    # Move Instructions
    'MOV', 'MVM', 'SWPB', 'CLR',
    'MOVE',  # v36+ rename of MOV - see comparison-instruction note above

    # Convert Instructions
    'TOD', 'FRD', 'DEG', 'RAD',
    'TO_BCD', 'BCD_TO',  # v36+ renames of TOD/FRD - see comparison-instruction note above
    'ACS', 'ASN', 'ATN', 'ACOS', 'ASIN', 'ATAN',  # ACS/ASN/ATN and their v36+ renames
    'TRN', 'TRUNC', 'XPY', 'EXPT',  # TRN/XPY and their v36+ renames

    # Process/Drives Instructions (new in v37)
    'D2SD', 'D3SD',

    # File/Array Instructions
    'COP', 'CPS', 'FLL', 'AVE', 'SRT', 'STD',
    'FFL', 'FFU', 'LFL', 'LFU', 'FAL', 'FSC', 'BSL', 'BSR',

    # ASCII String Instructions
    'FIND', 'MID', 'CONCAT', 'INSERT', 'DELETE',

    # ASCII Conversion Instructions
    'DTOS', 'STOD',

    # Timer/Counter reset (Timer and Counter Instructions category)
    'RES',

    # Program Control
    'JMP', 'LBL', 'JSR', 'RET', 'SBR', 'FOR', 'BRK',
    'MCR', 'END', 'TND', 'UID', 'UIE', 'AFI', 'NOP',

    # System Instructions
    'GSV', 'SSV', 'IOT', 'MSG', 'PID', 'PIDE',

    # Advanced Instructions
    'ALMA', 'ALMD', 'BTDT',
    'DEDT', 'DERV', 'HMIBC', 'HPF', 'INTG', 'LPF',
    'MAAT', 'MAFR', 'MAHD', 'MAHO', 'MAOC', 'MAPC',
    'MAST', 'MATC', 'MAXC', 'MDAC', 'MDCC', 'MDOC',
    'MDSF', 'MRHD', 'MRAT', 'MRCC', 'MRCS',
    'MRST', 'MSET', 'MTLF', 'MTTP', 'MVMT', 'PATT',
    'PCMD', 'PRNP', 'RESD', 'RLLK', 'RMPD', 'RMPS',
    'SCRV', 'SEL', 'SIZE', 'SMAT', 'SMOC', 'STOS',
    'TONR', 'TOFR', 'UPDN',
})

# Structured Text control-flow/type keywords. These have no trailing '(' the
# way an instruction or AOI call does, so they need their own list rather
# than being confused with either mnemonic set.
ST_KEYWORDS: FrozenSet[str] = frozenset({
    'IF', 'THEN', 'ELSE', 'ELSIF', 'END_IF',
    'FOR', 'TO', 'BY', 'DO', 'END_FOR',
    'WHILE', 'END_WHILE', 'REPEAT', 'UNTIL', 'END_REPEAT',
    'CASE', 'OF', 'END_CASE',
    'RETURN', 'EXIT',
    'AND', 'OR', 'XOR', 'NOT', 'MOD',
    'TRUE', 'FALSE',
    'BOOL', 'SINT', 'INT', 'DINT', 'LINT', 'REAL', 'STRING',
})


class InstructionMnemonicRegistry:
    """Holds CURATED_MNEMONICS plus whatever documented instruction names the
    MCP server has registered from parsed Rockwell help files, per version."""

    def __init__(self) -> None:
        self._documented: Dict[str, FrozenSet[str]] = {}

    def register_documented(self, version: str, names: Iterable[str]) -> None:
        """Called once by the server (studio5000_mcp_server.py) after it
        finishes parsing a version's instruction index. names must already
        be uppercase mnemonics, matching how Studio5000Parser stores them."""
        self._documented[version] = frozenset(n.upper() for n in names)

    def known_instructions(self, version: Optional[str] = None) -> FrozenSet[str]:
        """CURATED_MNEMONICS unioned with the documented names for `version`
        (or every registered version, if version is None). Permissive by
        design - see module docstring. Verified counterexamples for why this
        must stay a union and never a replacement of CURATED_MNEMONICS: on
        v35, get_instruction('COP') and get_instruction('JMP') both return
        None even though COP and JMP are real, common instructions; on v37,
        JSR/SBR/DTOS are similarly absent from the parsed index."""
        if version is not None:
            documented = self._documented.get(version, frozenset())
        elif self._documented:
            documented = frozenset().union(*self._documented.values())
        else:
            documented = frozenset()
        return CURATED_MNEMONICS | documented

    def reserved_mnemonics(self) -> FrozenSet[str]:
        """CURATED_MNEMONICS only - never the documented/parsed set. See
        module docstring: 323 of 577 v35 doc entries have an empty category
        and are glossary topics (PV, IO, TIMER, AXIS, REG, HSC...) that are
        also common real tag names. A consumer deciding "is this token a tag
        or an instruction" must not treat those as reserved words."""
        return CURATED_MNEMONICS

    def st_keywords(self) -> FrozenSet[str]:
        return ST_KEYWORDS

    def is_instruction(self, token: str, version: Optional[str] = None) -> bool:
        return token.upper() in self.known_instructions(version)


# Module-level singleton, mirroring the existing `sdk_verifier = SDKVerifier()`
# pattern in src/verification/sdk_verifier.py. Safe to import and use before
# register_documented() is ever called - it just behaves as CURATED_MNEMONICS
# alone until the server pushes documented names in.
instruction_mnemonics = InstructionMnemonicRegistry()
