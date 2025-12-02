from lark import Lark

from IfritAI.AICompiler.AIASTTransformer import AIASTTransformer

# Use the same grammar
grammar = r"""
    start: item*

    item: command | block

    command: CMD_NAME ":" command_content ";"
    block: "{" item* "}"

    command_content: (text | param)*
    text: /[^\[\];]+/
    param: "[" param_value "]"
    param_value: /[^\]]+/

    CMD_NAME: /[a-zA-Z_][a-zA-Z0-9_]*/

    %import common.WS
    %ignore WS
"""

parser = Lark(grammar, start='start', parser='lalr')
transformer = AIASTTransformer()

# Test cases
test_cases = [
    # Simple command
    "target: Target [ALL ENEMIES];",

    # If with block
    """if: If with Subject ID [220], LOCAL VAR [varA] [>=] [5];
{
    target: Target [ALL ENEMIES];
}""",

    # If-else
    """if: If with Subject ID [14], GROUP LEVEL OF [ENEMY TEAM] [>=] [1];
{
    target: Target [0];
}
else:;
{
    target: Target [1];
}""",

    # Nested if
    """if: If with Subject ID [220], LOCAL VAR [varA] [>=] [5];
{
    if: If with Subject ID [2], RANDOM VALUE BETWEEN 0 AND [1] [==] [0];
    {
        target: Target [1];
    }
    target: Target [0];
}""",

    """if: If with Subject ID [4], STATUS_SPE OF [SELF] [==] [Aura];
{
    if: If with Subject ID [2], RANDOM VALUE BETWEEN 0 AND [2] [==] [0] ;
    {
        add: Add to [varA] value [1] (scope:monster);
    }
    statChange: Set [Strength] to [200]% of original;
    statChange: Set [Magic] to [200]% of original;
}
else:;
{
    statChange: Set [Strength] to [100]% of original;
    statChange: Set [Magic] to [100]% of original;
}
if: If with Subject ID [2], RANDOM VALUE BETWEEN 0 AND [4] [==] [0] ;
{
    stop: Stop;
}
if: If with Subject ID [9], ALIVE [!=] [Elite Soldier] ;
{
    var: Set [varA] to [1] (scope:monster);
}
else:;
{
    if: If with Subject ID [220], LOCAL VAR [varA] [==] [1] ;
    {
        var: Set [varA] to [0] (scope:monster);
        if: If with Subject ID [2], RANDOM VALUE BETWEEN 0 AND [2] [==] [0] ;
        {
            target: Target [ALL ENEMIES];
            use: Execute ability line [1] (Low - Ray Bomb | Med - Ray Bomb | High - Ray Bomb );
            stop: Stop;
        }
        else:;
        {
            target: Target [RANDOM ENEMY];
            useRandom: Randomly use ability line [0] (Low - Physical attack | Med - Physical attack | High - Physical attack ) or [2] (Low - Micro Missiles | Med - Micro Missiles | High - Micro Missiles ) or [3] (Low - Thundara | Med - Thundara | High - Thundaga );
            stop: Stop;
        }
    }
}
if: If with Subject ID [220], LOCAL VAR [varA] [>=] [5] ;
{
    var: Set [varA] to [1] (scope:monster);
    target: Target [ALL ENEMIES];
    use: Execute ability line [1] (Low - Ray Bomb | Med - Ray Bomb | High - Ray Bomb );
    stop: Stop;
}
target: Target [RANDOM ENEMY];
useRandom: Randomly use ability line [0] (Low - Physical attack | Med - Physical attack | High - Physical attack ) or [0] (Low - Physical attack | Med - Physical attack | High - Physical attack ) or [2] (Low - Micro Missiles | Med - Micro Missiles | High - Micro Missiles );
stop: Stop;
stop: Stop;
stop: Stop;"""
]

print("Testing AST Transformer...")
print("=" * 60)

for i, test_code in enumerate(test_cases, 1):
    print(f"\nTest Case {i}:")
    print("-" * 40)
    print("Input:")
    print(test_code)
    print("\nAST (Abstract Syntax Tree):")
    try:
        tree = parser.parse(test_code)
        ast = transformer.transform(tree)
        print(ast)
        print("✓ SUCCESS")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback

        traceback.print_exc()

    print("-" * 40)