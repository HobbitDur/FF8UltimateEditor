"""A whole script section as editable text, and back.

The world-map scripts are short but there are 154 of them, and the interesting work on them -
working out what a script is for, writing that down, then changing it - is text work. So a
section can be written out as a text file, edited in any editor, and read back in.

The format is a rewrite of the one Nihil's browser editor uses, with its two sharp edges taken
off:

- **Jump targets are names, not numbers.** In the binary a ``GOTO`` holds a byte offset counted
  from the start of the section, so inserting one instruction anywhere before it silently sends
  every later jump to the wrong place. Here a jump target is written ``some_label:`` on its own
  line and the jump says ``GOTO some_label``; the offsets are worked out on import, however much
  the text was edited in between.
- **A parameter is written the way the game reads it.** An opcode taking a 16-bit value shows
  that one value (``CHECK_WORLD_MAP_STATE 14``), not the two bytes it is stored as
  (``14, 0``) - which is how ``GOTO 60, 2`` ended up meaning offset 572.

Everything else round-trips: comments, blank lines, indentation and the name given to a script.
Those live in the text file only - the .obj has nowhere to keep them.
"""

import re

from Chocoboy.wmsetscript import (Instruction, OPCODE_BY_NAME, NO_PARAM, WORD,
                                  GOTO_CODE, indent_depths)

MARKER_RE = re.compile(r"^=+\s*Script\s*#?\s*(\d+)\s*(?:\(([^)]*)\))?\s*=*\s*$", re.IGNORECASE)
LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:$")
COMMENT_RE = re.compile(r"^\s*(?:;|//)")

# Control opcodes of the other tool's dialect that mean something else here. Its ELSE is this
# tool's THEN, so a file written for it must not be read as if it were written for this one.
OTHER_DIALECT_NAMES = {"IFBLOCK", "NESTEDIF", "NESTEDELSE", "EXEC", "ENDIF"}

HEADER = [
    "; Chocoboy world-map script export - section {index} ({name})",
    "; {count} script(s). Edit and read back with \"Import from text\".",
    ";",
    "; Keep the \"=== Script #N ===\" lines: they are what separates one script from the next.",
    "; Name a script with \"=== Script #N (what it does) ===\"; the name comes back into the tool.",
    "; A jump target is a \"label:\" line and a jump says \"GOTO label\" - the byte offsets are",
    "; worked out on import, so inserting and deleting instructions cannot break a jump.",
    "; Comments, blank lines and indentation are kept, in this file only: the .obj has no room",
    "; for them, so keep the file if you want to keep them.",
]


def section_to_text(section, section_name):
    """Write every script of one section out, ready to be edited."""
    labels = _label_targets(section)
    lines = [line.format(index=section.index, name=section_name,
                         count=len(section.entry_offsets)) for line in HEADER]
    for entry in range(len(section.entry_offsets)):
        lines.append("")
        name = section.script_names.get(entry)
        lines.append(f"=== Script #{entry} ({name}) ===" if name else f"=== Script #{entry} ===")
        lines.extend(_script_to_lines(section, entry, labels))
    return "\n".join(lines) + "\n"


def _label_targets(section):
    """``instruction index -> label name`` for every instruction some GOTO jumps to."""
    labels = {}
    for instruction in section.instructions:
        if instruction.code != GOTO_CODE:
            continue
        index = section.index_at_offset(instruction.word)
        if index is not None and index not in labels:
            labels[index] = f"label_{len(labels) + 1}"
    return labels


def _script_to_lines(section, entry, labels):
    start, end = section.script_range(entry)
    depths = indent_depths(section, entry)
    lines = []
    for index in range(start, end):
        instruction = section.instructions[index]
        indent = "    " * depths[index - start]
        lines.extend(instruction.comments)
        if index in labels:
            lines.append(f"{indent}{labels[index]}:")
        lines.append(indent + _instruction_to_line(section, instruction, labels))
    lines.extend(section.script_trailing_comments.get(entry, []))
    return lines


def _instruction_to_line(section, instruction, labels):
    opcode = instruction.opcode
    if opcode is None:
        text = f"RAW 0x{instruction.code:04X} {instruction.param1}, {instruction.param2}"
    elif instruction.code == GOTO_CODE:
        target = section.index_at_offset(instruction.word)
        text = f"GOTO {labels[target]}" if target in labels else f"GOTO {instruction.word}"
    elif opcode.params == NO_PARAM:
        # The game ignores both bytes for these, but one of them is not always zero in the
        # shipped file - so they are written out whenever they hold something, and read back.
        text = (opcode.name if not instruction.param1 and not instruction.param2
                else f"{opcode.name} {instruction.param1}, {instruction.param2}")
    elif opcode.params == WORD:
        text = f"{opcode.name} {instruction.word}"
    else:
        text = f"{opcode.name} {instruction.param1}, {instruction.param2}"
    return f"{text} {instruction.trailing}".rstrip() if instruction.trailing else text


class ImportResult:
    """What an import produced, and everything the user should know about it.

    ``scripts`` is None when the text could not be read at all; otherwise it is ready to hand to
    ``ScriptSection.replace_scripts`` and ``errors`` is empty.
    """

    def __init__(self):
        self.scripts = None
        self.names = {}
        self.trailing_comments = {}
        self.errors = []
        self.warnings = []

    @property
    def ok(self):
        return self.scripts is not None and not self.errors


def text_to_section(text):
    """Read a section back from text. The section is only changed when ``result.ok``."""
    result = ImportResult()
    chunks, names = _split_on_markers(text, result)
    if result.errors:
        return result

    scripts = []
    trailing_comments = {}
    label_places = {}  # label name -> (script index, instruction index inside it)
    jumps = []  # (instruction, label name, source line) to resolve once the layout is known
    for script_index, chunk in enumerate(chunks):
        script, leftover = _parse_script(chunk, script_index, result, label_places, jumps)
        scripts.append(script)
        if leftover:
            trailing_comments[script_index] = leftover
    if result.errors:
        return result

    _drop_trailing_padding(scripts)
    offsets = _resolve_labels(scripts, label_places, jumps, result)
    if result.errors:
        return result

    result.scripts = scripts
    result.names = names
    result.trailing_comments = trailing_comments
    result.warnings.append(f"{len(scripts)} script(s), "
                           f"{sum(len(script) for script in scripts)} instruction(s), "
                           f"{len(jumps)} jump(s) pointed at their label.")
    if offsets:
        result.warnings.append("The section is now " + str(offsets) + " bytes of script data.")
    return result


def _split_on_markers(text, result):
    """Cut the text into one chunk of lines per script, on the "=== Script #N ===" lines."""
    chunks = []
    names = {}
    current = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = MARKER_RE.match(line.strip())
        if match:
            if match.group(2):
                names[len(chunks)] = match.group(2).strip()
            current = ([], line_number + 1)
            chunks.append(current)
        elif current is not None:
            current[0].append((line_number, line))
        # lines before the first marker are the header, and are dropped
    if not chunks:
        result.errors.append('No "=== Script #N ===" line found, so there is nothing to read. '
                             "Import the kind of file the Export button writes.")
    return chunks, names


def _parse_script(chunk, script_index, result, label_places, jumps):
    """One script's lines to a list of Instructions, plus whatever comments it ends on."""
    lines, _start = chunk
    script = []
    pending = []  # comment and blank lines waiting for the instruction they sit above
    for line_number, raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or COMMENT_RE.match(raw_line):
            pending.append(raw_line.rstrip())
            continue
        code, trailing = _split_trailing_comment(raw_line)
        code = code.strip()
        if not code:
            pending.append(raw_line.rstrip())
            continue

        label = LABEL_RE.match(code)
        if label:
            name = label.group(1)
            if name in label_places:
                result.errors.append(f"Line {line_number}: the label \"{name}\" is defined twice.")
            label_places[name] = (script_index, len(script))
            continue

        instruction = _parse_instruction(code, line_number, result, jumps)
        if instruction is None:
            continue
        instruction.comments = pending
        instruction.trailing = trailing
        pending = []
        script.append(instruction)
    # pending is what was written after the last instruction. The blank lines at the very end of
    # it are dropped: the export puts one before each script marker of its own, so keeping them
    # would add a blank line every time the section went out to text and came back.
    while pending and not pending[-1].strip():
        pending.pop()
    return script, pending


def _split_trailing_comment(raw_line):
    positions = [raw_line.find(marker) for marker in (";", "//")]
    positions = [position for position in positions if position != -1]
    if not positions:
        return raw_line, ""
    cut = min(positions)
    return raw_line[:cut], raw_line[cut:].rstrip()


def _parse_instruction(code, line_number, result, jumps):
    tokens = [token for token in re.split(r"[\s,]+", code) if token]
    mnemonic = tokens[0].upper()

    if mnemonic == "RAW":
        if len(tokens) < 2:
            result.errors.append(f"Line {line_number}: RAW needs a value, e.g. RAW 0xFF27 5, 1")
            return None
        return Instruction(_parse_number(tokens[1], line_number, result),
                           _parse_number(tokens[2], line_number, result) if len(tokens) > 2 else 0,
                           _parse_number(tokens[3], line_number, result) if len(tokens) > 3 else 0)

    if mnemonic in OTHER_DIALECT_NAMES:
        result.errors.append(
            f"Line {line_number}: \"{mnemonic}\" is the other world-map editor's name for a "
            "control opcode. Do not import its files as they are: its ELSE is this tool's THEN, "
            "so the branches would come out wrong. Export from here first and edit that.")
        return None

    opcode = OPCODE_BY_NAME.get(mnemonic)
    if opcode is None:
        result.errors.append(f"Line {line_number}: \"{tokens[0]}\" is not an instruction. "
                             "Use RAW 0xFFxx p1, p2 to write bytes this tool does not know.")
        return None

    instruction = Instruction(opcode.code)
    if opcode.code == GOTO_CODE:
        if len(tokens) < 2:
            result.errors.append(f"Line {line_number}: GOTO needs a label, e.g. GOTO cleanup")
        elif LABEL_RE.match(tokens[1] + ":"):
            jumps.append((instruction, tokens[1], line_number))
        else:  # a bare number: taken as a section offset, exactly as the binary stores it
            instruction.set_word(_parse_number(tokens[1], line_number, result))
            result.warnings.append(f"Line {line_number}: GOTO {tokens[1]} was kept as a raw "
                                   "section offset. A label is safer - a raw offset does not "
                                   "follow the instruction it points at.")
    elif opcode.params == NO_PARAM:
        if len(tokens) > 1:  # the game ignores them, but they are kept exactly as written
            instruction.param1 = _parse_number(tokens[1], line_number, result) & 0xFF
        if len(tokens) > 2:
            instruction.param2 = _parse_number(tokens[2], line_number, result) & 0xFF
    elif opcode.params == WORD:
        if len(tokens) > 1:
            instruction.set_word(_parse_number(tokens[1], line_number, result))
    else:
        if len(tokens) > 1:
            instruction.param1 = _parse_number(tokens[1], line_number, result) & 0xFF
        if len(tokens) > 2:
            instruction.param2 = _parse_number(tokens[2], line_number, result) & 0xFF
    return instruction


def _parse_number(token, line_number, result):
    try:
        return int(token, 16) if token.lower().startswith("0x") else int(token, 10)
    except ValueError:
        result.errors.append(f"Line {line_number}: \"{token}\" is not a number.")
        return 0


def _drop_trailing_padding(scripts):
    """Take the zero word off the end of the last script.

    The section ends on one, and an export shows it as "RAW 0x0000 0, 0". It is filler, not an
    instruction, and the section writer puts it back on its own - so reading it back in as an
    instruction too would add four bytes on every round trip.
    """
    while scripts and scripts[-1] and scripts[-1][-1].is_padding:
        scripts[-1].pop()
    while scripts and not scripts[-1]:
        scripts.pop()


def _resolve_labels(scripts, label_places, jumps, result):
    """Turn every "GOTO label" into the byte offset that label ends up at."""
    table_size = 4 * (len(scripts) + 1)
    script_base = []
    offset = table_size
    for script in scripts:
        script_base.append(offset)
        offset += 4 * len(script)
    for instruction, name, line_number in jumps:
        place = label_places.get(name)
        if place is None:
            result.errors.append(f"Line {line_number}: there is no label called \"{name}\".")
            continue
        script_index, instruction_index = place
        instruction.set_word(script_base[script_index] + 4 * instruction_index)
    return offset - table_size
