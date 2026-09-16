"""Shared pieces of the section files: the error type and the hex helpers."""


class SectionFileError(ValueError):
    """A section file could not be read or applied. The message names the file and the problem,
    written to be shown as-is to the person who edited the file.

    A ValueError so argparse reports a bad --sections value as a plain command line error rather
    than a traceback."""


def bytes_to_hex(data) -> str:
    """b'\\x01\\xAB' -> '01 AB' (the spelling every xml section file uses for raw bytes)."""
    return ' '.join(f'{byte:02X}' for byte in data)


def hex_to_bytes(text: str, file_path) -> bytearray:
    """'01 AB' -> bytearray(b'\\x01\\xAB'). An empty or missing text is an empty byte stream."""
    if not text or not text.strip():
        return bytearray()
    try:
        return bytearray(int(token, 16) for token in text.split())
    except ValueError:
        raise SectionFileError(f"{file_path}: '{text.strip()[:40]}' is not a list of hexadecimal bytes")


def parse_int(text: str, file_path, what: str) -> int:
    """Read an integer written either in decimal ('144') or in hexadecimal ('0x90')."""
    try:
        text = text.strip()
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except (AttributeError, ValueError):
        raise SectionFileError(f"{file_path}: {what} '{text}' is not an integer")
