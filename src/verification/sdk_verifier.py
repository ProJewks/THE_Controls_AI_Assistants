"""
SDK Verifier - Fast Validation Only

This module provides fast, reliable ladder logic validation without 
SDK dependencies. Provides instant validation (0.001s) with no setup required.
"""

import asyncio
import re
import sys
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from plc_language import CURATED_MNEMONICS, instruction_mnemonics

# Back-compat alias: sdk_verifier_clean.py and verification/__init__.py both
# reference COMMON_INSTRUCTIONS by this name. The actual curated set now
# lives in plc_language.mnemonics so it can be shared with l5x_analyzer
# without either package importing the other (see src/plc_language/__init__.py).
COMMON_INSTRUCTIONS = CURATED_MNEMONICS

@dataclass
class VerificationError:
    """Represents a validation error"""
    code: str
    message: str
    severity: str = "error"
    line_number: Optional[int] = None
    position: Optional[int] = None

@dataclass  
class VerificationWarning:
    """Represents a validation warning"""
    code: str
    message: str
    line_number: Optional[int] = None
    position: Optional[int] = None

@dataclass
class VerificationResult:
    """Results of ladder logic verification"""
    success: bool
    errors: List[VerificationError]
    warnings: List[VerificationWarning]
    build_info: Dict[str, Any] 
    verification_time: float = 0.0
    sdk_available: bool = False

class SDKVerifier:
    """Fast ladder logic verifier without SDK dependencies"""
    
    def __init__(self, version: Optional[str] = None):
        """Initialize the fast verifier.

        Args:
            version: Optional default Studio 5000 doc version ('v35', 'v36',
                'v37', ...) used to widen the known-instruction check via
                plc_language.instruction_mnemonics.known_instructions(). Can
                be overridden per call via context['version']. Left as None,
                verification still works using CURATED_MNEMONICS plus
                whatever version(s) the server has registered - this keeps
                the module-level `sdk_verifier` singleton usable with zero
                arguments and no server handle, exactly as before.
        """
        self.sdk_available = False  # We don't use SDK anymore
        self.version = version

        # Default controller type for verification
        self.default_controller_type = "1756-L83E"
        self.default_major_revision = 35
        
    async def verify_ladder_logic(self, ladder_logic: str, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """
        Verify ladder logic using fast validation (reliable and instant)
        
        Args:
            ladder_logic: Ladder logic text to verify
            context: Optional context including:
                - 'controller_type': Controller type for validation
                - 'instructions_used': List of instructions used (optional)
                
        Returns:
            VerificationResult with success status and detailed error information
        """
        start_time = asyncio.get_event_loop().time()
        context = context or {}
        
        # Use fast validation (reliable, fast, always works)
        result = await self._fast_verify_ladder_logic(ladder_logic, context)
        
        # Set timing
        result.verification_time = asyncio.get_event_loop().time() - start_time
        return result
    
    async def verify_routine(self, routine_name: str, rungs: List[str], context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """
        Verify a complete routine with multiple rungs
        
        Args:
            routine_name: Name of the routine to verify
            rungs: List of rung logic strings
            context: Verification context
            
        Returns:
            Combined verification results for all rungs
        """
        all_errors = []
        all_warnings = []
        
        for i, rung in enumerate(rungs):
            rung_result = await self.verify_ladder_logic(rung, context)
            
            # Add rung number to errors and warnings
            for error in rung_result.errors:
                error.line_number = i
                all_errors.append(error)
            
            for warning in rung_result.warnings:
                warning.line_number = i  
                all_warnings.append(warning)
        
        return VerificationResult(
            success=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
            build_info={
                'verification_method': 'fast_routine_validation',
                'routine_name': routine_name,
                'rung_count': len(rungs),
                'total_errors': len(all_errors),
                'total_warnings': len(all_warnings)
            }
        )

    async def _fast_verify_ladder_logic(self, ladder_logic: str, context: Dict[str, Any]) -> VerificationResult:
        """
        Fast validation using syntax checks and instruction validation
        
        This method provides instant validation without SDK dependencies:
        - Syntax validation (balanced parentheses, proper structure)
        - Instruction validation (against known Studio 5000 instructions)
        - Basic logic structure checks
        - Performance: 0.001-0.020 seconds
        
        Args:
            ladder_logic: Ladder logic code to validate
            context: Validation context
            
        Returns:
            VerificationResult with validation status
        """
        errors = []
        warnings = []
        
        if not ladder_logic or not ladder_logic.strip():
            errors.append(VerificationError(
                code="EMPTY_LOGIC",
                message="Ladder logic is empty"
            ))
            return VerificationResult(
                success=False, 
                errors=errors,
                warnings=warnings,
                build_info={'verification_method': 'fast_validation'}
            )
        
        # 'version' lets a caller widen the known-instruction check to a
        # specific Rockwell doc version's parsed index (see
        # plc_language.instruction_mnemonics.known_instructions). Falls back
        # to this verifier's own default, which is None for the bare
        # module-level singleton - known_instructions() then unions
        # CURATED_MNEMONICS with every version the server has registered.
        version = (context or {}).get('version', self.version)

        # Split into rungs for individual validation
        rungs = [rung.strip() for rung in ladder_logic.split(';') if rung.strip()]

        for rung_idx, rung in enumerate(rungs):
            # 1. Syntax validation
            syntax_errors = self._validate_ladder_syntax(rung, rung_idx)
            errors.extend(syntax_errors)

            # 2. Instruction validation - unrecognized names are warnings, not
            # errors (see _validate_instructions_fast docstring for why).
            instruction_warnings = self._validate_instructions_fast(rung, rung_idx, version)
            warnings.extend(instruction_warnings)

            # 3. Basic structure validation
            structure_warnings = self._validate_basic_structure(rung, rung_idx)
            warnings.extend(structure_warnings)
        
        # 4. Overall logic validation
        overall_errors = self._validate_overall_logic(ladder_logic)
        errors.extend(overall_errors)
        
        return VerificationResult(
            success=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            build_info={
                'verification_method': 'fast_validation',
                'rung_count': len(rungs),
                'validation_checks': ['syntax', 'instructions', 'structure'],
                'total_errors': len(errors),
                'total_warnings': len(warnings)
            }
        )

    def _validate_ladder_syntax(self, rung: str, rung_number: int) -> List[VerificationError]:
        """Validate basic ladder logic syntax"""
        errors = []

        # Check balanced parentheses
        open_parens = rung.count('(')
        close_parens = rung.count(')')

        if open_parens != close_parens:
            errors.append(VerificationError(
                code="UNBALANCED_PARENTHESES",
                message=f"Unbalanced parentheses in rung {rung_number}: {open_parens} open, {close_parens} close",
                line_number=rung_number
            ))

        # Check for empty instructions (consecutive parentheses)
        if '()' in rung:
            errors.append(VerificationError(
                code="EMPTY_INSTRUCTION",
                message=f"Empty instruction parameters in rung {rung_number}",
                line_number=rung_number
            ))

        # Check for proper instruction format
        if rung and not re.search(r'[A-Z]{2,}', rung):
            errors.append(VerificationError(
                code="NO_INSTRUCTIONS",
                message=f"No valid instructions found in rung {rung_number}",
                line_number=rung_number
            ))

        errors.extend(self._validate_branch_brackets(rung, rung_number))

        return errors

    def _validate_branch_brackets(self, rung: str, rung_number: int) -> List[VerificationError]:
        """Validate '[...]' parallel-branch constructs in RLL neutral text.

        A '[...]' in RLL text represents a set of parallel (OR'd) branches
        separated by top-level commas - e.g. '[XIC(A) ,XIC(B)]'. Two defect
        classes this specifically catches, neither of which was previously
        detected anywhere in this validator (both found the hard way, via a
        real Studio 5000 import rejection on logic that had passed this
        validator with zero errors):

        1. Unbalanced '[' / ']' - never checked before; only '(' / ')' was.
        2. A bracket with no top-level comma, e.g. '[GEQ(State,30) LEQ(State,40)]'.
           This is meaningless RLL syntax (a bracket exists to hold
           comma-separated parallel branches; a single branch is just a
           plain instruction series and needs no brackets at all) and
           Studio 5000's importer rejects it outright with a generic
           "Syntax error found while scanning import file" pointing at the
           rung - it is NOT caught by the open/close bracket count, since
           the brackets themselves are perfectly balanced.

        Commas inside an instruction's own parameter list (e.g. the '0' and
        '1' inside 'EQU(CommandPosition,0)') must not be mistaken for a
        branch-separator comma - this method tracks '(' / ')' nesting
        alongside '[' / ']' nesting so only a comma that appears directly
        inside a bracket (not inside a deeper paren) counts as a branch
        separator. A '[' is treated as an array index (exempt from the
        single-branch check) when the immediately preceding character is
        part of a tag name (alphanumeric, '_', or a closing ']' for chained
        indexing) rather than the start of a branch expression.
        """
        errors = []
        stack = []  # each entry: {'kind': '[' or '(', 'start': idx, 'has_comma': bool, 'is_array': bool}

        for idx, ch in enumerate(rung):
            if ch == '[':
                is_array = idx > 0 and (rung[idx - 1].isalnum() or rung[idx - 1] in ('_', ']'))
                stack.append({'kind': '[', 'start': idx, 'has_comma': False, 'is_array': is_array})
            elif ch == '(':
                stack.append({'kind': '(', 'start': idx, 'has_comma': False, 'is_array': False})
            elif ch == ',':
                if stack:
                    stack[-1]['has_comma'] = True
            elif ch == ')':
                if stack and stack[-1]['kind'] == '(':
                    stack.pop()
                elif stack:
                    errors.append(VerificationError(
                        code="UNBALANCED_BRACKET",
                        message=f"Unexpected ')' in rung {rung_number} at position {idx} while inside a '[' branch group",
                        line_number=rung_number,
                        position=idx
                    ))
            elif ch == ']':
                if stack and stack[-1]['kind'] == '[':
                    top = stack.pop()
                    if not top['has_comma'] and not top['is_array']:
                        snippet = rung[top['start']:idx + 1]
                        errors.append(VerificationError(
                            code="SINGLE_BRANCH_BRACKET",
                            message=(
                                f"Rung {rung_number}: '[...]' with no top-level comma - "
                                f"a bracket must hold at least two comma-separated branches "
                                f"or it isn't valid RLL syntax (Studio 5000 will reject this on "
                                f"import). Either add a second branch or remove the brackets "
                                f"entirely: {snippet}"
                            ),
                            line_number=rung_number,
                            position=top['start']
                        ))
                elif stack:
                    errors.append(VerificationError(
                        code="UNBALANCED_BRACKET",
                        message=f"Unexpected ']' in rung {rung_number} at position {idx} while inside a '(' parameter list",
                        line_number=rung_number,
                        position=idx
                    ))
                else:
                    errors.append(VerificationError(
                        code="UNBALANCED_BRACKET",
                        message=f"Unmatched ']' in rung {rung_number} at position {idx} - no corresponding '['",
                        line_number=rung_number,
                        position=idx
                    ))

        unclosed = [s for s in stack if s['kind'] == '[']
        if unclosed:
            errors.append(VerificationError(
                code="UNBALANCED_BRACKET",
                message=f"Rung {rung_number} has {len(unclosed)} unclosed '[' branch group(s) starting at position(s) {[s['start'] for s in unclosed]}",
                line_number=rung_number
            ))

        return errors

    def _validate_instructions_fast(self, rung: str, rung_number: int,
                                     version: Optional[str] = None) -> List[VerificationWarning]:
        """Check instruction names against the known instruction set.

        This is a warning, not an error: the extraction regex matches ANY
        capitalized identifier followed by '(', which also matches every
        AOI and UDT-instance call (e.g. FB_MDR_AI2(...)) - names that are
        never going to appear in any instruction list because they're
        project-specific, not Studio 5000 built-ins. Hard-failing validation
        on those would reject legitimate AOI-heavy ladder logic outright.
        Reporting them as warnings keeps genuine typos visible without
        blocking real logic that just happens to call an AOI this validator
        has never heard of.
        """
        warnings = []

        # Extract all instruction names using regex
        # Pattern matches: INSTRUCTION_NAME(parameters)
        instruction_pattern = r'\b([A-Z][A-Z0-9_]*)\s*\('
        instructions_found = re.findall(instruction_pattern, rung)

        for instruction in instructions_found:
            if not instruction_mnemonics.is_instruction(instruction, version):
                warnings.append(VerificationWarning(
                    code="UNKNOWN_INSTRUCTION",
                    message=f"'{instruction}' is not a recognized Studio 5000 instruction - "
                            f"this is expected for AOI/UDT instance calls, but flag it if it "
                            f"was meant to be a built-in instruction.",
                    line_number=rung_number
                ))

        return warnings

    def _validate_basic_structure(self, rung: str, rung_number: int) -> List[VerificationWarning]:
        """Validate basic ladder logic structure and patterns"""
        warnings = []
        
        # Check for common patterns
        if 'XIC(' in rung and 'OTE(' not in rung and 'OTL(' not in rung and 'OTU(' not in rung:
            warnings.append(VerificationWarning(
                code="INPUT_ONLY",
                message=f"Rung {rung_number} has inputs but no outputs",
                line_number=rung_number
            ))
        
        # Check for very long rungs (might be hard to read)
        if len(rung) > 200:
            warnings.append(VerificationWarning(
                code="LONG_RUNG",
                message=f"Rung {rung_number} is very long ({len(rung)} characters) - consider breaking into multiple rungs",
                line_number=rung_number
            ))
        
        return warnings

    def _validate_overall_logic(self, ladder_logic: str) -> List[VerificationError]:
        """Validate overall ladder logic structure"""
        errors = []
        
        # Check for proper rung termination
        if ladder_logic.strip() and not ladder_logic.strip().endswith(';'):
            errors.append(VerificationError(
                code="MISSING_TERMINATOR",
                message="Ladder logic should end with semicolon (;)"
            ))
        
        return errors

# Global instance for easy access
sdk_verifier = SDKVerifier()
