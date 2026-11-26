from PyQt6.QtCore import QObject, pyqtSignal

from Common.filebinding import FileBinding
from FF8GameData.font.atlas import FontAtlas
from FF8GameData.font.textlayout import FontMetrics


class PageFontSource(QObject):
    """The menu font as two complementary (read-only) files of a page preview tool (Zone, Moomba):

      * sysfnt.TEX: the glyph pictures (without it, the text is drawn as boxes);
      * sysfnt.tdw: each glyph's width (without it, every glyph is as wide as the widest).

    They are side files like any other, shared through the registry and listed in the Opened files
    panel: the font is only what the user opened, never looked up in some folder. `changed` fires
    after every load / removal, so the tool redraws; apply_to() puts the font in a PageRenderer.
    """

    changed = pyqtSignal()

    NOTICE_TEXT = ("No menu font: the text is drawn as boxes. Open {missing} (beside mngrp.bin in "
                   "the game's menu folder) with the toolbar's \"Import complementary\" button.")

    def __init__(self, file_registry):
        QObject.__init__(self)
        self.tex_binding = FileBinding("sysfnt.TEX", file_registry, file_filter="sysfnt*.TEX",
                                       read_only=True)
        self.tdw_binding = FileBinding("sysfnt.tdw", file_registry, file_filter="sysfnt*.tdw",
                                       read_only=True)
        self.tex_binding.file_opened.connect(self._load_tex)
        self.tex_binding.file_closed.connect(self._clear_tex)
        self.tdw_binding.file_opened.connect(self._load_tdw)
        self.tdw_binding.file_closed.connect(self._clear_tdw)
        self.atlas = None    # FontAtlas of the opened sysfnt.TEX
        self.metrics = None  # FontMetrics of the opened sysfnt.tdw
        self.error = ""      # why the last file opened could not be read

    @property
    def bindings(self):
        return [self.tex_binding, self.tdw_binding]

    def load_opened_files(self):
        """Pick up a font another tool already opened."""
        for binding in self.bindings:
            binding.load_opened_file()

    def apply_to(self, renderer):
        """Give a PageRenderer the opened font (uniform widths / boxes for a missing file)."""
        if renderer is None:
            return
        renderer.metrics = self.metrics if self.metrics is not None else FontMetrics(widths=None)
        renderer.atlas = self.atlas

    def notice(self):
        """What the preview says about its font: "" when both files are open."""
        if self.error:
            return self.error
        missing = [name for name, loaded in (("sysfnt.TEX", self.atlas is not None),
                                             ("sysfnt.tdw", self.metrics is not None)) if not loaded]
        if not missing:
            return ""
        if self.atlas is not None:  # glyphs but no widths
            return ("No sysfnt.tdw: every glyph is drawn as wide as the widest. Open it (beside "
                    "mngrp.bin in the game's menu folder) with the toolbar's \"Import complementary\" "
                    "button.")
        return self.NOTICE_TEXT.format(missing=" and ".join(missing))

    def _load_tex(self, file_name):
        try:
            self.atlas = FontAtlas.from_file(file_name)
            self.error = ""
        except (OSError, ValueError) as e:
            self.atlas = None
            self.error = f"Could not read {file_name}: {e}"
        self.changed.emit()

    def _load_tdw(self, file_name):
        try:
            with open(file_name, "rb") as tdw_file:
                self.metrics = FontMetrics.from_tdw_bytes(tdw_file.read())
            self.error = ""
        except OSError as e:
            self.metrics = None
            self.error = f"Could not read {file_name}: {e}"
        self.changed.emit()

    def _clear_tex(self, *_args):
        self.atlas = None
        self.error = ""
        self.changed.emit()

    def _clear_tdw(self, *_args):
        self.metrics = None
        self.error = ""
        self.changed.emit()
