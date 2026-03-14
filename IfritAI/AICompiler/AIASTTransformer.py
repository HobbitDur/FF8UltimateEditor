# AIASTTransformer.py
from lark import Transformer, Token
from IfritAI.AICompiler.AIAST import *


class AIASTTransformer(Transformer):
    def __init__(self):
        super().__init__()

    # Terminal values
    def ID(self, token):
        return Value(token.value)

    def NUMBER(self, token):
        return Value(str(int(token.value, 0)))

    def OPERATOR(self, token):
        return Value(token.value)

    def STRING(self, token):
        return Value(str(token.value))

    def COMMENT(self, token):
        # Simply return our new Comment node
        return Comment(text=str(token))

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
        # Filter out the Lark Tokens (IF, ELSEIF, ELSE)
        # We only want the AST nodes (Condition, Block)
        nodes = [item for item in items if not isinstance(item, Token)]

        # Now nodes[0] is the if_condition, nodes[1] is the if_block
        if_condition = nodes[0]
        if_block = nodes[1]

        elif_branches = []
        else_block = None

        i = 2
        while i < len(nodes):
            if isinstance(nodes[i], Condition):
                if i + 1 < len(nodes):
                    elif_branches.append(ElifBranch(
                        condition=nodes[i],
                        block=nodes[i + 1]
                    ))
                    i += 2
                else:
                    i += 1
            else:
                else_block = nodes[i]
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
        # Filter out None if any empty items sneak in
        items = [item for item in items if item is not None]
        if len(items) == 1:
            return items[0]
        else:
            return Block(statements=items)