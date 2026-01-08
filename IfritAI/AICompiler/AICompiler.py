import copy
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
        ff8_assembly = self.generator.generate(resolved_ast)
        print("ff8_assembly")
        print(ff8_assembly)
        return ff8_assembly

    # def _update_stop_on_list(self, list_to_update: [CommandAnalyser]):
    #     """To remove all too much 0 and add new one till %4 for rainbow fix"""
    #     new_end = CommandAnalyser(0, [], self.game_data)
    #     # Must always have a stop at the end, so adding one:
    #     list_to_update.append(copy.deepcopy(new_end))
    #     if len(list_to_update) == 1:
    #         list_to_update[-1].line_index = 0
    #     else:
    #         list_to_update[-1].line_index = list_to_update[-2].line_index + 1
    #     # First do it by removing exceeding of stop
    #     while len(list_to_update) >= 2 and list_to_update[-1].get_id() == 0 and list_to_update[-2].get_id() == 0:
    #         del list_to_update[-1]
    #     # Now compute the size of all command
    #     section_size = 0
    #     # Last jump position is to manage the case where you jump in the middle of lots of stop so that you don't remove useful ones.
    #     last_jump_position = 0
    #     for command in list_to_update:
    #         section_size += command.get_size()
    #         if section_size + command.get_jump_value() > last_jump_position and command.get_jump_value() > 0:
    #             last_jump_position = section_size + command.get_jump_value()
    #
    #     if last_jump_position > 0:
    #         while section_size <= last_jump_position + 1:
    #             list_to_update.append(copy.deepcopy(new_end))
    #             if len(list_to_update) == 1:
    #                 list_to_update[-1].line_index = 0
    #             else:
    #                 list_to_update[-1].line_index = list_to_update[-2].line_index + 1
    #             section_size += 1
    #     while section_size % 4 != 0 or section_size == 0:
    #         list_to_update.append(copy.deepcopy(new_end))
    #         if len(list_to_update) == 1:
    #             list_to_update[-1].line_index = 0
    #         else:
    #             list_to_update[-1].line_index = list_to_update[-2].line_index + 1
    #         section_size += 1
    #     return list_to_update