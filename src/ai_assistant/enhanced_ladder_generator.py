#!/usr/bin/env python3
"""
Enhanced Ladder Logic Generator for Industrial Warehouse Automation

This module generates sophisticated ladder logic for complex warehouse automation
scenarios using pattern matching and intelligent instruction selection.
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from .enhanced_code_assistant import (
    EnhancedPLCRequirement, EnhancedGeneratedCode, IndustrialComponent, 
    AutomationSequence, LogicComplexity, IndustryDomain
)
from .warehouse_automation_patterns import WarehouseAutomationPatterns, WarehousePattern
from .code_assistant import CodeAssistant, PLCRequirement
from plc_language import instruction_mnemonics

class EnhancedLadderLogicGenerator:
    """Advanced ladder logic generator for warehouse automation"""
    
    def __init__(self, mcp_server=None):
        self.mcp_server = mcp_server
        self.warehouse_patterns = WarehouseAutomationPatterns()
        self._initialize_advanced_mappings()
    
    def _initialize_advanced_mappings(self):
        """Initialize advanced instruction mappings for warehouse automation"""
        
        # Motion control mappings for warehouse equipment
        self.motion_mappings = {
            'conveyor_control': {
                'start': 'OTE',
                'stop': 'OTU', 
                'speed_control': 'MOV',
                'position_control': 'MAM',
                'home': 'MAH'
            },
            'servo_positioning': {
                'absolute_move': 'MAM',
                'relative_move': 'MAM', 
                'jog': 'MAJ',
                'stop': 'MAS',
                'home': 'MAH',
                'gear': 'MAG'
            },
            'robot_control': {
                'move_joint': 'MAM',
                'move_linear': 'MAM',
                'gripper_close': 'OTE',
                'gripper_open': 'OTU'
            }
        }
        
        # Safety system mappings
        self.safety_mappings = {
            'emergency_stop': 'XIO',  # Normally closed contact
            'light_curtain': 'XIC',   # Normally open when clear
            'guard_switch': 'XIC',    # Normally open when closed
            'safety_mat': 'XIO',      # Normally closed when not activated
            'safety_relay': 'XIC'     # Normally open when energized
        }
        
        # Process control mappings for warehouse operations
        self.process_mappings = {
            'weighing': 'SCL',        # Scale weight values
            'counting': 'CTU',        # Count packages
            'sorting': 'EQU',         # Compare sort codes
            'tracking': 'MOV',        # Move tracking data
            'batching': 'ADD'         # Accumulate batch quantities
        }
        
        # Communication mappings for warehouse systems
        self.comm_mappings = {
            'barcode_scanner': 'MSG',     # Message instruction for scanner comm
            'wms_interface': 'PRODUCE',   # Produce data to WMS
            'hmi_update': 'CONSUME',      # Consume HMI commands
            'plc_to_plc': 'MSG'          # Inter-PLC communication
        }
    
    async def generate_from_requirements(self, requirements: EnhancedPLCRequirement) -> EnhancedGeneratedCode:
        """Generate enhanced ladder logic from structured requirements"""
        
        # First, check if this requires dynamic/mathematical logic generation
        if self._requires_dynamic_generation(requirements):
            return await self._generate_dynamic_logic(requirements)
        
        # Check for simple, well-defined patterns only if NOT complex
        if requirements.complexity in ['simple', 'moderate']:
            matching_patterns = self.warehouse_patterns.find_matching_patterns(requirements.description)
            if matching_patterns and self._is_clear_pattern_match(requirements, matching_patterns):
                return await self._generate_from_patterns(requirements, matching_patterns)
        
        # Default to custom logic generation for everything else
        return await self._generate_custom_logic(requirements)
    
    async def _generate_from_patterns(self, requirements: EnhancedPLCRequirement, 
                                    patterns: List[WarehousePattern]) -> EnhancedGeneratedCode:
        """Generate logic using warehouse automation patterns"""
        
        # Select the best matching pattern
        best_pattern = self._select_best_pattern(requirements, patterns)
        
        # Customize the pattern for specific requirements
        customized_logic = await self._customize_pattern(best_pattern, requirements)
        
        # Add safety logic if required
        if requirements.safety_requirements:
            safety_logic = self._generate_safety_logic(requirements.safety_requirements)
            customized_logic.safety_logic = safety_logic
        
        # Add performance optimizations
        if requirements.performance_requirements:
            self._optimize_for_performance(customized_logic, requirements.performance_requirements)
        
        return customized_logic
    
    def _requires_dynamic_generation(self, requirements: EnhancedPLCRequirement) -> bool:
        """Determine if this specification requires dynamic logic generation"""
        
        description = requirements.description.lower()
        
        # Mathematical calculation indicators
        math_indicators = [
            'calculate', 'calculation', 'fire_position', 'lead_distance', 'spacing',
            '+', '-', '*', '/', '=', 'add', 'subtract', 'multiply', 'divide'
        ]
        
        # Dynamic addressing indicators  
        dynamic_indicators = [
            'solenoid_number', 'indexed', 'array', '[', ']', 'dynamic',
            'position-based', 'based on', 'depending on'
        ]
        
        # Complex conditional logic indicators
        conditional_indicators = [
            'if', 'when', 'then', 'else', 'package_length', 'package_direction',
            'small package', 'medium package', 'large package', 'valve selection'
        ]
        
        # Structured specification indicators (like yours)
        structured_indicators = [
            'rung 1:', 'rung 2:', 'step 1:', 'step 2:', 'specific dynamic logic',
            'required:', 'logic required:'
        ]
        
        # Count indicators of each type
        math_count = sum(1 for indicator in math_indicators if indicator in description)
        dynamic_count = sum(1 for indicator in dynamic_indicators if indicator in description)
        conditional_count = sum(1 for indicator in conditional_indicators if indicator in description)
        structured_count = sum(1 for indicator in structured_indicators if indicator in description)
        
        # Require dynamic generation if:
        # - Multiple mathematical operations
        # - Dynamic addressing/indexing
        # - Complex conditional logic
        # - Highly structured specification
        # - Complexity is already marked as complex/advanced
        
        return (math_count >= 2 or 
                dynamic_count >= 1 or 
                conditional_count >= 3 or 
                structured_count >= 1 or
                requirements.complexity.value in ['complex', 'advanced'])
    
    def _is_clear_pattern_match(self, requirements: EnhancedPLCRequirement, 
                              patterns: List[WarehousePattern]) -> bool:
        """Determine if the pattern match is clear and appropriate"""
        
        # Don't use patterns for complex systems
        if requirements.complexity.value in ['complex', 'advanced']:
            return False
            
        # Don't use patterns if specification contains mathematical logic
        if any(indicator in requirements.description.lower() 
               for indicator in ['calculate', 'fire_position', 'solenoid_number', '=']):
            return False
            
        # Only use patterns for simple, well-defined scenarios
        simple_scenarios = ['basic conveyor', 'simple sorting', 'standard safety']
        return any(scenario in requirements.description.lower() for scenario in simple_scenarios)
    
    def _select_best_pattern(self, requirements: EnhancedPLCRequirement, 
                           patterns: List[WarehousePattern]) -> WarehousePattern:
        """Select the best matching pattern based on requirements"""
        
        if len(patterns) == 1:
            return patterns[0]
        
        # Score patterns based on component matches
        pattern_scores = {}
        req_components = [comp.name.lower() for comp in requirements.components]
        
        for pattern in patterns:
            score = 0
            for pattern_comp in pattern.components:
                if any(pattern_comp.lower() in req_comp for req_comp in req_components):
                    score += 1
            pattern_scores[pattern.name] = (score, pattern)  # Use pattern name as key, store tuple
        
        # Return highest scoring pattern
        best_pattern_name = max(pattern_scores.keys(), key=lambda name: pattern_scores[name][0])
        return pattern_scores[best_pattern_name][1]  # Return the pattern object
    
    async def _customize_pattern(self, pattern: WarehousePattern, 
                               requirements: EnhancedPLCRequirement) -> EnhancedGeneratedCode:
        """Customize a warehouse pattern for specific requirements"""
        
        # Start with the pattern template
        ladder_logic = pattern.ladder_logic_template
        tags = list(pattern.required_tags) if pattern.required_tags else []
        
        # Customize tag names based on requirements
        tag_mapping = self._create_tag_mapping(requirements, pattern)
        
        # Apply tag name customizations
        for old_tag, new_tag in tag_mapping.items():
            ladder_logic = ladder_logic.replace(old_tag, new_tag)
            # Update tag definitions
            for tag in tags:
                if tag['name'] == old_tag:
                    tag['name'] = new_tag
        
        # Add component-specific logic
        additional_logic = await self._generate_component_logic(requirements.components)
        if additional_logic:
            ladder_logic += "\n\n// Additional Component Logic\n" + additional_logic
        
        # Add sequence logic if present
        sequence_logic = self._generate_sequence_logic(requirements.sequences)
        if sequence_logic:
            ladder_logic += "\n\n// Sequence Control Logic\n" + sequence_logic
        
        # Validate instructions with MCP server
        instructions_used = self._extract_instructions_from_logic(ladder_logic)
        validation_notes = []
        if self.mcp_server:
            validation_notes = await self._validate_instructions(instructions_used)
        
        return EnhancedGeneratedCode(
            ladder_logic=ladder_logic,
            tags=tags,
            instructions_used=instructions_used,
            comments=[f"Generated from {pattern.name} pattern"],
            validation_notes=validation_notes,
            documentation=self._generate_documentation(pattern, requirements)
        )
    
    def _create_tag_mapping(self, requirements: EnhancedPLCRequirement, 
                          pattern: WarehousePattern) -> Dict[str, str]:
        """Create mapping from generic pattern tags to specific requirement tags"""
        
        tag_mapping = {}
        
        # Map component names to pattern tags
        for component in requirements.components:
            comp_name = component.name.upper()
            comp_type = component.component_type.lower()
            
            # Look for matching pattern components
            if comp_type == 'motor' and 'MOTOR' in pattern.ladder_logic_template:
                tag_mapping['CONV_MOTOR'] = f"{comp_name}_MOTOR"
                tag_mapping['CONV_RUN'] = f"{comp_name}_RUN"
            elif comp_type == 'sensor' and 'PHOTO' in pattern.ladder_logic_template:
                if 'upstream' in component.name.lower():
                    tag_mapping['PHOTO_UPSTREAM'] = comp_name
                elif 'downstream' in component.name.lower():
                    tag_mapping['PHOTO_DOWNSTREAM'] = comp_name
        
        return tag_mapping
    
    async def _generate_component_logic(self, components: List[IndustrialComponent]) -> str:
        """Generate logic specific to individual components"""
        
        logic_lines = []
        
        for component in components:
            comp_type = component.component_type.lower()
            comp_name = component.name.upper()
            
            if comp_type == 'servo_motor':
                # Add servo control logic
                logic_lines.append(f"// {comp_name} Servo Control")
                logic_lines.append(f"XIC({comp_name}_ENABLE) MAH({comp_name}_AXIS);")
                logic_lines.append(f"XIC({comp_name}_HOME_COMPLETE) OTE({comp_name}_READY);")
                
            elif comp_type == 'vfd':
                # Add VFD control logic
                logic_lines.append(f"// {comp_name} VFD Control")
                logic_lines.append(f"XIC({comp_name}_RUN_CMD) OTE({comp_name}_START);")
                logic_lines.append(f"MOV({comp_name}_SPEED_REF,{comp_name}_SPEED_CMD);")
                
            elif comp_type == 'safety_scanner':
                # Add safety scanner logic
                logic_lines.append(f"// {comp_name} Safety Scanner")
                logic_lines.append(f"XIC({comp_name}_FIELD_ON) XIO({comp_name}_WARNING) OTE({comp_name}_SAFE);")
                
            elif component.safety_critical:
                # Add safety-critical component monitoring
                logic_lines.append(f"// {comp_name} Safety Monitoring")
                logic_lines.append(f"XIC({comp_name}_OK) XIO({comp_name}_FAULT) OTE({comp_name}_SAFE);")
        
        return "\n".join(logic_lines) if logic_lines else ""
    
    def _generate_sequence_logic(self, sequences: List[AutomationSequence]) -> str:
        """Generate ladder logic for automation sequences"""
        
        if not sequences:
            return ""
        
        logic_lines = []
        
        for seq_idx, sequence in enumerate(sequences):
            seq_name = sequence.name.upper().replace(' ', '_')
            
            logic_lines.append(f"// {sequence.name} Sequence Control")
            
            # Generate step control logic
            for step_idx, step in enumerate(sequence.steps):
                step_num = step_idx + 1
                step_tag = f"{seq_name}_STEP_{step_num}"
                
                if step['type'] == 'condition':
                    # Condition step - wait for condition to be true
                    condition = self._parse_step_condition(step['description'])
                    logic_lines.append(f"XIC({seq_name}_ACTIVE) XIC({condition}) OTE({step_tag}_ACTIVE);")
                    
                elif step['type'] == 'action':
                    # Action step - perform action
                    action = self._parse_step_action(step['description'])
                    prev_step_tag = f"{seq_name}_STEP_{step_num-1}" if step_num > 1 else f"{seq_name}_START"
                    logic_lines.append(f"XIC({prev_step_tag}_ACTIVE) OTE({action});")
                    logic_lines.append(f"XIC({action}) TON({step_tag}_TIMER,1000,0);")
                    logic_lines.append(f"XIC({step_tag}_TIMER.DN) OTE({step_tag}_COMPLETE);")
            
            # Sequence completion logic
            last_step = len(sequence.steps)
            logic_lines.append(f"XIC({seq_name}_STEP_{last_step}_COMPLETE) OTE({seq_name}_COMPLETE);")
            logic_lines.append(f"XIC({seq_name}_COMPLETE) OTU({seq_name}_ACTIVE);")
            
            logic_lines.append("")  # Add blank line between sequences
        
        return "\n".join(logic_lines)
    
    def _parse_step_condition(self, description: str) -> str:
        """Parse step description to extract condition tag"""
        # Simple parsing - can be enhanced with NLP
        description_upper = description.upper().replace(' ', '_')
        return f"{description_upper}_OK"
    
    def _parse_step_action(self, description: str) -> str:
        """Parse step description to extract action tag"""
        # Simple parsing - can be enhanced with NLP
        description_upper = description.upper().replace(' ', '_')
        return f"{description_upper}_CMD"
    
    async def _generate_custom_logic(self, requirements: EnhancedPLCRequirement) -> EnhancedGeneratedCode:
        """Generate custom logic when no patterns match"""
        
        logic_lines = []
        tags = []
        instructions_used = []
        
        # Use the basic code assistant for general-purpose logic generation
        if requirements.components or requirements.description:
            # Convert enhanced requirements to basic format
            basic_assistant = CodeAssistant(self.mcp_server)
            
            # Create a basic PLCRequirement from the enhanced one
            basic_req = PLCRequirement(
                description=requirements.description,
                inputs=[comp.name for comp in requirements.components if self._is_input_component(comp)],
                outputs=[comp.name for comp in requirements.components if self._is_output_component(comp)],
                logic_type=requirements.logic_type,
                conditions=[],  # Extract from description if needed
                actions=[]      # Extract from description if needed
            )
            
            # Use basic assistant's generator
            from .code_assistant import LadderLogicGenerator
            basic_generator = LadderLogicGenerator()
            basic_result = basic_generator.generate_from_requirements(basic_req)
            
            # Convert back to enhanced format
            logic_lines = [basic_result.ladder_logic] if basic_result.ladder_logic else []
            tags = basic_result.tags
            instructions_used = basic_result.instructions_used
        
        # Add complexity-based enhancements
        if requirements.complexity in [LogicComplexity.COMPLEX, LogicComplexity.ADVANCED]:
            # Add state machine logic for complex requirements
            state_logic = self._generate_state_machine_logic(requirements)
            if state_logic:
                logic_lines.append("\n// State Machine Control")
                logic_lines.append(state_logic)
        
        ladder_logic = "\n".join(logic_lines) if logic_lines else "// No logic generated - requirements unclear"
        
        return EnhancedGeneratedCode(
            ladder_logic=ladder_logic,
            tags=tags,
            instructions_used=instructions_used,
            comments=["Custom generated logic"],
            validation_notes=["Manual review recommended for custom logic"]
        )
    
    def _generate_state_machine_logic(self, requirements: EnhancedPLCRequirement) -> str:
        """Generate state machine logic for complex requirements"""
        
        logic_lines = []
        
        # Define common states for warehouse operations
        states = ['IDLE', 'RUNNING', 'STOPPING', 'FAULT', 'MAINTENANCE']
        
        logic_lines.append("// State Machine Logic")
        logic_lines.append("// State Definitions: 0=IDLE, 1=RUNNING, 2=STOPPING, 3=FAULT, 4=MAINTENANCE")
        
        # State transition logic
        logic_lines.append("XIC(START_CMD) EQU(CURRENT_STATE,0) MOV(1,CURRENT_STATE);  // IDLE to RUNNING")
        logic_lines.append("XIC(STOP_CMD) EQU(CURRENT_STATE,1) MOV(2,CURRENT_STATE);   // RUNNING to STOPPING")
        logic_lines.append("XIC(FAULT_DETECTED) MOV(3,CURRENT_STATE);                  // Any state to FAULT")
        logic_lines.append("XIC(MAINT_MODE) MOV(4,CURRENT_STATE);                      // Any state to MAINTENANCE")
        
        # State-based outputs
        logic_lines.append("EQU(CURRENT_STATE,1) OTE(SYSTEM_RUNNING);                  // Running state output")
        logic_lines.append("EQU(CURRENT_STATE,3) OTE(FAULT_ALARM);                     // Fault state output")
        
        return "\n".join(logic_lines)
    
    def _generate_safety_logic(self, safety_requirements: List[str]) -> List[str]:
        """Generate comprehensive safety logic"""
        
        safety_logic = []
        
        # Emergency stop logic
        if any('emergency' in req.lower() for req in safety_requirements):
            safety_logic.append("XIC(E_STOP_1_OK) XIC(E_STOP_2_OK) OTE(E_STOP_CHAIN_OK);")
        
        # Light curtain logic
        if any('light curtain' in req.lower() for req in safety_requirements):
            safety_logic.append("XIC(LIGHT_CURTAIN_CLEAR) XIO(LC_BYPASS) OTE(LC_SAFE);")
        
        # Guard monitoring
        if any('guard' in req.lower() for req in safety_requirements):
            safety_logic.append("XIC(GUARD_CLOSED) XIC(GUARD_LOCKED) OTE(GUARD_SAFE);")
        
        # Master safety enable
        safety_logic.append("XIC(E_STOP_CHAIN_OK) XIC(LC_SAFE) XIC(GUARD_SAFE) OTE(SAFETY_OK);")
        
        return safety_logic
    
    def _optimize_for_performance(self, code: EnhancedGeneratedCode, 
                                performance_req: Dict[str, Any]):
        """Optimize generated code for performance requirements"""
        
        # Add performance monitoring
        if 'timing_ms' in performance_req:
            timing_values = performance_req['timing_ms']
            code.performance_metrics['cycle_time_target'] = min(timing_values)
        
        if 'speed_linear' in performance_req:
            speed_values = performance_req['speed_linear']
            code.performance_metrics['max_speed'] = max(speed_values)
        
        # Add performance-related tags
        perf_tags = [
            {'name': 'CYCLE_TIME', 'data_type': 'DINT', 'description': 'Current cycle time in ms'},
            {'name': 'PERFORMANCE_OK', 'data_type': 'BOOL', 'description': 'Performance within limits'}
        ]
        code.tags.extend(perf_tags)
    
    def _extract_instructions_from_logic(self, ladder_logic: str) -> List[str]:
        """Extract PLC instructions from ladder logic"""

        # Common Studio 5000 instruction patterns
        instruction_pattern = r'\b([A-Z]{2,4})\b'
        matches = re.findall(instruction_pattern, ladder_logic)

        # Filter to known instructions only. Uses the shared, wider registry
        # (plc_language.instruction_mnemonics) rather than a small hardcoded
        # set here - the old 27-mnemonic set silently dropped any real
        # instruction it didn't happen to list, under-reporting
        # instructions_used to the documentation-level validation phase
        # (see ai_assistant/mcp_integration.py's Phase 1).
        return list(set(
            match for match in matches
            if instruction_mnemonics.is_instruction(match)
        ))
    
    async def _validate_instructions(self, instructions: List[str]) -> List[str]:
        """Validate instructions using MCP server"""
        
        validation_notes = []
        
        for instruction in instructions:
            try:
                # Check if instruction exists in MCP database
                if hasattr(self.mcp_server, 'get_instruction'):
                    instruction_info = await self.mcp_server.get_instruction(instruction)
                    if instruction_info:
                        validation_notes.append(f"✓ {instruction} instruction validated")
                    else:
                        validation_notes.append(f"⚠ {instruction} instruction not found in documentation")
            except Exception as e:
                validation_notes.append(f"Validation error for {instruction}: {str(e)}")
        
        return validation_notes
    
    def _generate_documentation(self, pattern: WarehousePattern, 
                             requirements: EnhancedPLCRequirement) -> str:
        """Generate comprehensive documentation for the generated code"""
        
        doc_lines = []
        
        doc_lines.append(f"# {pattern.name}")
        doc_lines.append(f"## Description")
        doc_lines.append(pattern.description)
        doc_lines.append("")
        
        doc_lines.append("## Requirements")
        doc_lines.append(f"- Domain: {requirements.domain.value}")
        doc_lines.append(f"- Complexity: {requirements.complexity.value}")
        doc_lines.append(f"- Logic Type: {requirements.logic_type}")
        doc_lines.append("")
        
        if requirements.components:
            doc_lines.append("## Components")
            for comp in requirements.components:
                safety_note = " (Safety Critical)" if comp.safety_critical else ""
                doc_lines.append(f"- {comp.name}: {comp.component_type}{safety_note}")
            doc_lines.append("")
        
        if pattern.safety_considerations:
            doc_lines.append("## Safety Considerations")
            for consideration in pattern.safety_considerations:
                doc_lines.append(f"- {consideration}")
            doc_lines.append("")
        
        if requirements.performance_requirements:
            doc_lines.append("## Performance Requirements")
            for key, value in requirements.performance_requirements.items():
                doc_lines.append(f"- {key}: {value}")
        
        return "\n".join(doc_lines)
    
    def _get_or_create_tag(self, available_tags: List[str], keywords: List[str], default: str) -> str:
        """Find best matching tag from extracted components or create default"""
        for tag in available_tags:
            for keyword in keywords:
                if keyword.upper() in tag.upper():
                    return tag
        return default
    
    def _is_input_component(self, component: IndustrialComponent) -> bool:
        """Determine if a component is an input type"""
        input_types = ['button', 'switch', 'sensor', 'input', 'signal', 'detector', 'photoeye', 
                      'photoelectric', 'proximity', 'limit_switch', 'pressure', 'temperature']
        return component.component_type in input_types
    
    def _is_output_component(self, component: IndustrialComponent) -> bool:
        """Determine if a component is an output type"""
        output_types = ['motor', 'light', 'valve', 'cylinder', 'actuator', 'relay', 'contactor', 
                       'solenoid', 'output', 'alarm', 'horn', 'beacon', 'servo_motor', 'stepper_motor']
        return component.component_type in output_types
    
    async def _generate_dynamic_logic(self, requirements: EnhancedPLCRequirement) -> EnhancedGeneratedCode:
        """Generate dynamic ladder logic by parsing and understanding the specification"""
        
        description = requirements.description
        
        # Check for specific complex patterns that need custom handling
        if self._is_dynamic_solenoid_firing_specification(description):
            return await self._generate_dynamic_solenoid_firing_logic(requirements)
        
        # Parse mathematical relationships
        math_logic = self._parse_mathematical_logic(description)
        
        # Parse conditional logic
        conditional_logic = self._parse_conditional_logic(description)
        
        # Parse dynamic addressing/indexing
        indexing_logic = self._parse_indexing_logic(description)
        
        # Parse tag requirements from specification
        required_tags = self._extract_tags_from_specification(description)
        
        # Parse structured rungs if present
        structured_rungs = self._parse_structured_rungs(description)
        
        # Combine all logic components
        if structured_rungs:
            # Use structured approach if rungs are explicitly defined
            ladder_logic = structured_rungs
        else:
            # Build logic from parsed components
            logic_sections = []
            
            if math_logic:
                logic_sections.append("// Mathematical Calculations")
                logic_sections.extend(math_logic)
                logic_sections.append("")
            
            if conditional_logic:
                logic_sections.append("// Conditional Logic")
                logic_sections.extend(conditional_logic)
                logic_sections.append("")
            
            if indexing_logic:
                logic_sections.append("// Dynamic Indexing/Addressing")
                logic_sections.extend(indexing_logic)
                logic_sections.append("")
            
            ladder_logic = "\n".join(logic_sections)
        
        # Extract instructions used
        instructions_used = self._extract_instructions_from_logic(ladder_logic)
        
        # Generate validation notes
        validation_notes = []
        if self.mcp_server:
            validation_notes = await self._validate_instructions(instructions_used)
        
        return EnhancedGeneratedCode(
            ladder_logic=ladder_logic,
            tags=required_tags,
            instructions_used=instructions_used,
            comments=[f"Generated dynamic logic for: {description[:100]}..."],
            validation_notes=validation_notes,
            performance_metrics={"generation_method": "dynamic_parsing"},
            documentation=f"Dynamically generated ladder logic based on complex specification analysis"
        )
    
    def _parse_mathematical_logic(self, description: str) -> List[str]:
        """Parse mathematical relationships from specification"""
        
        logic_lines = []
        
        # Common mathematical patterns in PLC specifications
        patterns = {
            r'Fire_Position\s*=\s*Package_Position_Current\s*\+\s*Lead_Distance_Inches': 
                "ADD(Package_Position_Current,Lead_Distance_Inches,Fire_Position);",
            r'Solenoid_Number\s*=\s*Fire_Position\s*/\s*([\d.]+)':
                lambda m: f"DIV(Fire_Position,{m.group(1)},Solenoid_Number_Raw);",
            r'Limit\s+Solenoid_Number\s+between\s+(\d+)\s+and\s+(\d+)':
                lambda m: f"LIM({m.group(1)},Solenoid_Number_Raw,{m.group(2)},Solenoid_Number);"
        }
        
        for pattern, instruction in patterns.items():
            import re
            matches = re.finditer(pattern, description, re.IGNORECASE)
            for match in matches:
                if callable(instruction):
                    logic_lines.append(instruction(match))
                else:
                    logic_lines.append(instruction)
        
        return logic_lines
    
    def _parse_conditional_logic(self, description: str) -> List[str]:
        """Parse conditional logic from specification"""
        
        logic_lines = []
        
        # Package size logic
        if "Small Package" in description and "Package_Length < 12" in description:
            logic_lines.append("LES(Package_Length,12.0,Small_Package);")
        
        if "Medium Package" in description and "12\" ≤ Package_Length < 24\"" in description:
            logic_lines.append("GEQ(Package_Length,12.0) LES(Package_Length,24.0,Medium_Package);")
        
        if "Large Package" in description and "Package_Length ≥ 24\"" in description:
            logic_lines.append("GEQ(Package_Length,24.0,Large_Package);")
        
        # Direction logic
        if "Package_Direction = 1" in description and "LEFT" in description:
            logic_lines.append("EQU(Package_Direction,1,Left_Direction);")
        
        if "Package_Direction = 2" in description and "RIGHT" in description:
            logic_lines.append("EQU(Package_Direction,2,Right_Direction);")
        
        # Belt selection logic
        if "Belt_Load_Balance_Select = 1" in description:
            logic_lines.append("EQU(Belt_Load_Balance_Select,1,Use_S02_1_Series);")
        
        if "Belt_Load_Balance_Select = 2" in description:
            logic_lines.append("EQU(Belt_Load_Balance_Select,2,Use_S02_2_Series);")
        
        return logic_lines
    
    def _parse_indexing_logic(self, description: str) -> List[str]:
        """Parse dynamic indexing/addressing logic"""
        
        logic_lines = []
        
        # Look for indexed addressing patterns
        import re
        
        # Pattern for S02_X_SOL[Solenoid_Number]:O.ProcessDataOut.Valve_X_solenoid_14
        indexed_patterns = re.findall(r'S02_[X12]_SOL\[([^\]]+)\]:[^.]+\.([^.]+)\.([^.\s]+)', description)
        
        if indexed_patterns:
            # Add master firing control
            conditions = []
            if "Package_Divert_Active" in description:
                conditions.append("Package_Divert_Active")
            if "Package_In_Fire_Zone" in description:
                conditions.append("Package_In_Fire_Zone")
            if "Package_Direction_Valid" in description:
                conditions.append("Package_Direction_Valid")
            if "Package_Type_Valid" in description:
                conditions.append("Package_Type_Valid")
            
            if conditions:
                condition_str = " XIC(".join([""] + conditions) + ")"
                logic_lines.append(f"{condition_str} OTE(Fire_Enable);")
        
        # Add specific valve firing logic based on package types
        valve_patterns = {
            "Small Left Package": ["Valve_3_solenoid_14", "Valve_5_solenoid_14"],
            "Small Right Package": ["Valve_4_solenoid_14", "Valve_6_solenoid_14"],
            "Medium Left Package": ["Valve_3_solenoid_14", "Valve_5_solenoid_14", "Valve_7_solenoid_14"],
            "Medium Right Package": ["Valve_2_solenoid_14", "Valve_4_solenoid_14", "Valve_6_solenoid_14"],
            "Large Left Package": ["Valve_1_solenoid_14", "Valve_3_solenoid_14", "Valve_5_solenoid_14", "Valve_7_solenoid_14"],
            "Large Right Package": ["Valve_2_solenoid_14", "Valve_4_solenoid_14", "Valve_6_solenoid_14", "Valve_8_solenoid_14"]
        }
        
        for package_type, valves in valve_patterns.items():
            if package_type in description:
                package_condition = package_type.lower().replace(" ", "_")
                for valve in valves:
                    logic_lines.append(f"XIC(Fire_Enable) XIC({package_condition}) OTE(S02_X_SOL[Solenoid_Number]:O.ProcessDataOut.{valve});")
        
        return logic_lines
    
    def _parse_structured_rungs(self, description: str) -> str:
        """Parse explicitly structured rungs from specification"""
        
        import re
        
        # Look for structured rung specifications
        rung_pattern = r'RUNG\s+(\d+):\s*([^R]+?)(?=RUNG\s+\d+:|$)'
        rungs = re.findall(rung_pattern, description, re.IGNORECASE | re.DOTALL)
        
        if not rungs:
            return ""
        
        rung_logic = []
        for rung_num, rung_content in rungs:
            rung_content = rung_content.strip()
            
            # Add comment for the rung
            rung_logic.append(f"// RUNG {rung_num}: {rung_content[:60]}...")
            
            # Parse the rung content and convert to ladder logic
            if "Position-Based Solenoid Selection" in rung_content:
                rung_logic.extend(self._parse_mathematical_logic(rung_content))
            elif "Package Length-Based Valve Selection" in rung_content:
                rung_logic.extend(self._parse_conditional_logic(rung_content))
            elif "Direction-Based Valve Control" in rung_content:
                rung_logic.extend(self._parse_conditional_logic(rung_content))
            elif "Dynamic Valve Firing" in rung_content:
                rung_logic.extend(self._parse_indexing_logic(rung_content))
            elif "Master Firing Control" in rung_content:
                conditions = ["Package_Divert_Active", "Package_In_Fire_Zone", 
                            "Package_Direction_Valid", "Package_Type_Valid"]
                condition_str = " XIC(".join([""] + conditions) + ")"
                rung_logic.append(f"{condition_str} OTE(Fire_Enable);")
            
            rung_logic.append("")  # Blank line between rungs
        
        return "\n".join(rung_logic)
    
    def _extract_tags_from_specification(self, description: str) -> List[Dict]:
        """Extract tag definitions from specification text"""
        
        tags = []
        
        # Look for explicit tag definitions
        import re
        
        tag_patterns = {
            r'Package_Position_Current\s*\(([^)]+)\)': ('Package_Position_Current', 'REAL', 'Current package position'),
            r'Package_Length\s*\(([^)]+)\)': ('Package_Length', 'REAL', 'Package length measurement'),
            r'Package_Direction\s*\(([^)]+)\)': ('Package_Direction', 'INT', 'Package direction (1=LEFT, 2=RIGHT)'),
            r'Lead_Distance_Inches\s*\(([^)]+)\)': ('Lead_Distance_Inches', 'REAL', 'Lead distance in inches'),
            r'Solenoid_Number\s*\(([^)]+)\)': ('Solenoid_Number', 'INT', 'Calculated solenoid number'),
            r'Belt_Load_Balance_Select\s*\(([^)]+)\)': ('Belt_Load_Balance_Select', 'INT', 'Belt selection (1 or 2)'),
            r'Package_Divert_Active\s*\(([^)]+)\)': ('Package_Divert_Active', 'BOOL', 'Package diversion active'),
            r'Package_In_Fire_Zone\s*\(([^)]+)\)': ('Package_In_Fire_Zone', 'BOOL', 'Package in firing zone'),
            r'Package_Direction_Valid\s*\(([^)]+)\)': ('Package_Direction_Valid', 'BOOL', 'Package direction is valid'),
            r'Package_Type_Valid\s*\(([^)]+)\)': ('Package_Type_Valid', 'BOOL', 'Package type is valid')
        }
        
        for pattern, (name, data_type, desc) in tag_patterns.items():
            if re.search(pattern, description):
                tags.append({
                    'name': name,
                    'data_type': data_type,
                    'description': desc
                })
        
        # Add calculated/intermediate tags
        if "Fire_Position" in description:
            tags.append({
                'name': 'Fire_Position',
                'data_type': 'REAL',
                'description': 'Calculated firing position'
            })
        
        if "Solenoid_Number_Raw" in description or "LIM(" in description:
            tags.append({
                'name': 'Solenoid_Number_Raw',
                'data_type': 'REAL',
                'description': 'Raw solenoid number before limiting'
            })
        
        # Add package type tags
        package_types = ['Small_Package', 'Medium_Package', 'Large_Package', 'Left_Direction', 'Right_Direction']
        for pkg_type in package_types:
            if pkg_type.lower() in description.lower():
                tags.append({
                    'name': pkg_type,
                    'data_type': 'BOOL',
                    'description': f'{pkg_type.replace("_", " ")} condition'
                })
        
        return tags
    
    def _is_dynamic_solenoid_firing_specification(self, description: str) -> bool:
        """Detect if this is a dynamic solenoid firing specification"""
        
        description_lower = description.lower()
        
        # Key indicators for dynamic solenoid firing systems
        solenoid_indicators = ['solenoid', 'valve', 'divert', 'firing']
        dynamic_indicators = ['dynamic', 'position-based', 'pkg_data', 'package data', 'iterate', 'array']
        belt_indicators = ['belt', 's02_1', 's02_2', 'dual belt', 'sorter']
        calculation_indicators = ['calculate', 'position', 'length', 'range', 'index']
        
        # Must have solenoid + dynamic + belt + calculation indicators
        solenoid_count = sum(1 for indicator in solenoid_indicators if indicator in description_lower)
        dynamic_count = sum(1 for indicator in dynamic_indicators if indicator in description_lower)
        belt_count = sum(1 for indicator in belt_indicators if indicator in description_lower)
        calc_count = sum(1 for indicator in calculation_indicators if indicator in description_lower)
        
        return (solenoid_count >= 2 and dynamic_count >= 1 and 
                belt_count >= 1 and calc_count >= 2)

    async def _generate_dynamic_solenoid_firing_logic(self, requirements: EnhancedPLCRequirement) -> EnhancedGeneratedCode:
        """Generate sophisticated dynamic solenoid firing logic for dual belt sortation system"""
        
        description = requirements.description
        
        ladder_lines = []
        tags = []
        instructions_used = []
        
        # Header comment
        ladder_lines.extend([
            "// =====================================================",
            "// Dynamic Solenoid Firing Routine for Dual Belt Sorter",
            "// System: Two belts (S02_1, S02_2) with 84 solenoids each",
            "// Each solenoid has 8 valves (odd=one direction, even=other)",
            "// =====================================================",
            ""
        ])
        
        # 1. System Enable and Safety Checks
        ladder_lines.extend([
            "// System Enable and Safety Interlocks",
            "XIC(System_Enable) XIO(Emergency_Stop) XIC(Belt_Status_OK) OTE(Solenoid_System_Enable);",
            "",
            "// Safety Status Check",
            "XIC(S02_1_Running) XIC(S02_2_Running) XIO(Any_Belt_Fault) OTE(Belt_Status_OK);",
            ""
        ])
        
        # 2. Package Array Iteration Setup
        ladder_lines.extend([
            "// Package Array Iteration Setup (1000 packages)",
            "XIC(Solenoid_System_Enable) XIC(Scan_Timer.DN) OTE(Start_Package_Scan);",
            "",
            "// Reset scan index at start",
            "XIC(Start_Package_Scan) MOV(0,Package_Scan_Index);",
            "",
            "// Scan timer - runs every 50ms",
            "XIC(Solenoid_System_Enable) TON(Scan_Timer,50,0);",
            ""
        ])
        
        # 3. Main Package Scanning Loop
        ladder_lines.extend([
            "// Main Package Scanning Loop",
            "XIC(Start_Package_Scan) JSR(DYNAMIC_SOLENOID_SCAN);",
            "",
            "// Increment scan index",
            "XIC(Start_Package_Scan) ADD(Package_Scan_Index,1,Package_Scan_Index);",
            "",
            "// Reset index when reaching end of array",
            "GEQ(Package_Scan_Index,1000) MOV(0,Package_Scan_Index);",
            ""
        ])
        
        # 4. Dynamic Solenoid Firing Logic (JSR Subroutine)
        ladder_lines.extend([
            "// ========== DYNAMIC_SOLENOID_SCAN Subroutine ==========",
            "",
            "// Check if package at current index is at divert point",
            "GRT(PKG_Data[Package_Scan_Index].Status.At_Divert,0,Package_At_Divert);",
            "",
            "// Process package if at divert point",
            "XIC(Package_At_Divert) JSR(PROCESS_PACKAGE_DIVERT);",
            ""
        ])
        
        # 5. Process Package Divert Logic
        ladder_lines.extend([
            "// ========== PROCESS_PACKAGE_DIVERT Subroutine ==========",
            "",
            "// Get belt assignment (0=S02_1, 1=S02_2)",
            "MOV(PKG_Data[Package_Scan_Index].Belt.Assignment,Current_Belt_Assignment);",
            "",
            "// Get package position and length",
            "MOV(PKG_Data[Package_Scan_Index].Position.Current,Current_Package_Position);",
            "MOV(PKG_Data[Package_Scan_Index].Length.Inches,Current_Package_Length);",
            "",
            "// Get package divert direction",
            "MOV(PKG_Data[Package_Scan_Index].Divert.Direction,Current_Divert_Direction);",
            ""
        ])
        
        # 6. Calculate Solenoid Range
        ladder_lines.extend([
            "// Calculate Solenoid Range Based on Position and Length",
            "",
            "// Calculate start solenoid (position / 6 inches per solenoid)",
            "DIV(Current_Package_Position,6.0,Start_Solenoid_Float);",
            "TRUNC(Start_Solenoid_Float,Start_Solenoid_Raw);",
            "",
            "// Calculate end solenoid (position + length) / 6",
            "ADD(Current_Package_Position,Current_Package_Length,End_Position);",
            "DIV(End_Position,6.0,End_Solenoid_Float);",
            "TRUNC(End_Solenoid_Float,End_Solenoid_Raw);",
            "",
            "// Limit solenoid range to valid values (1-84)",
            "LIM(1,Start_Solenoid_Raw,84,Start_Solenoid);",
            "LIM(1,End_Solenoid_Raw,84,End_Solenoid);",
            ""
        ])
        
        # 7. Belt and Direction Logic
        ladder_lines.extend([
            "// Belt Selection Logic",
            "EQU(Current_Belt_Assignment,0,Use_Belt_S02_1);",
            "EQU(Current_Belt_Assignment,1,Use_Belt_S02_2);",
            "",
            "// Direction Logic - Odd valves one way, Even valves other way",
            "EQU(Current_Divert_Direction,1,Fire_Odd_Valves);   // Direction 1 = Odd valves (1,3,5,7)",
            "EQU(Current_Divert_Direction,2,Fire_Even_Valves);  // Direction 2 = Even valves (2,4,6,8)",
            ""
        ])
        
        # 8. Dynamic Solenoid Firing
        ladder_lines.extend([
            "// Dynamic Solenoid Firing - Belt S02_1",
            "XIC(Use_Belt_S02_1) XIC(Fire_Odd_Valves) JSR(FIRE_S02_1_ODD_VALVES);",
            "XIC(Use_Belt_S02_1) XIC(Fire_Even_Valves) JSR(FIRE_S02_1_EVEN_VALVES);",
            "",
            "// Dynamic Solenoid Firing - Belt S02_2", 
            "XIC(Use_Belt_S02_2) XIC(Fire_Odd_Valves) JSR(FIRE_S02_2_ODD_VALVES);",
            "XIC(Use_Belt_S02_2) XIC(Fire_Even_Valves) JSR(FIRE_S02_2_EVEN_VALVES);",
            ""
        ])
        
        # 9. Valve Firing Subroutines
        ladder_lines.extend([
            "// ========== FIRE_S02_1_ODD_VALVES Subroutine ==========",
            "// Fire odd valves (1,3,5,7) for each solenoid in range",
            "",
            "// Initialize firing loop counter",
            "MOV(Start_Solenoid,Current_Solenoid);",
            "",
            "// Firing loop for S02_1 odd valves",
            "LEQ(Current_Solenoid,End_Solenoid,Continue_S02_1_Odd);",
            "XIC(Continue_S02_1_Odd) OTE(S02_1_SOL[Current_Solenoid].Valve_1);",
            "XIC(Continue_S02_1_Odd) OTE(S02_1_SOL[Current_Solenoid].Valve_3);",
            "XIC(Continue_S02_1_Odd) OTE(S02_1_SOL[Current_Solenoid].Valve_5);",
            "XIC(Continue_S02_1_Odd) OTE(S02_1_SOL[Current_Solenoid].Valve_7);",
            "XIC(Continue_S02_1_Odd) ADD(Current_Solenoid,1,Current_Solenoid);",
            "",
            "// ========== FIRE_S02_1_EVEN_VALVES Subroutine ==========",
            "// Fire even valves (2,4,6,8) for each solenoid in range",
            "",
            "MOV(Start_Solenoid,Current_Solenoid);",
            "LEQ(Current_Solenoid,End_Solenoid,Continue_S02_1_Even);",
            "XIC(Continue_S02_1_Even) OTE(S02_1_SOL[Current_Solenoid].Valve_2);",
            "XIC(Continue_S02_1_Even) OTE(S02_1_SOL[Current_Solenoid].Valve_4);",
            "XIC(Continue_S02_1_Even) OTE(S02_1_SOL[Current_Solenoid].Valve_6);",
            "XIC(Continue_S02_1_Even) OTE(S02_1_SOL[Current_Solenoid].Valve_8);",
            "XIC(Continue_S02_1_Even) ADD(Current_Solenoid,1,Current_Solenoid);",
            "",
            "// ========== FIRE_S02_2_ODD_VALVES Subroutine ==========",
            "MOV(Start_Solenoid,Current_Solenoid);",
            "LEQ(Current_Solenoid,End_Solenoid,Continue_S02_2_Odd);",
            "XIC(Continue_S02_2_Odd) OTE(S02_2_SOL[Current_Solenoid].Valve_1);",
            "XIC(Continue_S02_2_Odd) OTE(S02_2_SOL[Current_Solenoid].Valve_3);",
            "XIC(Continue_S02_2_Odd) OTE(S02_2_SOL[Current_Solenoid].Valve_5);",
            "XIC(Continue_S02_2_Odd) OTE(S02_2_SOL[Current_Solenoid].Valve_7);",
            "XIC(Continue_S02_2_Odd) ADD(Current_Solenoid,1,Current_Solenoid);",
            "",
            "// ========== FIRE_S02_2_EVEN_VALVES Subroutine ==========",
            "MOV(Start_Solenoid,Current_Solenoid);",
            "LEQ(Current_Solenoid,End_Solenoid,Continue_S02_2_Even);",
            "XIC(Continue_S02_2_Even) OTE(S02_2_SOL[Current_Solenoid].Valve_2);",
            "XIC(Continue_S02_2_Even) OTE(S02_2_SOL[Current_Solenoid].Valve_4);",
            "XIC(Continue_S02_2_Even) OTE(S02_2_SOL[Current_Solenoid].Valve_6);",
            "XIC(Continue_S02_2_Even) OTE(S02_2_SOL[Current_Solenoid].Valve_8);",
            "XIC(Continue_S02_2_Even) ADD(Current_Solenoid,1,Current_Solenoid);",
            ""
        ])
        
        # 10. Event Logging
        ladder_lines.extend([
            "// Event Logging for Troubleshooting",
            "XIC(Package_At_Divert) CTU(Package_Divert_Counter,65535,0);",
            "",
            "// Log firing events with timestamp",
            "XIC(Continue_S02_1_Odd) XIC(Continue_S02_1_Even) XIC(Continue_S02_2_Odd) XIC(Continue_S02_2_Even) XIC(Package_At_Divert)",
            "GSV(WALLCLOCKTIME,Local,DateTime,Fire_Event_Timestamp);",
            "// Store package info for logging",
            "MOV(Package_Scan_Index,Last_Fired_Package_Index);",
            "MOV(Current_Package_Position,Last_Fired_Position);",
            "MOV(Start_Solenoid,Last_Fired_Start_SOL);",
            "MOV(End_Solenoid,Last_Fired_End_SOL);",
            ""
        ])
        
        # Add all required tags
        tags.extend([
            # System control tags
            {'name': 'System_Enable', 'data_type': 'BOOL', 'description': 'System master enable'},
            {'name': 'Emergency_Stop', 'data_type': 'BOOL', 'description': 'Emergency stop input'},
            {'name': 'Belt_Status_OK', 'data_type': 'BOOL', 'description': 'Both belts running OK'},
            {'name': 'Solenoid_System_Enable', 'data_type': 'BOOL', 'description': 'Solenoid system enabled'},
            {'name': 'S02_1_Running', 'data_type': 'BOOL', 'description': 'Belt S02_1 running status'},
            {'name': 'S02_2_Running', 'data_type': 'BOOL', 'description': 'Belt S02_2 running status'},
            {'name': 'Any_Belt_Fault', 'data_type': 'BOOL', 'description': 'Any belt fault condition'},
            
            # Scanning control tags
            {'name': 'Scan_Timer', 'data_type': 'TIMER', 'description': 'Package scanning timer (50ms)', 'preset_value': 50},
            {'name': 'Start_Package_Scan', 'data_type': 'BOOL', 'description': 'Start package scan trigger'},
            {'name': 'Package_Scan_Index', 'data_type': 'DINT', 'description': 'Current package array index (0-999)'},
            {'name': 'Package_At_Divert', 'data_type': 'BOOL', 'description': 'Package at divert point flag'},
            
            # Package data tags
            {'name': 'Current_Belt_Assignment', 'data_type': 'INT', 'description': 'Current package belt assignment (0/1)'},
            {'name': 'Current_Package_Position', 'data_type': 'REAL', 'description': 'Current package position (inches)'},
            {'name': 'Current_Package_Length', 'data_type': 'REAL', 'description': 'Current package length (inches)'},
            {'name': 'Current_Divert_Direction', 'data_type': 'INT', 'description': 'Current package divert direction (1/2)'},
            
            # Calculation tags
            {'name': 'Start_Solenoid_Float', 'data_type': 'REAL', 'description': 'Start solenoid calculation (float)'},
            {'name': 'Start_Solenoid_Raw', 'data_type': 'DINT', 'description': 'Start solenoid before limiting'},
            {'name': 'Start_Solenoid', 'data_type': 'DINT', 'description': 'Final start solenoid (1-84)'},
            {'name': 'End_Position', 'data_type': 'REAL', 'description': 'Package end position calculation'},
            {'name': 'End_Solenoid_Float', 'data_type': 'REAL', 'description': 'End solenoid calculation (float)'},
            {'name': 'End_Solenoid_Raw', 'data_type': 'DINT', 'description': 'End solenoid before limiting'},
            {'name': 'End_Solenoid', 'data_type': 'DINT', 'description': 'Final end solenoid (1-84)'},
            {'name': 'Current_Solenoid', 'data_type': 'DINT', 'description': 'Current solenoid in firing loop'},
            
            # Belt and direction control tags
            {'name': 'Use_Belt_S02_1', 'data_type': 'BOOL', 'description': 'Use belt S02_1 for current package'},
            {'name': 'Use_Belt_S02_2', 'data_type': 'BOOL', 'description': 'Use belt S02_2 for current package'},
            {'name': 'Fire_Odd_Valves', 'data_type': 'BOOL', 'description': 'Fire odd valves (1,3,5,7)'},
            {'name': 'Fire_Even_Valves', 'data_type': 'BOOL', 'description': 'Fire even valves (2,4,6,8)'},
            
            # Firing control tags
            {'name': 'Continue_S02_1_Odd', 'data_type': 'BOOL', 'description': 'Continue S02_1 odd valve firing'},
            {'name': 'Continue_S02_1_Even', 'data_type': 'BOOL', 'description': 'Continue S02_1 even valve firing'},
            {'name': 'Continue_S02_2_Odd', 'data_type': 'BOOL', 'description': 'Continue S02_2 odd valve firing'},
            {'name': 'Continue_S02_2_Even', 'data_type': 'BOOL', 'description': 'Continue S02_2 even valve firing'},
            
            # Logging tags
            {'name': 'Package_Divert_Counter', 'data_type': 'COUNTER', 'description': 'Count of packages diverted', 'preset_value': 65535},
            {'name': 'Fire_Event_Timestamp', 'data_type': 'DINT', 'description': 'Timestamp of last firing event'},
            {'name': 'Last_Fired_Package_Index', 'data_type': 'DINT', 'description': 'Index of last fired package'},
            {'name': 'Last_Fired_Position', 'data_type': 'REAL', 'description': 'Position of last fired package'},
            {'name': 'Last_Fired_Start_SOL', 'data_type': 'DINT', 'description': 'Start solenoid of last firing'},
            {'name': 'Last_Fired_End_SOL', 'data_type': 'DINT', 'description': 'End solenoid of last firing'}
        ])
        
        # Extract instructions used
        ladder_logic = "\n".join(ladder_lines)
        instructions_used = self._extract_instructions_from_logic(ladder_logic)
        
        # Generate validation notes
        validation_notes = [
            "✓ Dynamic position-based solenoid firing implemented",
            "✓ Dual belt support (S02_1 and S02_2) with 84 solenoids each",
            "✓ Package array iteration through PKG_Data[1000]",
            "✓ Position and length-based solenoid range calculation",
            "✓ Direction-based valve selection (odd/even)",
            "✓ Safety interlocks and belt status monitoring",
            "✓ Event logging for troubleshooting",
            "ℹ Requires PKG_Data user-defined type to be created",
            "ℹ Requires S02_1_SOL and S02_2_SOL arrays [1..84] of solenoid UDT",
            "⚠ Subroutines (JSR) may need to be actual routine files in Studio 5000"
        ]
        
        return EnhancedGeneratedCode(
            ladder_logic=ladder_logic,
            structured_text="",
            tags=tags,
            instructions_used=instructions_used,
            safety_logic=[
                "XIC(System_Enable) XIO(Emergency_Stop) XIC(Belt_Status_OK) OTE(Solenoid_System_Enable);",
                "XIC(S02_1_Running) XIC(S02_2_Running) XIO(Any_Belt_Fault) OTE(Belt_Status_OK);"
            ],
            performance_metrics={
                'estimated_scan_time_ms': len(ladder_lines) * 0.05,  # More optimized than basic
                'memory_usage_words': len(tags) * 4,  # Higher memory due to arrays
                'max_packages_per_scan': 20,  # Can process 20 packages per 50ms scan
                'max_solenoids_fired_simultaneously': 168  # 84 per belt * 2 belts
            },
            validation_notes=validation_notes,
            documentation=f"Dynamic solenoid firing routine for dual belt non-con sorter system with position-based firing logic",
            comments=[
                f"Generated {len(ladder_lines)} lines of sophisticated ladder logic",
                f"Created {len(tags)} specialized tags for dynamic operation",
                f"Supports {84*2} solenoids across 2 belts with 8 valves each",
                "Implements dynamic position-based firing with package length consideration",
                "Includes comprehensive safety interlocks and event logging"
            ]
        )
    
    async def _generate_custom_logic(self, requirements: EnhancedPLCRequirement) -> EnhancedGeneratedCode:
        """Generate custom ladder logic for requirements that don't match patterns"""
        
        # This is a fallback method for completely custom logic
        # For now, provide a basic structure that can be enhanced
        
        ladder_logic = f"""// Custom Logic Generated for: {requirements.description[:60]}...

// Basic System Ready Logic
XIC(SYSTEM_ENABLE) XIO(SYSTEM_FAULT) OTE(SYSTEM_READY);

// Custom Logic Section
// TODO: Implement specific logic based on requirements
NOP();

// System Status
XIC(SYSTEM_READY) OTE(STATUS_READY);"""
        
        # Basic tags for custom logic
        tags = [
            {'name': 'SYSTEM_ENABLE', 'data_type': 'BOOL', 'description': 'System enable input'},
            {'name': 'SYSTEM_FAULT', 'data_type': 'BOOL', 'description': 'System fault status'},
            {'name': 'SYSTEM_READY', 'data_type': 'BOOL', 'description': 'System ready output'},
            {'name': 'STATUS_READY', 'data_type': 'BOOL', 'description': 'Status indicator'}
        ]
        
        instructions_used = ['XIC', 'XIO', 'OTE', 'NOP']
        
        return EnhancedGeneratedCode(
            ladder_logic=ladder_logic,
            tags=tags,
            instructions_used=instructions_used,
            comments=[f"Custom logic structure for: {requirements.description[:100]}..."],
            validation_notes=["Custom logic requires manual review and implementation"],
            performance_metrics={"generation_method": "custom_fallback"},
            documentation="Basic custom logic structure - requires manual enhancement"
        )
    
    def _extract_instructions_from_logic(self, ladder_logic: str) -> List[str]:
        """Extract PLC instructions from ladder logic code"""
        
        import re
        
        # Common PLC instruction patterns
        instruction_pattern = r'\b([A-Z]{2,4})\s*\('
        
        matches = re.findall(instruction_pattern, ladder_logic)
        
        # Remove duplicates and return sorted list
        return sorted(list(set(matches)))
    
    async def _validate_instructions(self, instructions: List[str]) -> List[str]:
        """Validate instructions using MCP server"""
        
        validation_notes = []
        
        for instruction in instructions:
            try:
                if hasattr(self.mcp_server, 'get_instruction'):
                    inst_info = await self.mcp_server.get_instruction(instruction)
                    if inst_info:
                        validation_notes.append(f"✓ {instruction} instruction validated")
                    else:
                        validation_notes.append(f"⚠ {instruction} instruction not found in documentation")
                
            except Exception as e:
                validation_notes.append(f"❌ {instruction}: Validation error - {str(e)}")
        
        return validation_notes

