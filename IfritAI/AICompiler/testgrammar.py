from lark import Lark

grammar = r"""
start: stmt+

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
%ignore WS
%ignore "//" /[^\n]/*           // Single-line comments
%ignore "/*" /(.|\n)/* "*/"     // Multi-line comments
"""

parser = Lark(grammar, parser='lalr')

test_code = """
if (1,2,>=,4)
{
    if (1,2,<,4)
    {
        add(0,1);
    }
    statChange(0,200);
    statChange(0,100);
}
elseif (1,2,==,4)
{
    attack();
    target(1);
}
else
{
    attack();
    target(1);
}
attack();
"""

try:
    tree = parser.parse(test_code)
    print("Parse successful!")
    print(tree.pretty())
except Exception as e:
    print(f"Parse error: {e}")