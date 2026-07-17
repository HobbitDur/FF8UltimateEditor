"""The refine abilities of mngrp.bin, read from a shared MngrpManager.

No Qt here: the Shiva tab and the CLI both read the refine data this way, so they cannot
disagree on how the entries and their text line up.
"""


class RefineView:
    """One refine ability: a data block of a m00x bin section, with the entries of that block
    and the text objects of its msg section holding their text.

    The entries and the texts belong to the shared mngrp and are edited in place: the m00x
    sections keep the text of an entry in another section (the msg one), the two lined up by
    position. The offsets between them are recomputed when the file is written."""

    def __init__(self, bin_name, data, entries, texts, input_type, output_type):
        self.bin_name = bin_name
        self.name = data.name
        self.description = data.description
        self.entries = entries
        self.texts = texts  # One FF8Text per entry, same order
        self.input_type = input_type
        self.output_type = output_type


def build_refine_views(manager):
    """Line the entries of each m00x bin section up with the text of its msg section.

    Both are walked block by block then entry by entry, which is the order the offsets between
    them are rebuilt in (m00XManager.update_offset)."""
    refine_views = []
    for bin_section, msg_section in zip(manager.m00_manager.get_bin_list(),
                                        manager.m00_manager.get_msg_list()):
        texts = msg_section.get_text_list()
        index_text = 0
        for data in bin_section.m00bin.list_data:
            refine_views.append(RefineView(
                bin_name=bin_section.m00bin.name, data=data, entries=data.entries,
                texts=texts[index_text:index_text + len(data.entries)],
                input_type=bin_section.m00bin.input_id, output_type=bin_section.m00bin.output_id))
            index_text += len(data.entries)
    return refine_views
