from FF8GameData.gamedata import GameData
from IfritAI.AICompiler.AIAST import Block, IfStatement, Command
from IfritAI.AICompiler.AICompiler import AICompiler


def main():
    game_data = GameData("..\\..\\FF8GameData")
    game_data.load_all()
    compiler = AICompiler(game_data)

    test_code = """
    if (1,2,3,4)  
    {
        prepareMagic(1);
    }
    """

    try:
        # Parse
        tree = compiler.parser.parse(test_code)
        print("Parse successful!")
        print("Parse Tree:")
        print(tree.pretty())

        # Transform to AST
        ast = compiler.transformer.transform(tree)
        print("\nAST created successfully!")

        # Print AST using __str__
        print("\nAST Structure:")
        print(ast)

        # Let's manually verify the AST structure
        print("\nManual verification:")
        if isinstance(ast, Block):
            print(f"Root is a Block with {len(ast.statements)} statements")
            if ast.statements:
                stmt = ast.statements[0]
                if isinstance(stmt, IfStatement):
                    print(f"First statement is an IfStatement")
                    print(f"  Condition has {len(stmt.condition.params.params)} parameters: {[p.value for p in stmt.condition.params.params]}")
                    print(f"  ThenBlock has {len(stmt.then_block.statements)} statements")
                    if stmt.then_block.statements:
                        then_stmt = stmt.then_block.statements[0]
                        if isinstance(then_stmt, Command):
                            print(f"  ThenBlock command: {then_stmt.name} with params: {[p.value for p in then_stmt.params.params]}")
                    print(f"  ElseIf branches: {len(stmt.elif_branches)}")
                    if stmt.else_block:
                        print(f"  ElseBlock has {len(stmt.else_block.statements)} statements")
                    else:
                        print(f"  No ElseBlock")

        # Generate code
        print("\nGenerating FF8 assembly...")
        bytes_output = compiler.generator.generate(ast)

        print(f"\nGenerated {len(bytes_output)} bytes:")
        for i in range(0, len(bytes_output), 16):
            line_bytes = bytes_output[i:i + 16]
            hex_str = ' '.join(f'{b:02X}' for b in line_bytes)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line_bytes)
            print(f"{i:04X}: {hex_str:<48} {ascii_str}")

        # Detailed analysis
        print("\nDetailed byte analysis:")
        i = 0
        while i < len(bytes_output):
            byte = bytes_output[i]

            if byte == 0x02:  # IF command
                print(f"\nPosition {i:04X}: IF command (0x02)")
                print(f"  Position {i + 1:04X}: Subject ID = {bytes_output[i + 1]}")
                print(f"  Position {i + 2:04X}: Parameter type = {bytes_output[i + 2]}")
                print(f"  Position {i + 3:04X}: Comparator = {bytes_output[i + 3]}")
                # Value (2 bytes little-endian)
                value = bytes_output[i + 4] | (bytes_output[i + 5] << 8)
                print(f"  Position {i + 4:04X}-{i + 5:04X}: Value = {value} (0x{value:04X})")
                # Jump offset (2 bytes little-endian)
                jump = bytes_output[i + 6] | (bytes_output[i + 7] << 8)
                print(f"  Position {i + 6:04X}-{i + 7:04X}: Jump offset = {jump} bytes (0x{jump:04X})")
                i += 8  # IF is 7 bytes total

            elif byte == 0x03:  # prepareMagic
                print(f"\nPosition {i:04X}: prepareMagic command (0x03)")
                if i + 1 < len(bytes_output):
                    magic_id = bytes_output[i + 1]
                    print(f"  Position {i + 1:04X}: Magic ID = {magic_id}")
                i += 2

            elif byte == 0x23:  # Jump command (35 decimal = 0x23 hex)
                print(f"\nPosition {i:04X}: Jump command (0x23)")
                if i + 2 < len(bytes_output):
                    jump = bytes_output[i + 1] | (bytes_output[i + 2] << 8)
                    print(f"  Position {i + 1:04X}-{i + 2:04X}: Jump offset = {jump} bytes (0x{jump:04X})")
                i += 3

            else:
                print(f"\nPosition {i:04X}: Unknown byte 0x{byte:02X}")
                i += 1

        # Expected structure
        print("\nExpected structure:")
        print("IF command should be 7 bytes with:")
        print("  - Opcode: 0x02")
        print("  - Condition parameters: [1, 2, 3, 4]")
        print("  - Jump offset: size of prepareMagic(1) command = 2 bytes")
        print("")
        print("prepareMagic command should be 2 bytes with:")
        print("  - Opcode: 0x03")
        print("  - Magic ID: 0x01")

        # Check if jump command appears
        has_jump = any(b == 0x23 for b in bytes_output)
        print(f"\nContains jump command (0x23): {has_jump}")
        if has_jump:
            print("Note: Simple if without else shouldn't need a jump command!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()