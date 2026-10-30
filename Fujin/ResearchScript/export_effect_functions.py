"""Refresh Fujin's native-code snapshot (FF8GameData/Resources/json/magic_effect.json) from the
English IDA database - export only, the database is never changed.

For every effect slot of the dispatch tables (MagicList_Logic / MagicList_TextureLoad), it writes
the initializer and loader names, the file names the loader references, and each of the effect's
own functions: name, address, function comment and Hex-Rays pseudocode. An effect's functions are
those dump_magic_effects.spell_local_functions() reaches from its initializer (calls and task
callbacks), plus every function named MAG_<effect>_* that the walk does not reach. The "_snapshot"
entry records which database it came from and when.

Fujin reads the json at runtime and never needs IDA. Re-run this whenever the IDB has been
improved (new names, comments):

    Headless, on a COPY of the saved .i64 (the open database is never touched), with IDA 9's
    idalib (IDADIR = the IDA install; IDAUSR = an empty folder keeps user plugins such as the MCP
    server from starting):
        set IDADIR=C:\\Program Files\\IDA Professional 9.2
        set PYTHONPATH=%IDADIR%\\idalib\\python
        python Fujin/ResearchScript/export_effect_functions.py --idb D:\\FF8_EN.exe.i64

    Or inside IDA: File > Script file... > this file (writes the json of this checkout).

dump_magic_effects.py stays the script that also renames variables in the IDB; this one only reads.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "FF8GameData" / "Resources" / "json" / "magic_effect.json"
# The pseudocode (about 23 MB, one copy per function address) goes to a gzip file beside the index,
# which Fujin opens only when Native code shows a function (EffectCatalog.pseudocode).
CODE_NAME = "magic_effect_code.json.gz"
AUDIT_BLOCK = re.compile(r"\[FF8_EFFECT_AUDIT\].*?\[/FF8_EFFECT_AUDIT\]\s*", re.S)  # sync_effect_ida's own text


def _function_comment(ea):
    import idc
    parts = [idc.get_func_cmt(ea, False) or "", idc.get_func_cmt(ea, True) or ""]
    # the regular and the repeatable comment, once each (a tool may write the same text in both)
    kept = []
    for part in (part.strip() for part in parts):
        if part and part not in kept:
            kept.append(part)
    text = "\n\n".join(kept)
    return AUDIT_BLOCK.sub("", text).strip()   # the audit text comes from this json: not fed back


def export(idb_label, idb_saved):
    """Build the snapshot from the database open in this process."""
    import ida_bytes
    import ida_hexrays
    import idautils
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dump_magic_effects as walk   # its helpers only: main() runs when IDA runs that script

    if not ida_hexrays.init_hexrays_plugin():
        raise RuntimeError("the Hex-Rays decompiler is not available")
    by_prefix = {}
    for ea in idautils.Functions():
        match = re.match(r"MAG_(\d{3})_", walk.function_name(ea))
        if match:
            by_prefix.setdefault(int(match[1]), []).append(ea)
    effects = {"_snapshot": {
        "source": idb_label,
        "idb_saved": idb_saved,
        "exported": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "script": "Fujin/ResearchScript/export_effect_functions.py",
    }}
    for slot in range(walk.SLOT_COUNT):
        effect_id = slot + 1
        init_addr = ida_bytes.get_dword(walk.MAGIC_LIST_LOGIC + 4 * slot)
        fl_addr = ida_bytes.get_dword(walk.MAGIC_LIST_TEXTURE_LOAD + 4 * slot)
        if init_addr == 0 and fl_addr == 0:
            effects[str(effect_id)] = {"free": True}
            continue
        reached = walk.spell_local_functions(init_addr) if init_addr else []
        named = sorted(ea for ea in by_prefix.get(effect_id, []) if ea not in reached and ea != fl_addr)
        functions = []
        for ea in reached + named:
            entry = {"addr": "0x%X" % ea, "name": walk.function_name(ea),
                     "pseudocode": walk.decompile_text(ea)}
            comment = _function_comment(ea)
            if comment:
                entry["comment"] = comment
            functions.append(entry)
        effects[str(effect_id)] = {
            "free": False,
            "logic_addr": "0x%X" % init_addr,
            "logic_name": walk.function_name(init_addr),
            "fl_addr": "0x%X" % fl_addr,
            "fl_name": walk.function_name(fl_addr),
            "files_loaded": walk.strings_used_by(fl_addr),
            "functions": functions,
        }
    return effects


def write(effects, output=OUTPUT):
    """The index (names, addresses, comments, files) to `output`, the pseudocode by address to
    magic_effect_code.json.gz beside it (gzip without a timestamp: the same export, the same bytes)."""
    import gzip
    output = Path(output)
    code, index = {}, {}
    for key, entry in effects.items():
        entry = dict(entry)
        if "functions" in entry:
            functions = []
            for function in entry["functions"]:
                function = dict(function)
                code[function["addr"]] = function.pop("pseudocode", "")
                functions.append(function)
            entry["functions"] = functions
        index[key] = entry
    index["_snapshot"] = dict(index.get("_snapshot", {}), code=CODE_NAME)
    output.write_text(json.dumps(index, indent=1), encoding="utf-8")
    payload = json.dumps(dict(sorted(code.items())), separators=(",", ":")).encode("utf-8")
    (output.parent / CODE_NAME).write_bytes(gzip.compress(payload, 9, mtime=0))
    named = sum(1 for key, entry in effects.items() if not key.startswith("_")
                for function in entry.get("functions", []) if not function["name"].startswith(("sub_", "nullsub_")))
    total = sum(len(entry.get("functions", [])) for key, entry in effects.items() if not key.startswith("_"))
    print(f"wrote {output} and {CODE_NAME}: {total} functions ({len(code)} addresses), {named} named")


def main_headless(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--idb", required=True, help="the saved .i64 (a temporary copy is opened)")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(argv)
    idb = Path(args.idb)
    saved = datetime.fromtimestamp(idb.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    import idapro
    with tempfile.TemporaryDirectory(prefix="fujin_idb_") as folder:
        copy = Path(folder) / idb.name
        shutil.copyfile(idb, copy)          # never open the database IDA may have open
        if idapro.open_database(str(copy), run_auto_analysis=False) != 0:
            raise SystemExit(f"idalib could not open {copy}")
        try:
            effects = export(idb.name, saved)
        finally:
            idapro.close_database(save=False)
    write(effects, args.output)


def main_in_ida():
    import idc
    path = Path(idc.get_idb_path())
    write(export(path.name, datetime.now().strftime("%Y-%m-%d %H:%M") + " (open database)"))


if __name__ == "__main__":
    try:
        import idc  # noqa: F401 - only importable inside IDA (or after idapro opened a database)
        main_in_ida()
    except ImportError:
        main_headless()
