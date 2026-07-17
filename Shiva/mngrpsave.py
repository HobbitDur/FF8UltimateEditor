"""Shiva's save policy: only the sections a tab edits are rewritten, the rest stay byte for byte.

MngrpManager parses and re-encodes every text section it knows (it is built for ShumiTranslator,
the all-text editor), which would rewrite sections Shiva does not edit and even resize some.
Both the Shiva GUI and the Shiva CLI call this before saving, so a section no editor touched is
left exactly as it was read.
"""
from FF8GameData.GenericSection.section import Section


def keep_unowned_sections_raw(game_data, mngrp, owned_ids):
    """Swap every parsed section not in owned_ids for a plain Section holding the same bytes.

    A plain Section is not re-encoded on save, so MngrpManager emits it unchanged. The section
    keeps its id and offset and the same bytes, so nothing shifts."""
    section_list = mngrp.get_section_list()
    for index, section in enumerate(section_list):
        if section.id == -1 or section.id in owned_ids or type(section) is Section:
            continue  # invalid, owned by an editor, or already raw: leave it
        section_list[index] = Section(game_data=game_data, data_hex=bytearray(section.get_data_hex()),
                                      id=section.id, own_offset=section.own_offset, name=section.name)
