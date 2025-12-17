# AICodeByteGenerator.py
from IfritAI.AICompiler.AIAST import *


class AICodeGenerator:
    def __init__(self, game_data):
        self.game_data = game_data
        self.opcode_map = self._build_opcode_map()
        self.output_bytes = []
        self.labels = {}  # For tracking jump targets
        self.current_position = 0

    def _build_opcode_map(self):
        """Build a mapping from command names to opcode info"""
        opcode_map = {}
        for op_info in self.game_data.ai_data_json.get('op_code_info', []):
            func_name = op_info.get('func_name')
            if func_name:
                opcode_map[func_name] = op_info
        return opcode_map

    def generate(self, ast):
        """Generate FF8 assembly as list of integers from AST"""
        self.output_bytes = []
        self.current_position = 0
        self.visit(ast)
        return self.output_bytes  # Return list instead of bytes()

    def emit_byte(self, value):
        """Emit a single byte to the output"""
        self.output_bytes.append(value)
        self.current_position += 1

    def emit_bytes(self, values):
        """Emit multiple bytes to the output"""
        for value in values:
            self.emit_byte(value)

    def emit_int16_le(self, value):
        """Emit a 16-bit integer in little-endian format"""
        if value & 0x8000 != 0:
            signed=True
        else:
            signed=False
        int16 = value.to_bytes(signed=signed,  length=2, byteorder='little')
        for i, param in enumerate(list(int16)):
            self.emit_byte(int(param))

    def visit_Block(self, node):
        """Generate code for a block of statements"""
        for stmt in node.statements:
            self.visit(stmt)

    def visit_IfStatement(self, node):
        """Generate code for an if-statement with optional elseif/else"""

        # For a simple if/else:
        # IF condition jump_over_then
        # then_block
        # JUMP over_else (if else exists)
        # else_block

        # Calculate size of then-block
        then_block_size = self._calculate_block_size(node.then_block)

        # Emit IF command
        self.emit_byte(0x02)  # IF opcode

        # Emit condition with jump offset to skip then-block when false
        # The jump offset is the size of the then-block
        self._emit_condition(node.condition, then_block_size+3)

        # Emit then-block
        self.visit(node.then_block)

        # Handle elseif branches
        for elif_branch in node.elif_branches:
            # For elseif: JUMP over next part, then IF
            # Calculate size of the entire remaining structure
            remaining_size = self._calculate_remaining_size(elif_branch, node.elif_branches, node.else_block)
            # Emit jump to skip to end if previous condition was true
            self.emit_byte(0x23)  # JUMP opcode
            self.emit_int16_le(remaining_size)

            # Emit the elseif condition
            elif_then_size = self._calculate_block_size(elif_branch.block) + 3
            self.emit_byte(0x02)  # IF opcode
            self._emit_condition(elif_branch.condition, elif_then_size)

            # Emit elseif then-block
            self.visit(elif_branch.block)

        # Handle else block
        if node.else_block:
            # Calculate size of else block
            else_block_size = self._calculate_block_size(node.else_block)

            # Emit jump to skip else block if we executed then-block or elseif
            self.emit_byte(0x23)  # JUMP opcode
            self.emit_int16_le(else_block_size)

            # Emit else block
            self.visit(node.else_block)
        else:
            self.emit_byte(0x23)  # JUMP opcode
            self.emit_int16_le(0)

        # If no else block and no elseif, nothing more to do

    def _calculate_remaining_size(self, current_elif, remaining_elifs, else_block):
        """Calculate size from current point to end of if-structure"""
        # We need to calculate: current elif block + remaining elifs + else
        total_size = 0

        # Size of current elif's IF command and condition (8 bytes)
        total_size += 8

        # Size of current elif's then-block
        total_size += self._calculate_block_size(current_elif.block)

        # For each remaining elif: jump + IF + then-block
        for elif_branch in remaining_elifs:
            if elif_branch != current_elif:  # Skip current one
                total_size += 3  # JUMP command
                total_size += 8  # IF command
                total_size += self._calculate_block_size(elif_branch.block)

        # Add else block if exists
        if else_block:
            total_size += 3  # JUMP command to skip else
            total_size += self._calculate_block_size(else_block)
        else:
            total_size += 3

        return total_size

    def _emit_condition(self, condition, jump_offset):
        """Emit condition parameters for IF command with jump offset"""
        params = condition.params.params

        if len(params) >= 4:
            # Subject ID
            self.emit_byte(int(params[0].value))

            # Parameter type
            self.emit_byte(int(params[1].value))

            # Comparator
            self.emit_byte(int(params[2].value))

            # Value (2 bytes, little-endian)
            value = int(params[3].value)
            self.emit_byte(value & 0xFF)
            self.emit_byte((value >> 8) & 0xFF)

            # Jump offset (2 bytes, little-endian)
            self.emit_byte(jump_offset & 0xFF)
            self.emit_byte((jump_offset >> 8) & 0xFF)
        else:
            # Not enough parameters
            for _ in range(6):
                self.emit_byte(0x00)

    def _calculate_block_size(self, block):
        """Calculate the size of a block without emitting bytes"""
        # We need to temporarily capture output to calculate size
        original_output = self.output_bytes
        original_position = self.current_position

        # Create temporary buffers
        temp_output = []
        self.output_bytes = temp_output
        self.current_position = 0

        # Visit the block
        self.visit(block)

        # Get size
        block_size = self.current_position

        # Restore original state
        self.output_bytes = original_output
        self.current_position = original_position

        return block_size

    def visit_Command(self, node):
        """Generate code for a command"""
        if node.name in self.opcode_map:
            op_info = self.opcode_map[node.name]
            opcode = op_info.get('op_code', 0)
            size = op_info.get('size', 0)
            complexity = op_info.get('complexity', 0)
            # Emit opcode
            self.emit_byte(opcode)
            # Emit parameters if any
            if node.params and size > 0:
                params = node.params.params
                param_type = self.opcode_map[node.name]["param_type"]
                # First re-arrange the params:
                param_index = self.opcode_map[node.name]["param_index"]
                inverse = [0] * len(param_index)
                for orig, new in enumerate(param_index):
                    inverse[new] = orig
                result =  [params[i] for i in inverse]
                for i, param in enumerate(result):
                    if param_type[i] in ("int16", "percent_elem"):
                        self.emit_int16_le(int(param.value))
                    else:
                        self.emit_byte(int(param.value))

    def visit(self, node):
        """Generic visitor"""
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        """Default handler for unknown node types"""
        return node