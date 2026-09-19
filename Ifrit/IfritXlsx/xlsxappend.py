"""Add monster sheets to an existing monster xlsx, in place, without rewriting the rest of it.

A modder edits the monster workbook by hand (Excel, LibreOffice), and it holds a stat chart per
monster and a drop-down per name column: a spreadsheet library that reads and saves it loses
things. So, like xlsxnames, the file is patched at the zip level instead. The new sheets are
written first into a separate workbook by the usual writer (IfritManager.dat_to_xlsx), then moved
across: each sheet with its drawing and chart, its texts added to the target's shared-string table
and its cell formats added to the target's style table. Every sheet already there is copied over
byte for byte.

The new sheets go where their monster id puts them (0 before 1, 127 between 126 and 128, 144 after
143), always before ref_data.
"""
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr, unescape

from Ifrit.IfritXlsx.xlsxmanager import REF_DATA_SHEET_TITLE
from Ifrit.IfritXlsx.xlsxnames import SHARED_STRINGS, _replace_workbook

WORKBOOK = "xl/workbook.xml"
WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"
STYLES = "xl/styles.xml"

SHEET_PATTERN = re.compile(r"<sheet\b[^>]*/>")
SI_PATTERN = re.compile(r"<si>.*?</si>|<si/>", re.S)
TEXT_PATTERN = re.compile(r"<t[^>]*>([^<]*)</t>")
CELL_PATTERN = re.compile(r"<c\b([^>]*?)(/>|>(.*?)</c>)", re.S)

CONTENT_TYPE = {
    "sheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
    "drawing": "application/vnd.openxmlformats-officedocument.drawing+xml",
    "chart": "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
}


def _attribute(tag: str, name: str):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return unescape(match.group(1), {"&quot;": '"'}) if match else None


def _sheets(files) -> list:
    """[(name, sheet element, zip path)] of a workbook, in tab order."""
    book = files[WORKBOOK].decode("utf8")
    rels = files[WORKBOOK_RELS].decode("utf8")
    sheets = []
    for tag in SHEET_PATTERN.findall(book):
        rel_id = _attribute(tag, "r:id")
        target = re.search(rf'Id="{rel_id}"[^>]*Target="([^"]+)"', rels) or \
            re.search(rf'Target="([^"]+)"[^>]*Id="{rel_id}"', rels)
        path = target.group(1).lstrip("/")
        sheets.append((_attribute(tag, "name"), tag, path if path.startswith("xl/") else "xl/" + path))
    return sheets


def _monster_id(sheet_name):
    match = re.match(r"\s*(\d+)", sheet_name or "")
    return int(match.group(1)) if match else None


def _shared_texts(shared: str) -> list:
    """Every entry of a shared-string table, in order (one per <si>, whatever runs it holds)."""
    return ["".join(unescape(text) for text in TEXT_PATTERN.findall(si)) for si in SI_PATTERN.findall(shared)]


class _SharedStrings:
    """The target's shared-string table, growing as texts are added."""

    def __init__(self, shared: str):
        self.xml = shared
        self.places = {}
        for index, text in enumerate(_shared_texts(shared)):
            self.places.setdefault(text, index)
        self.count = len(SI_PATTERN.findall(shared))
        self.added = ""

    def place(self, text: str) -> int:
        if text not in self.places:
            self.places[text] = self.count
            self.added += f"<si><t xml:space=\"preserve\">{escape(text)}</t></si>"
            self.count += 1
        return self.places[text]

    def result(self) -> str:
        if not self.added:
            return self.xml
        xml = self.xml.replace("</sst>", self.added + "</sst>")
        return re.sub(r'uniqueCount="\d+"', f'uniqueCount="{self.count}"', xml, count=1)


def _block(styles: str, tag: str):
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>|<{tag}\b[^>]*/>", styles, re.S)
    return match


def _elements(block_xml: str, tag: str) -> list:
    return re.findall(rf"<{tag}\b[^>]*?(?:/>|>.*?</{tag}>)", block_xml or "", re.S)


class _Styles:
    """Adds the source workbook's cell formats to the target's style table, mapping each source
    format index to a target one. Fonts, fills, borders and number formats are reused when the
    target already has the same one."""

    LISTS = (("fonts", "font", "fontId"), ("fills", "fill", "fillId"), ("borders", "border", "borderId"))

    def __init__(self, source_styles: str, target_styles: str):
        self.source = source_styles
        self.target = target_styles
        self.map = {}
        self.source_xfs = _elements(_block(source_styles, "cellXfs").group(1), "xf")
        self.source_items = {tag: _elements((_block(source_styles, group) or [None, ""])[1] or "", tag)
                             for group, tag, _ in self.LISTS}
        self.source_formats = {_attribute(f, "numFmtId"): _attribute(f, "formatCode")
                               for f in _elements((_block(source_styles, "numFmts") or [None, ""])[1] or "", "numFmt")}

    def _target_list(self, group, tag):
        match = _block(self.target, group)
        return _elements(match.group(1) if match and match.group(1) is not None else "", tag)

    def _add_to_group(self, group, tag, element) -> int:
        items = self._target_list(group, tag)
        if element in items:
            return items.index(element)
        match = _block(self.target, group)
        if match is None:
            raise ValueError(f"The target workbook has no <{group}> table")
        whole = match.group(0)
        grown = (whole.replace(f"</{group}>", element + f"</{group}>") if whole.endswith(f"</{group}>")
                 else whole[:-2] + ">" + element + f"</{group}>")
        grown = re.sub(r'count="\d+"', f'count="{len(items) + 1}"', grown, count=1)
        self.target = self.target.replace(whole, grown, 1)
        return len(items)

    def _number_format(self, source_id: str) -> str:
        if source_id is None or int(source_id) < 164:
            return source_id                     # built-in format, same id everywhere
        code = self.source_formats.get(source_id)
        formats = _elements((_block(self.target, "numFmts") or [None, ""])[1] or "", "numFmt")
        for existing in formats:
            if _attribute(existing, "formatCode") == code:
                return _attribute(existing, "numFmtId")
        new_id = str(max([163] + [int(_attribute(f, "numFmtId")) for f in formats]) + 1)
        element = f'<numFmt numFmtId="{new_id}" formatCode={quoteattr(code)}/>'
        if _block(self.target, "numFmts") is None:
            self.target = re.sub(r"(<styleSheet\b[^>]*>)", r"\1" + f'<numFmts count="1">{element}</numFmts>',
                                 self.target, count=1)
        else:
            self._add_to_group("numFmts", "numFmt", element)
        return new_id

    def target_index(self, source_index: int) -> int:
        if source_index in self.map:
            return self.map[source_index]
        xf = self.source_xfs[source_index]
        for group, tag, attribute in self.LISTS:
            source_id = _attribute(xf, attribute)
            if source_id is not None:
                new_id = self._add_to_group(group, tag, self.source_items[tag][int(source_id)])
                xf = re.sub(rf'\b{attribute}="\d+"', f'{attribute}="{new_id}"', xf, count=1)
        number_format = _attribute(xf, "numFmtId")
        if number_format is not None:
            xf = re.sub(r'\bnumFmtId="\d+"', f'numFmtId="{self._number_format(number_format)}"', xf, count=1)
        xf = re.sub(r'\bxfId="\d+"', 'xfId="0"', xf)            # the target's default cell style
        xfs = self._target_list("cellXfs", "xf")
        self.map[source_index] = self._add_to_group("cellXfs", "xf", xf) if xf not in xfs else xfs.index(xf)
        return self.map[source_index]


def _next_number(files, prefix: str) -> int:
    numbers = [int(match.group(1)) for name in files
               if (match := re.fullmatch(re.escape(prefix) + r"(\d+)\.xml", name))]
    return max(numbers, default=0) + 1


def _add_override(content_types: str, part: str, kind: str) -> str:
    return content_types.replace(
        "</Types>", f'<Override PartName="/{part}" ContentType="{CONTENT_TYPE[kind]}"/></Types>')


def append_sheets(target_xlsx, source_xlsx) -> list:
    """Add to `target_xlsx` every monster sheet of `source_xlsx` whose name it does not have yet
    (ref_data is never copied). Returns the names of the sheets added, in id order. The target is
    left untouched when there is nothing to add."""
    with zipfile.ZipFile(source_xlsx) as source:
        source_files = {name: source.read(name) for name in source.namelist()}
    with zipfile.ZipFile(target_xlsx) as target:
        entries = [(info, target.read(info.filename)) for info in target.infolist()]
    files = {info.filename: content for info, content in entries}

    have = {name for name, _, _ in _sheets(files)}
    wanted = [(name, path) for name, _, path in _sheets(source_files)
              if name != REF_DATA_SHEET_TITLE and name not in have]
    if not wanted:
        return []
    wanted.sort(key=lambda item: (_monster_id(item[0]) is None, _monster_id(item[0]) or 0))

    shared = _SharedStrings(files[SHARED_STRINGS].decode("utf8"))
    source_texts = _shared_texts(source_files[SHARED_STRINGS].decode("utf8"))
    styles = _Styles(source_files[STYLES].decode("utf8"), files[STYLES].decode("utf8"))
    book = files[WORKBOOK].decode("utf8")
    rels = files[WORKBOOK_RELS].decode("utf8")
    content_types = files[CONTENT_TYPES].decode("utf8")
    new_parts = {}

    def remap_cell(match):
        attributes, body = match.group(1), match.group(3)
        style = _attribute(attributes, "s")
        if style is not None:
            attributes = re.sub(r'\bs="\d+"', f's="{styles.target_index(int(style))}"', attributes, count=1)
        if body is not None and _attribute(attributes, "t") == "s":
            index = re.search(r"<v>(\d+)</v>", body)
            if index:
                body = body.replace(index.group(0), f"<v>{shared.place(source_texts[int(index.group(1))])}</v>", 1)
        return f"<c{attributes}" + (f">{body}</c>" if body is not None else "/>")

    added = []
    for name, source_path in wanted:
        sheet = source_files[source_path].decode("utf8")
        sheet = CELL_PATTERN.sub(remap_cell, sheet)
        sheet = re.sub(r'(<row\b[^>]*?\bs=")(\d+)(")',
                       lambda m: m.group(1) + str(styles.target_index(int(m.group(2)))) + m.group(3), sheet)
        sheet = re.sub(r'(<col\b[^>]*?\bstyle=")(\d+)(")',
                       lambda m: m.group(1) + str(styles.target_index(int(m.group(2)))) + m.group(3), sheet)
        sheet = sheet.replace(' tabSelected="1"', "")

        all_parts = {**files, **new_parts}
        sheet_number = _next_number(all_parts, "xl/worksheets/sheet")
        sheet_path = f"xl/worksheets/sheet{sheet_number}.xml"
        source_rels_path = source_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
        if source_rels_path in source_files:
            sheet_rels = source_files[source_rels_path].decode("utf8")
            for drawing_target in re.findall(r'Target="\.\./drawings/(drawing\d+\.xml)"', sheet_rels):
                drawing = source_files["xl/drawings/" + drawing_target]
                drawing_number = _next_number({**files, **new_parts}, "xl/drawings/drawing")
                new_drawing = f"xl/drawings/drawing{drawing_number}.xml"
                drawing_rels_path = f"xl/drawings/_rels/{drawing_target}.rels"
                if drawing_rels_path in source_files:
                    drawing_rels = source_files[drawing_rels_path].decode("utf8")
                    for chart_target in re.findall(r'Target="\.\./charts/(chart\d+\.xml)"', drawing_rels):
                        chart_number = _next_number({**files, **new_parts}, "xl/charts/chart")
                        new_chart = f"chart{chart_number}.xml"
                        new_parts["xl/charts/" + new_chart] = source_files["xl/charts/" + chart_target]
                        content_types = _add_override(content_types, "xl/charts/" + new_chart, "chart")
                        drawing_rels = drawing_rels.replace(f"../charts/{chart_target}\"",
                                                            f"../charts/{new_chart}\"")
                    new_parts[f"xl/drawings/_rels/drawing{drawing_number}.xml.rels"] = drawing_rels.encode("utf8")
                new_parts[new_drawing] = drawing
                content_types = _add_override(content_types, new_drawing, "drawing")
                sheet_rels = sheet_rels.replace(f"../drawings/{drawing_target}\"",
                                                f"../drawings/drawing{drawing_number}.xml\"")
            new_parts[f"xl/worksheets/_rels/sheet{sheet_number}.xml.rels"] = sheet_rels.encode("utf8")
        new_parts[sheet_path] = sheet.encode("utf8")
        content_types = _add_override(content_types, sheet_path, "sheet")

        used_ids = {int(n) for n in re.findall(r'Id="rId(\d+)"', rels)}
        rel_id = f"rId{max(used_ids, default=0) + 1}"
        rels = rels.replace("</Relationships>",
                            f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/'
                            f'officeDocument/2006/relationships/worksheet" '
                            f'Target="worksheets/sheet{sheet_number}.xml"/></Relationships>')
        sheet_id = max(int(_attribute(tag, "sheetId")) for tag in SHEET_PATTERN.findall(book)) + 1
        element = f'<sheet name={quoteattr(name)} sheetId="{sheet_id}" state="visible" r:id="{rel_id}"/>'
        # In id order, before the first sheet with a higher id or ref_data
        new_id = _monster_id(name)
        anchor = None
        for tag in SHEET_PATTERN.findall(book):
            existing_id = _monster_id(_attribute(tag, "name"))
            if existing_id is None or (new_id is not None and existing_id > new_id):
                anchor = tag
                break
        book = book.replace(anchor, element + anchor, 1) if anchor else book.replace("</sheets>", element + "</sheets>", 1)
        added.append(name)

    files[SHARED_STRINGS] = shared.result().encode("utf8")
    files[STYLES] = styles.target.encode("utf8")
    files[WORKBOOK] = book.encode("utf8")
    files[WORKBOOK_RELS] = rels.encode("utf8")
    files[CONTENT_TYPES] = content_types.encode("utf8")
    files.update(new_parts)
    template = entries[0][0]
    for part in new_parts:
        info = zipfile.ZipInfo(part, date_time=template.date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        entries.append((info, None))
    _replace_workbook(target_xlsx, entries, files)
    return added
