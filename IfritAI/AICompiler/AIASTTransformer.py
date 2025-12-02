# AIASTTransformer.py
from lark import Transformer
from IfritAI.AICompiler.AIAST import *


class AIASTTransformer(Transformer):
    def __init__(self):
        super().__init__()

    # Terminal values
    def ID(self, token):
        return Value(token.value)

    def NUMBER(self, token):
        return Value(token.value)

    def OPERATOR(self, token):
        return Value(token.value)

    def value(self, items):
        return items[0]

    def param_list(self, items):
        return ParamList(params=items)

    def condition(self, items):
        return Condition(params=items[0])

    def command(self, items):
        name = items[0].value
        # Handle commands with and without parameters
        if len(items) > 1 and items[1] is not None:
            params = items[1]
        else:
            params = None
        return Command(name=name, params=params)

    def block(self, items):
        return Block(statements=items)

    def if_stmt(self, items):
        # The structure is: [if_condition, if_block, *elif_conditions, *elif_blocks, else_block?]
        if_condition = items[0]
        if_block = items[1]

        elif_branches = []
        else_block = None

        # Process remaining items
        i = 2
        while i < len(items):
            if isinstance(items[i], Condition):
                # This is an elseif condition, next should be its block
                if i + 1 < len(items):
                    elif_branches.append(ElifBranch(
                        condition=items[i],
                        block=items[i + 1]
                    ))
                    i += 2
                else:
                    i += 1
            else:
                # This must be the else block
                else_block = items[i]
                i += 1

        return IfStatement(
            condition=if_condition,
            then_block=if_block,
            elif_branches=elif_branches,
            else_block=else_block
        )

    def stmt(self, items):
        return items[0]

    def start(self, items):
        # If there's only one statement, return it directly
        # If there are multiple statements, wrap them in a Block
        if len(items) == 1:
            return items[0]
        else:
            return Block(statements=items)