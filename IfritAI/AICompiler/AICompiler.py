import os
import sys
from lark import Lark

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
    value: ID | NUMBER | OPERATOR

    ID: /[a-zA-Z_][a-zA-Z_0-9]*/
    NUMBER: /[0-9]+/
    OPERATOR: /[><!]=?|==/

    %import common.WS
    %import common.CPP_COMMENT    // For // comments
    %import common.C_COMMENT      // For /* ... */ comments
    %ignore WS
    %ignore CPP_COMMENT
    %ignore C_COMMENT
    """

    def __init__(self, game_data):
        self.game_data = game_data
        self.parser = Lark(self.grammar, start='start', parser='lalr')
        self.transformer = AIASTTransformer()
        self.type_resolver = AITypeResolver(game_data)
        self.generator = AICodeGenerator(game_data)

    def compile(self, source_code):
        try:
            tree = self.parser.parse(source_code)
            ast = self.transformer.transform(tree)
            resolved_ast = self.type_resolver.resolve(ast)
            ff8_assembly = self.generator.generate(resolved_ast)
            return ff8_assembly
        except Exception as e:
            return f"Compilation error: {e}"