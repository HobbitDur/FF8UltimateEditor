import copy
import os
import sys
from lark import Lark

from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import Block, Command, IfStatement, Value, ParamList
from IfritAI.AICompiler.AIASTTransformer import AIASTTransformer
from IfritAI.AICompiler.AICodeGenerator import AICodeGenerator
from IfritAI.AICompiler.AICompilerTypeResolver import AICompilerTypeResolver


class AICompiler:
    grammar = r"""
    start: stmt*

    stmt: if_stmt | command

    if_stmt: "if" condition block ("elseif" condition block)* ("else" block)?
    condition: "(" param_list ")"
    block: "{" stmt* "}"
    command: ID ("(" param_list? ")")? ";"

    param_list: value ("," value)*
    value: ID | NUMBER | OPERATOR | STRING 

    ID: /[a-zA-Z_][a-zA-Z_0-9%]*|[0-9]+%/
    NUMBER: /-?[0-9]+/
    OPERATOR: /[><!]=?|==/
    STRING: /"(?:[^"\\]|\\.)*"/

    %import common.WS
    %import common.CPP_COMMENT    // For // comments
    %import common.C_COMMENT      // For /* ... */ comments
    %ignore WS
    %ignore CPP_COMMENT
    %ignore C_COMMENT
    """

    def __init__(self, game_data: GameData, battle_text=(), info_stat_data={}):
        self.game_data = game_data
        self.parser = Lark(self.grammar, start='start', parser='lalr')
        self.transformer = AIASTTransformer()
        self.type_resolver = AICompilerTypeResolver(game_data, battle_text, info_stat_data)
        self.generator = AICodeGenerator(game_data)

    def compile(self, source_code: str):
        print("Compile")
        print("Source_code")
        print(source_code)
        source_code_cleaned = self.clean_all(source_code)
        print("source_code_cleaned")
        print(source_code_cleaned)
        # print("compile")
        tree = self.parser.parse(source_code_cleaned)
        # print("tree")
        # print(tree)
        ast = self.transformer.transform(tree)
        # print("ast")
        # print(ast)

        resolved_ast = self.type_resolver.resolve(ast)
        # print("resolved_ast")
        # print(resolved_ast)

        ast_rainbow_fixed = self.update_stop(resolved_ast)
        ff8_assembly = self.generator.generate(ast_rainbow_fixed)
        # print("ff8_assembly")
        # print(ff8_assembly)
        return ff8_assembly

    def clean_all(self, source_code: str):
        source_code_cleaned = self._clean_comparator(source_code)
        source_code_cleaned = self._clean_quote(source_code)
        return source_code_cleaned

    def _clean_comparator(self, source_code: str):
        comparator_single = self.game_data.ai_data_json["list_comparator"]
        comparator_code_expected = self.game_data.ai_data_json["list_comparator_ifritAI"]

        source_code_cleaned = str(source_code)
        for index in range(len(comparator_single)):
            source_code_cleaned = source_code_cleaned.replace(comparator_single[index], comparator_code_expected[index])
        return source_code_cleaned

    def _clean_quote(self, source_code: str):
        quote_to_be_changed = [
            "“", "”",  # U+201C, U+201D | English double quotes (curly/smart quotes)
            "«", "»",  # U+00AB, U+00BB | French/European guillemets (double angle)
            "„", "‟",  # U+201E, U+201F | Double low-9 and high-reversed-9 quotes
            "＂",      # U+FF02         | Fullwidth double quote (CJK/Asian)
            "‘", "’",  # U+2018, U+2019 | Single curly quotes / Typographic apostrophes
            "‚", "‛",  # U+201A, U+201B | Single low-9 and high-reversed-9 quotes
            "′", "″"   # U+2032, U+2033 | Prime and double prime symbols
        ]
        quote_expected = "\""
        source_code_cleaned = str(source_code)
        for index in range(len(quote_to_be_changed)):
            source_code_cleaned = source_code_cleaned.replace(quote_to_be_changed[index], quote_expected)
        return source_code_cleaned


    def set_battle_text_info_stat(self, battle_text=None, info_stat=None):
        self.type_resolver.set_battle_text_info_stat(battle_text, info_stat)

    def update_stop(self, ast):
        """Ensure exactly one stop at the end and size is multiple of 4"""
        # print("\n=== UPDATE STOP ===")
        # print(f"Initial AST: {self._ast_to_string(ast)}")

        # Ensure we have a Block at the top level
        if not isinstance(ast, Block):
            # print(f"Root is not a Block, wrapping in Block")
            ast = Block(statements=[ast])

        # Ensure the top-level block ends with exactly one stop
        ast = self._ensure_top_level_stop(ast)
        # print(f"After _ensure_top_level_stop: {self._ast_to_string(ast)}")

        # Calculate the current size
        current_size = self._calculate_tree_size(ast)
        # print(f"Current size: {current_size}")

        # Add padding to make it a multiple of 4
        padding_needed = (4 - (current_size % 4)) % 4
        # print(f"Padding needed: {padding_needed}")

        if padding_needed > 0:
            ast = self._add_top_level_padding(ast, padding_needed)
            # print(f"After _add_top_level_padding: {self._ast_to_string(ast)}")

        # Verify final size
        final_size = self._calculate_tree_size(ast)
        # print(f"Final size: {final_size} (multiple of 4: {final_size % 4 == 0})")
        # print("=== END UPDATE STOP ===\n")

        return ast

    def _ensure_top_level_stop(self, block):
        """Ensure the top-level block ends with exactly one stop"""
        if not isinstance(block, Block):
            return block

        # Remove all trailing stops from the top level
        while block.statements and self._is_stop_command(block.statements[-1]):
            removed = block.statements.pop()
            # print(f"    Removed top-level stop: {self._ast_to_string(removed)}")

        # Add exactly one stop at the end
        block.statements.append(Command('stop'))
        # print(f"    Added final top-level stop")

        return block

    def _add_top_level_padding(self, block, padding_needed):
        """Add padding stops to the top-level block only"""
        # print(f"  _add_top_level_padding: need {padding_needed} padding stops")

        # Create padding commands
        padding_stops = [Command('stop') for _ in range(padding_needed)]
        # print(f"    Created {len(padding_stops)} padding stops")

        if not isinstance(block, Block):
            # print(f"    WARNING: Expected Block, got {type(block)}")
            return block

        # Insert padding stops right before the last statement (which should be the final stop)
        if block.statements and len(block.statements) >= 1:
            # print(f"    Inserting {padding_needed} padding stops before last statement")
            block.statements[-1:-1] = padding_stops
        else:
            # print(f"    Block is empty, setting statements to padding + stop")
            block.statements = padding_stops + [Command('stop')]

        # print(f"    Block now has {len(block.statements)} statements")
        return block

    def _calculate_tree_size(self, node):
        """Calculate the total size of the tree based on your rules"""
        if isinstance(node, Block):
            total = 0
            for stmt in node.statements:
                total += self._calculate_tree_size(stmt)
            return total

        elif isinstance(node, IfStatement):
            size = 8  # for the condition
            # Add size of then block (just its content, no extra for the block itself)
            size += self._calculate_tree_size(node.then_block)

            # Add size of elseif branches
            for elif_branch in node.elif_branches:
                size += 8  # for the elseif condition
                size += 3  # The jump for the elseif
                size += self._calculate_tree_size(elif_branch.block)

            # Add size of else block if present
            if node.else_block:
                size += self._calculate_tree_size(node.else_block)
                size += 3  # The jump for the else

            if not node.else_block:
                size += 3  # Need a endif in this case.
            return size

        elif isinstance(node, Command):
            size = 1  # for the command itself
            if node.params:
                size += self._calculate_tree_size(node.params)
            return size

        elif isinstance(node, Value):
            return node.size

        elif isinstance(node, ParamList):
            size = 0
            if node.params:
                for param in node.params:
                    size += self._calculate_tree_size(param)
            return size

        return 0

    def _ast_to_string(self, node, indent=0):
        """Helper to convert AST to string for #printing"""
        spaces = "  " * indent

        if isinstance(node, Block):
            result = f"{spaces}Block:\n"
            for stmt in node.statements:
                result += self._ast_to_string(stmt, indent + 1)
            return result

        elif isinstance(node, IfStatement):
            result = f"{spaces}IfStatement:\n"
            if node.condition:
                result += f"{spaces}  Condition:\n"
                result += self._ast_to_string(node.condition, indent + 2)
            result += f"{spaces}  ThenBlock:\n"
            result += self._ast_to_string(node.then_block, indent + 2)
            for i, elif_branch in enumerate(node.elif_branches):
                result += f"{spaces}  ElseIf {i}:\n"
                result += self._ast_to_string(elif_branch.block, indent + 2)
            if node.else_block:
                result += f"{spaces}  ElseBlock:\n"
                result += self._ast_to_string(node.else_block, indent + 2)
            return result

        elif isinstance(node, Command):
            params = ""
            if node.params and node.params.params:
                params = "(" + ", ".join([str(p.value) for p in node.params.params]) + ")"
            return f"{spaces}Command('{node.name}'{params})\n"

        elif isinstance(node, Value):
            return f"{spaces}Value('{node.value}')\n"

        elif isinstance(node, ParamList):
            result = f"{spaces}ParamList:\n"
            for param in node.params:
                result += self._ast_to_string(param, indent + 1)
            return result

        elif isinstance(node, list):
            result = f"{spaces}List [{len(node)} items]:\n"
            for item in node:
                result += self._ast_to_string(item, indent + 1)
            return result

        else:
            return f"{spaces}{str(node)}\n"

    def _is_stop_command(self, node):
        """Check if a node is a Command('stop')"""
        return isinstance(node, Command) and node.name.lower() == 'stop'
