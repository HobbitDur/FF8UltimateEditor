import re


class CodePreprocessing:
    """
    A class for preprocessing code by transforming elseif blocks to jump: ELSE with if inside
    and formatting code with proper indentation
    """

    def transform_all_elseif_blocks(self, code_text):
        """
        Transform all elseif blocks in the code to jump: ELSE with if inside

        Args:
            code_text (str): The original code text

        Returns:
            str: The transformed code text
        """
        working_text = code_text
        iteration = 1

        while True:
            # Find the first elseif block
            original_elseif_block, start, end = self._find_first_elseif_block(working_text)

            if not original_elseif_block:
                break

            # Find where the complete logic flow ends
            flow_end_pos = self._find_complete_logic_flow_end(working_text, end)

            # Transform the elseif block
            transformed_block = self._transform_elseif_block_to_jump_else(original_elseif_block)

            # Replace the complete original elseif block with the transformed version
            working_text = self._replace_complete_elseif_block(working_text, original_elseif_block, start, end, transformed_block)

            # Calculate the new flow end position (adjust for the length difference)
            length_difference = len(transformed_block) - len(original_elseif_block)
            new_flow_end_pos = flow_end_pos + length_difference

            # Insert closing brace with newline at the new flow end position
            working_text = self._insert_closing_brace_at_flow_end(working_text, new_flow_end_pos)

            iteration += 1

        return working_text

    def indent_code(self, code_text, indent_size=4):
        """
        Properly indent the pseudo code based on brace nesting
        Ensures opening braces are always on their own line
        Removes all empty lines

        Args:
            code_text (str): The code text to indent
            indent_size (int): Number of spaces per indentation level (default: 4)

        Returns:
            str: The properly indented code
        """
        # First, normalize the code to ensure braces are on separate lines
        normalized_lines = []
        lines = code_text.split('\n')

        for line in lines:
            stripped_line = line.strip()

            # Skip empty lines - DON'T append them to normalized_lines
            if not stripped_line:
                continue  # This removes empty lines

            # Handle lines that contain both code and opening brace
            if '{' in stripped_line and not stripped_line.startswith('{'):
                # Split the line at the opening brace
                parts = stripped_line.split('{', 1)
                # Add the code part (without brace)
                if parts[0].strip():
                    normalized_lines.append(parts[0].strip())
                # Add the opening brace on its own line
                normalized_lines.append('{')
                # If there's anything after the brace, add it on next line
                if parts[1].strip():
                    normalized_lines.append(parts[1].strip())
            # Handle lines that contain both code and closing brace
            elif '}' in stripped_line and not stripped_line.startswith('}'):
                # Split the line at the closing brace
                parts = stripped_line.split('}', 1)
                # Add the code part (without brace)
                if parts[0].strip():
                    normalized_lines.append(parts[0].strip())
                # Add the closing brace on its own line
                normalized_lines.append('}')
                # If there's anything after the brace, add it on next line
                if parts[1].strip():
                    normalized_lines.append(parts[1].strip())
            else:
                # Line is already properly formatted (just brace or just code)
                normalized_lines.append(stripped_line)

        # Now apply indentation to the normalized lines
        indented_lines = []
        current_indent = 0
        indent_str = ' ' * indent_size

        for line in normalized_lines:
            # Skip empty lines - DON'T append them to indented_lines
            # Since we already removed empty lines in normalization, this check might be redundant
            # but it's kept for safety
            if not line:
                continue  # This removes any remaining empty lines

            # Decrease indent before adding line if it's a closing brace
            if line == '}':
                current_indent = max(0, current_indent - 1)

            # Add the line with current indent
            indented_lines.append(indent_str * current_indent + line)

            # Increase indent after adding line if it's an opening brace
            if line == '{':
                current_indent += 1

        return '\n'.join(indented_lines)

    def _find_first_elseif_block(self, code_text):
        """
        Find the first complete elseif block in the code text using regex
        Returns the block text, start position, and end position
        """
        # Find the first elseif: using regex
        elseif_match = re.search(r'elseif:', code_text)
        if not elseif_match:
            return None, -1, -1

        start_pos = elseif_match.start()

        # Find the opening brace after this elseif:
        brace_start = code_text.find("{", start_pos)
        if brace_start == -1:
            return None, -1, -1

        # Count braces to find the matching closing brace
        depth = 1
        current_pos = brace_start + 1

        while current_pos < len(code_text) and depth > 0:
            if code_text[current_pos] == '{':
                depth += 1
            elif code_text[current_pos] == '}':
                depth -= 1
                if depth == 0:
                    break

            current_pos += 1

        if depth == 0:
            end_pos = current_pos + 1
            block_content = code_text[start_pos:end_pos]
            return block_content, start_pos, end_pos
        else:
            return None, -1, -1

    def _get_nesting_level_at_position(self, code_text, position):
        """
        Calculate the nesting level (brace depth) at a given position
        """
        text_before = code_text[:position]
        open_braces = text_before.count('{')
        close_braces = text_before.count('}')
        return open_braces - close_braces

    def _find_complete_logic_flow_end(self, code_text, start_position):
        """
        Find where the complete elseif/else logic flow ends at the same nesting level
        Returns the position where the final block ends
        """
        # Get the nesting level of the starting position
        start_nesting_level = self._get_nesting_level_at_position(code_text, start_position)

        current_pos = start_position
        last_block_end = start_position

        while current_pos < len(code_text):
            # Look for elseif: or jump: Else from current position
            remaining_text = code_text[current_pos:]

            # Check for elseif: (case sensitive)
            elseif_match = re.search(r'elseif:', remaining_text)
            # Check for jump: Else (case insensitive)
            else_match = re.search(r'jump:\s*Else', remaining_text, re.IGNORECASE)

            # Determine which comes first
            next_element_pos = -1
            element_type = None

            if elseif_match and else_match:
                if elseif_match.start() < else_match.start():
                    next_element_pos = current_pos + elseif_match.start()
                    element_type = 'elseif'
                else:
                    next_element_pos = current_pos + else_match.start()
                    element_type = 'else'
            elif elseif_match:
                next_element_pos = current_pos + elseif_match.start()
                element_type = 'elseif'
            elif else_match:
                next_element_pos = current_pos + else_match.start()
                element_type = 'else'
            else:
                # No more elements found
                return last_block_end

            # Check if this element is at the same nesting level as our start
            element_nesting_level = self._get_nesting_level_at_position(code_text, next_element_pos)
            if element_nesting_level != start_nesting_level:
                # This element is at a different nesting level, so we've reached the end of our logic flow
                return last_block_end

            # Find the boundaries of this element's block
            if element_type == 'elseif':
                block_content, block_start, block_end = self._find_elseif_block_from_position(code_text, next_element_pos)
            else:  # else
                block_start, block_end = self._find_else_block_boundaries(code_text, next_element_pos)

            if block_end == -1:
                return last_block_end

            last_block_end = block_end
            current_pos = block_end  # Move to after this block to continue searching

            # If we found an else, this is definitely the end
            if element_type == 'else':
                return block_end

        return last_block_end

    def _find_elseif_block_from_position(self, code_text, start_pos):
        """
        Find elseif block starting from a specific position
        """
        # Find the opening brace after this position
        brace_start = code_text.find("{", start_pos)
        if brace_start == -1:
            return None, -1, -1

        # Count braces to find the matching closing brace
        depth = 1
        current_pos = brace_start + 1

        while current_pos < len(code_text) and depth > 0:
            if code_text[current_pos] == '{':
                depth += 1
            elif code_text[current_pos] == '}':
                depth -= 1
                if depth == 0:
                    break

            current_pos += 1

        if depth == 0:
            end_pos = current_pos + 1
            block_content = code_text[start_pos:end_pos]
            return block_content, start_pos, end_pos
        else:
            return None, -1, -1

    def _find_else_block_boundaries(self, code_text, else_start):
        """
        Find the start and end of an else block
        """
        # Find the opening brace after else
        brace_start = code_text.find("{", else_start)
        if brace_start == -1:
            return -1, -1

        # Count braces to find matching closing brace
        depth = 1
        current_pos = brace_start + 1

        while current_pos < len(code_text) and depth > 0:
            if code_text[current_pos] == '{':
                depth += 1
            elif code_text[current_pos] == '}':
                depth -= 1
                if depth == 0:
                    break

            current_pos += 1

        if depth == 0:
            else_end = current_pos + 1
            return else_start, else_end
        else:
            return -1, -1

    def _transform_elseif_block_to_jump_else(self, elseif_block):
        """
        Transform an elseif block into a jump: ELSE structure with if inside
        """
        # Find the condition part (from 'elseif:' to the opening brace)
        brace_pos = elseif_block.find("{")
        if brace_pos == -1:
            return elseif_block

        # Extract the condition part (remove 'elseif:' and keep the condition)
        condition_part = elseif_block[7:brace_pos].strip()

        # Extract the content inside the braces (everything between { and } but not including them)
        content_start = brace_pos + 1
        content_end = elseif_block.rfind("}")
        if content_end == -1:
            return elseif_block

        content_inside = elseif_block[content_start:content_end].strip()

        # Build the new structure: jump: ELSE { if: condition { content } }
        new_structure = f"jump: ELSE\n{{\nif: {condition_part}\n{{\n{content_inside}\n}}"

        return new_structure

    def _replace_complete_elseif_block(self, code_text, original_elseif_block, start_pos, end_pos, transformed_block):
        """
        Replace the complete original elseif block with the transformed block
        """
        # Replace the block in the original text
        modified_text = code_text[:start_pos] + transformed_block + code_text[end_pos:]

        return modified_text

    def _insert_closing_brace_at_flow_end(self, code_text, flow_end_pos):
        """
        Insert a closing brace } at the end of the logic flow with a newline
        Returns the modified text
        """
        # Insert the closing brace with a newline
        modified_text = code_text[:flow_end_pos] + '\n}' + code_text[flow_end_pos:]

        return modified_text


# Example usage
if __name__ == "__main__":
    # Test with the example
    test_code = """var: Set [varH] to [0] (scope:monster)
add: Add to [varH] value [203] (scope:monster)
if: If with Subject ID [227], LOCAL VAR [varH] [<] [64]
{
    target: Target [RANDOM ENEMY]
    use: Execute ability line [0] (Low - Physical attack | Med - Physical attack | High - Physical attack )
}
elseif: If with Subject ID [227], LOCAL VAR [varH] [<] [128]
{
    if: If with Subject ID [2], RANDOM VALUE BETWEEN 0 AND [2] [==] [0]
    {
        target: Target [SELF]
        use: Execute ability line [1] (Low - Fire | Med - Fira | High - Firaga )
    }
    elseif: If with Subject ID [2], RANDOM VALUE BETWEEN 0 AND [2] [==] [0]
    {
        target: Target [SELF]
        use: Execute ability line [0] (Low - Physical attack | Med - Physical attack | High - Physical attack )
    }
    target: Target [RANDOM ENEMY]
    use: Execute ability line [1] (Low - Fire | Med - Fira | High - Firaga )
}
elseif: If with Subject ID [227], LOCAL VAR [varH] [<] [200]
{
    target: Target [RANDOM ENEMY]
    use: Execute ability line [2] (Low - Thunder | Med - Thundara | High - Thundaga )
}
elseif: If with Subject ID [227], LOCAL VAR [varH] [<] [220]
{
    target: Target [RANDOM ENEMY]
    use: Execute ability line [3] (Low - Reflect | Med - Reflect | High - Reflect )
}
jump: ELSE
{
    target: Target [RANDOM ENEMY]
    use: Execute ability line [4] (Low - Death | Med - Death | High - Death )
}
stop: Stop
stop: Stop
stop: Stop
stop: Stop"""

    # Create an instance and apply the transformation
    preprocessor = CodePreprocessing()

    # Transform the elseif blocks
    transformed_result = preprocessor.transform_all_elseif_blocks(test_code)

    # Indent the transformed code
    indented_result = preprocessor.indent_code(transformed_result)

    print("=== FINAL INDENTED RESULT ===")
    print(indented_result)

    # Test just the indentation on original code
    print("\n=== ORIGINAL CODE WITH INDENTATION ===")
    original_indented = preprocessor.indent_code(test_code)
    print(original_indented)