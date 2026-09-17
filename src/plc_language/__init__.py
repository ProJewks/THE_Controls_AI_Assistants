"""
plc_language - shared, dependency-free vocabulary for Studio 5000 instruction
mnemonics and Structured Text keywords.

This package exists so that both src/verification (the fast ladder-logic
validator) and src/l5x_analyzer (the L5X content indexer/cross-referencer)
can share one source of truth for "is this token a known instruction",
without either importing the other. src/mcp_server already imports
src/l5x_analyzer, and src/verification/__init__.py re-exports SDKVerifier, so
a shared vocabulary living inside either of those packages would create an
import cycle or drag in unrelated code. plc_language has no imports from
anywhere else in this project and is safe for any package to depend on.
"""

from .mnemonics import (
    CURATED_MNEMONICS,
    ST_KEYWORDS,
    InstructionMnemonicRegistry,
    instruction_mnemonics,
)

__all__ = [
    "CURATED_MNEMONICS",
    "ST_KEYWORDS",
    "InstructionMnemonicRegistry",
    "instruction_mnemonics",
]
