#!/usr/bin/env python3
"""Run code generator tests step by step"""
import subprocess
import sys
import time


def run_single_test(test_name, description):
    """Run a single test with detailed output"""
    print(f"\n{'=' * 80}")
    print(f"🔍 {description}")
    print(f"{'=' * 80}")
    print(f"Test: {test_name}")
    print(f"{'=' * 80}")

    cmd = [
        sys.executable,
        "-m", "pytest",
        "../tests/test_code_byte_generator.py",
        f"-k {test_name}",
        "-v",  # Verbose
        "-s",  # Show print output
        "--tb=short",  # Short traceback
        "--color=yes",  # Color output
    ]

    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)

    print(f"\n{'=' * 80}")
    if result.returncode == 0:
        print(f"✅ {test_name} PASSED")
    else:
        print(f"❌ {test_name} FAILED")
    print(f"{'=' * 80}")

    time.sleep(1)  # Pause between tests
    return result.returncode


def main():
    """Run tests in order"""
    tests = [
        ("test_generate_simple_command",
         "TEST 1: Simple command - prepareMagic(1)"),

        ("test_generate_command_without_params",
         "TEST 2: Command without parameters - attack()"),

        ("test_generate_if_statement_simple",
         "TEST 3: Simple if statement"),

        ("test_generate_if_else_statement",
         "TEST 4: If-else statement"),

        ("test_generate_multiple_commands",
         "TEST 5: Multiple commands in sequence"),

        ("test_generate_nested_if",
         "TEST 6: Nested if statement"),

        ("test_generate_real_example",
         "TEST 7: Realistic AI script example"),
    ]

    print("\n" + "=" * 80)
    print("🧪 CODE GENERATOR TEST SUITE")
    print("=" * 80)
    print("Testing FF8 assembly byte generation step by step")
    print("=" * 80)

    exit_code = 0
    for test_name, description in tests:
        result = run_single_test(test_name, description)
        if result != 0:
            exit_code = result
            if "-x" in sys.argv:
                print(f"\n🚨 Stopping due to failure (using -x flag)")
                break

    print(f"\n{'=' * 80}")
    if exit_code == 0:
        print("🎉 ALL CODE GENERATOR TESTS COMPLETED SUCCESSFULLY!")
    else:
        print(f"⚠ Some tests failed. Exit code: {exit_code}")
    print(f"{'=' * 80}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()