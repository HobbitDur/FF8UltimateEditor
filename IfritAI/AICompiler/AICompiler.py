import copy
import os
import sys
from lark import Lark

from IfritAI.AICompiler.AIAST import Block, Command, IfStatement, Value, ParamList
from IfritAI.AICompiler.AIASTTransformer import AIASTTransformer
from IfritAI.AICompiler.AICodeGenerator import AICodeGenerator
from IfritAI.AICompiler.AITypeResolver import AITypeResolver

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

    def __init__(self, game_data, battle_text=(), info_stat_data={}):
        self.game_data = game_data
        self.parser = Lark(self.grammar, start='start', parser='lalr')
        self.transformer = AIASTTransformer()
        self.type_resolver = AITypeResolver(game_data,  battle_text, info_stat_data)
        self.generator = AICodeGenerator(game_data)

    def compile(self, source_code):
        print("compile")
        tree = self.parser.parse(source_code)
        print("tree")
        print(tree)
        ast = self.transformer.transform(tree)
        print("ast")
        print(ast)

        resolved_ast = self.type_resolver.resolve(ast)
        print("resolved_ast")
        print(resolved_ast)

        ast_rainbow_fixed = self.update_stop(resolved_ast)
        ff8_assembly = self.generator.generate(ast_rainbow_fixed)
        print("ff8_assembly")
        print(ff8_assembly)
        return ff8_assembly

    def update_stop(self, ast):
        """Ensure exactly one stop at the end and size is multiple of 4"""
        print("update_stop")
        # First, ensure we have exactly one stop at the end
        ast = self._ensure_single_trailing_stop(ast)
        print("ast after removing trailing")
        print(ast)
        # Calculate the current size
        current_size = self._calculate_tree_size(ast)
        print(f"current_size: {current_size}")
        # Add padding to make it a multiple of 4
        padding_needed = (4 - (current_size % 4)) % 4
        print(f"padding_needed: {padding_needed}")

        if padding_needed > 0:
            ast = self._add_padding(ast, padding_needed)
        print("ast at the end")
        print(ast)
        return ast

    def _ensure_single_trailing_stop(self, node):
        """Ensure exactly one Command('stop') at the end of blocks"""
        if isinstance(node, Block):
            # Process all statements recursively first
            processed_statements = []
            for stmt in node.statements:
                processed_statements.append(self._ensure_single_trailing_stop(stmt))

            # Remove all trailing stops
            while processed_statements and self._is_stop_command(processed_statements[-1]):
                processed_statements.pop()

            # Add exactly one stop at the end
            processed_statements.append(Command('stop'))

            # Update the node's statements
            node.statements = processed_statements
            return node

        elif isinstance(node, IfStatement):
            # Process then block
            node.then_block = self._ensure_single_trailing_stop(node.then_block)

            # Process elseif branches
            for elif_branch in node.elif_branches:
                elif_branch.block = self._ensure_single_trailing_stop(elif_branch.block)

            # Process else block
            if node.else_block:
                node.else_block = self._ensure_single_trailing_stop(node.else_block)

            return node

        # Command nodes are leaf nodes, just return them
        return node

    def _calculate_tree_size(self, node):
        """Calculate the total size of the tree based on your rules"""
        if isinstance(node, Block):
            # Each statement in the block contributes its size
            total_size = 0
            for stmt in node.statements:
                total_size += self._calculate_tree_size(stmt)
            return total_size

        elif isinstance(node, IfStatement):
            # Condition adds 5
            # ThenBlock adds 3 plus its content
            size = 5  # for the condition

            # Add size of then block
            size += 3  # for the ThenBlock wrapper
            size += self._calculate_tree_size(node.then_block)

            # Add size of elseif branches
            for elif_branch in node.elif_branches:
                size += 5  # for the elseif condition
                size += 3  # for the block wrapper
                size += self._calculate_tree_size(elif_branch.block)

            # Add size of else block if present
            if node.else_block:
                size += 3  # for the else block wrapper
                size += self._calculate_tree_size(node.else_block)

            return size

        elif isinstance(node, Command):
            # Each command has at least 1 for the command itself
            # Plus each parameter adds 1
            size = 1  # for the command

            if node.params and node.params.params:
                size += len(node.params.params)

            return size

        elif isinstance(node, Value):
            # Each Value contributes 1
            return 1

        elif isinstance(node, ParamList):
            # ParamList size is the sum of its values
            size = 0
            if node.params:
                for param in node.params:
                    size += self._calculate_tree_size(param)
            return size

        # Default for unknown node types
        return 0

    def _add_padding(self, ast, padding_needed):
        """Add padding commands to make the size a multiple of 4"""
        # Create padding commands (could be nop or stop commands)
        # Let's use stop commands for padding
        padding_stops = [Command('stop') for _ in range(padding_needed)]

        # If the AST is a Block, add padding to its statements
        if isinstance(ast, Block):
            # Remove the last stop (we'll re-add it after padding)
            if ast.statements and self._is_stop_command(ast.statements[-1]):
                ast.statements.pop()

            # Add padding stops
            ast.statements.extend(padding_stops)

            # Add back the final stop
            ast.statements.append(Command('stop'))

        return ast

    def _is_stop_command(self, node):
        """Check if a node is a Command('stop')"""
        return isinstance(node, Command) and node.name.lower() == 'stop'