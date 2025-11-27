import re


class CodePostprocessing:
    """
    A class for postprocessing code by transforming "jump: ELSE { if: ... }" patterns to "elseif: ..."
    """

    @staticmethod
    def postprocessing_code_txt(code_text):
        """
        Transform "jump: ELSE { if: ... }" patterns to "elseif: ..."
        Handles HTML formatting and proper brace counting.
        """
        working_text = code_text
        while True:
            # Matches: jump:...Else...{
            pattern = re.compile(r'jump:.*?ELSE.*?\{', re.MULTILINE | re.IGNORECASE | re.DOTALL)
            match = pattern.search(working_text)
            if not match:
                break

            start = match.start()
            match_end = match.end()
            depth = 1  # found one '{'
            current_text_read = ""
            # Scan ahead to find the matching closing brace
            while match_end < len(working_text) and depth > 0:
                if working_text[match_end] == '{':
                    depth += 1
                elif working_text[match_end] == '}':
                    depth -= 1
                current_text_read += code_text[match_end]
                match_end += 1

            if depth == 0:
                else_blocks = working_text[start:match_end]
            else:
                else_blocks = ""

            pattern = r'jump:\s*ELSE(?:\s|&nbsp;|<br/>)*{(?:\s|&nbsp;|<br/>)*if:'

            else_blocks_modified, count = re.subn(pattern, 'elseif:', else_blocks, count=1, flags=re.IGNORECASE | re.DOTALL)
            if count == 0:  # It's a end without an if after, so just remove it from the work in progress string
                working_text = working_text.replace(else_blocks, '')
                continue
            # Removing last }
            if count > 0:
                text = else_blocks_modified
                last_index = text.rfind('}<br/>')
                if last_index != -1:
                    # Remove 5 characters: '}' + '<br/>' (total 5 chars)
                    else_blocks_modified = text[:last_index] + text[last_index + 6:]
            code_text = code_text.replace(else_blocks, else_blocks_modified, 1)
            working_text = working_text.replace(else_blocks, else_blocks_modified, 1)

        return code_text

    @staticmethod
    def format_c_style_indentation(html_text):
        """
        Comprehensive C-style formatting that properly handles elseif: statements.
        """
        # Step 1: Completely remove all existing indentation
        cleaned_text = re.sub(r'(&nbsp;)+', '', html_text)  # Remove all &nbsp;
        cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)  # Normalize spaces
        cleaned_text = re.sub(r'\s+<br/>\s+', '<br/>', cleaned_text)  # Clean around <br/>

        lines = cleaned_text.split('<br/>')
        formatted_lines = []
        indent_level = 0

        i = 0
        while i < len(lines):
            original_line = lines[i].strip()

            if not original_line:
                formatted_lines.append('')
                i += 1
                continue

            # Remove any remaining whitespace
            line = original_line.strip()

            # Check line type
            is_elseif = line.startswith('elseif:')
            is_control = line.startswith(('if:', 'elseif:', 'jump:'))

            # Count braces in this exact line
            open_braces = line.count('{')
            close_braces = line.count('}')

            # Calculate current indentation level
            current_indent = max(0, indent_level - close_braces)
            indent = "&nbsp;" * (4 * current_indent)

            # Format the line with proper indentation
            formatted_line = indent + line
            formatted_lines.append(formatted_line)

            # Update indent level for next lines
            indent_level = current_indent + open_braces

            i += 1

        transformed_text = '<br/>'.join(formatted_lines)
        return transformed_text


# Example usage and testing
if __name__ == "__main__":
    # Test code with jump: ELSE patterns
    test_code = """if: If with Subject ID <span style="color:#0055ff;">[4]</span>, STATUS_SPE OF <span style="color:#0055ff;">[SELF]</span> <span style="color:#0055ff;">[==]</span> <span style="color:#0055ff;">[Aura]</span>  <br/>{<br/>&nbsp;&nbsp;&nbsp;&nbsp;statChange: Set <span style="color:#0055ff;">[Strength]</span> to <span style="color:#0055ff;">[200]</span>% of original<br/>&nbsp;&nbsp;&nbsp;&nbsp;statChange: Set <span style="color:#0055ff;">[Magic]</span> to <span style="color:#0055ff;">[200]</span>% of original<br/>}<br/>jump: ELSE<br/>{<br/>&nbsp;&nbsp;&nbsp;&nbsp;statChange: Set <span style="color:#0055ff;">[Strength]</span> to <span style="color:#0055ff;">[100]</span>% of original<br/>&nbsp;&nbsp;&nbsp;&nbsp;statChange: Set <span style="color:#0055ff;">[Magic]</span> to <span style="color:#0055ff;">[100]</span>% of original<br/>}<br/>if: If with Subject ID <span style="color:#0055ff;">[2]</span>, RANDOM VALUE BETWEEN 0 AND <span style="color:#0055ff;">[2]</span> <span style="color:#0055ff;">[==]</span> <span style="color:#0055ff;">[0]</span>  <br/>{<br/>&nbsp;&nbsp;&nbsp;&nbsp;stop: Stop<br/>}<br/>if: If with Subject ID <span style="color:#0055ff;">[9]</span>, ALIVE <span style="color:#0055ff;">[!=]</span> <span style="color:#0055ff;">[Elite Soldier]</span>  <br/>{<br/>&nbsp;&nbsp;&nbsp;&nbsp;var: Set <span style="color:#0055ff;">[varA]</span> to <span style="color:#0055ff;">[1]</span> (scope:monster)<br/>}<br/>jump: ELSE<br/>{<br/>&nbsp;&nbsp;&nbsp;&nbsp;if: If with Subject ID <span style="color:#0055ff;">[220]</span>, LOCAL VAR <span style="color:#0055ff;">[varA]</span> <span style="color:#0055ff;">[==]</span> <span style="color:#0055ff;">[1]</span>  <br/>&nbsp;&nbsp;&nbsp;&nbsp;{<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;var: Set <span style="color:#0055ff;">[varA]</span> to <span style="color:#0055ff;">[0]</span> (scope:monster)<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;if: If with Subject ID <span style="color:#0055ff;">[2]</span>, RANDOM VALUE BETWEEN 0 AND <span style="color:#0055ff;">[2]</span> <span style="color:#0055ff;">[==]</span> <span style="color:#0055ff;">[0]</span>  <br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;target: Target <span style="color:#0055ff;">[ALL ENEMIES]</span><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;use: Execute ability line <span style="color:#0055ff;">[1]</span> (Low - Ray Bomb | Med - Ray Bomb | High - Ray Bomb )<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;stop: Stop<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;jump: ELSE<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;target: Target <span style="color:#0055ff;">[RANDOM ENEMY]</span><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;useRandom: Randomly use ability line <span style="color:#0055ff;">[0]</span> (Low - Physical attack | Med - Physical attack | High - Physical attack ) or <span style="color:#0055ff;">[2]</span> (Low - Micro Missiles | Med - Micro Missiles | High - Micro Missiles ) or <span style="color:#0055ff;">[3]</span> (Low - Thundara | Med - Thundara | High - Thundaga )<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;stop: Stop<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}<br/>&nbsp;&nbsp;&nbsp;&nbsp;}<br/>}<br/>if: If with Subject ID <span style="color:#0055ff;">[220]</span>, LOCAL VAR <span style="color:#0055ff;">[varA]</span> <span style="color:#0055ff;">[&gt;=]</span> <span style="color:#0055ff;">[5]</span>  <br/>{<br/>&nbsp;&nbsp;&nbsp;&nbsp;var: Set <span style="color:#0055ff;">[varA]</span> to <span style="color:#0055ff;">[1]</span> (scope:monster)<br/>&nbsp;&nbsp;&nbsp;&nbsp;target: Target <span style="color:#0055ff;">[ALL ENEMIES]</span><br/>&nbsp;&nbsp;&nbsp;&nbsp;use: Execute ability line <span style="color:#0055ff;">[1]</span> (Low - Ray Bomb | Med - Ray Bomb | High - Ray Bomb )<br/>&nbsp;&nbsp;&nbsp;&nbsp;stop: Stop<br/>}<br/>target: Target <span style="color:#0055ff;">[RANDOM ENEMY]</span><br/>useRandom: Randomly use ability line <span style="color:#0055ff;">[0]</span> (Low - Physical attack | Med - Physical attack | High - Physical attack ) or <span style="color:#0055ff;">[0]</span> (Low - Physical attack | Med - Physical attack | High - Physical attack ) or <span style="color:#0055ff;">[2]</span> (Low - Micro Missiles | Med - Micro Missiles | High - Micro Missiles )<br/>stop: Stop<br/>stop: Stop<br/>stop: Stop<br/>stop: Stop<br/>stop: Stop<br/>"""

    print("=== ORIGINAL CODE ===")
    print(test_code)
    print("\n" + "=" * 50 + "\n")

    # Apply postprocessing
    processed_code = CodePostprocessing.postprocessing_code_txt(test_code)

    print("=== PROCESSED CODE (with elseif) ===")
    print(processed_code)
    print("\n" + "=" * 50 + "\n")

    # Test with a simpler example to show the transformation clearly
    simple_test_code = """
if: If with Subject ID [3], COMBAT SCENE [==] [1]
{
    target: [Squall]
}
jump: ELSE
{
    if: If with Subject ID [3], COMBAT SCENE [==] [1]
    {
          target: [Squall]
    }
    jump: ELSE
    {
        if: If with Subject ID [3], COMBAT SCENE [==] [1]
        {
              target: [Squall]
        }
    }
}
"""

    print("=== SIMPLE TEST - ORIGINAL ===")
    print(simple_test_code)
    print("\n" + "=" * 50 + "\n")

    simple_processed = CodePostprocessing.postprocessing_code_txt(simple_test_code)

    print("=== SIMPLE TEST - PROCESSED ===")
    print(simple_processed)