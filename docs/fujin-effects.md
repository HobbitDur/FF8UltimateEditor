# Fujin: battle effect workspace

Select **Battle → Fujin (Battle effect editor)**, then an effect ID. Fujin replaces the
former separate effect explorer and GF cinematic editor: everything lives in the `Fujin`
package. The 400-slot list uses shared attack-animation names. `Fujin/magdocument.py` and
`Fujin/magdocumentwidget.py` provide the MAG documents and the cinematic tools.

## Components

- **Overview:** native initializer/loader, runtime family and dependencies. Loader references,
  verified runtime resources and filename-family hints are distinct. A matching filename does
  not prove ownership; verified shared resources can appear under several effect IDs.
  **Used by** lists the kernel.bin entries that play the effect: spells, GFs, enemy attacks,
  battle items, command abilities and limit breaks, each with its index in its kernel section.
  Open kernel.bin with the header's **Import complementary** (it is shared, so a kernel.bin
  opened in SolomonRing works too). The effect list then shows them as a tooltip, and its
  search also finds an effect by a user's name ("Phoenix Pinion" finds 001 Cure) or by what it
  has ("exe camera track", "MAG files", "editable exe values", "unused slot": also listed in
  each row's tooltip). An effect with no camera track says so in the Camera tab. The fields
  read are every "Attack animation" field of `kernel_section_fields.json`
  (`Fujin/effectusers.py`).
- **Camera:** executable tracks, embedded MAG tracks, and verified native parameters. MAG and
  executable tracks share the battle-context preview and caster/target imports. This previews
  the selected track, not additional procedural writes. Disease Breath (231) has a camera in
  `MAG230_B.00` at `0x870`: 3 blocks, 5 keyframe entries. Bone-driven motion is edited in scripts.
- **Choreography:** editable MAG instructions using each effect's opcode profile, scene
  playback (verified for the seven GFs; every other cinematic script replays with the same
  engine model as a labelled, untextured approximation that names the draw handlers it shows as
  markers only), and native decompilation read-only.
- **Models / animation:** a 3D view of every object of the selected file (meshes, morph
  targets as points, embedded battle models and the standard battle models of indexed
  containers such as `mag186_b.dat`, which play their own animations). Untextured: texture
  placement is known for the seven GFs only; sprite lists are listed, not drawn. The byte
  sections stay editable: skeleton scales and bone parent/length/rotations, animation
  directories/frame counts. Compressed skeletal animation authoring is not fully decoded here.
- **Textures:** every TIM of the selected file (Carbuncle's `mag277.tim` holds two) as its
  picture over a checkerboard and its palette (CLUT: the colours a 4/8-bit TIM's texels index,
  one row per alternate colouring; the game picks a row per sprite; a 16-bit TIM has none).
  Double-click the picture or the palette (or use its buttons) to replace it with a PNG of the
  same size: a new picture is mapped onto the selected palette row (texels that kept their
  colour keep their index), a new palette keeps each colour's transparency bit, and fewer rows
  than the palette replace the rows you pick. **Export PNGs…** writes `<name>.png` (the picture
  in the selected row) and `<name>_palette.png`, laid out like the swatches: 16 colours per
  line, each palette row under the previous one (a 256-colour row is 16 lines). The import takes
  that layout back, or one palette row per line. The CLUT bytes are written from the palette
  image (5 bits per channel, pure black kept opaque, fully transparent = colour 0).
  **Restore original** puts the TIM back as it is on disk; Undo / Redo cover every edit. The raw sections stay in Files / sections. A MAG file's textures are raw VRAM blocks
  whose size and depth come from the game code, so they are not drawn here.
- **Empty tabs say why.** Models, Textures and Sound name the effect's files still to import;
  once nothing is missing, they say what the effect has no data for, and point to the native
  functions that do the work when the snapshot names them (Cure: "stores no model of its own",
  `MAG_001_CURE_DrawTargetModelWithOverlay`). The greyed MAG script tab of a native effect says
  it is run by the exe's own code.
- **Sound:** each sound block `{u32 world sound id, "SCOT", PlayStation data}` resolved to its
  `audio.dat` entry (PlaySE -> BdPlaySE -> PlayWorldSound reads only the id) and played with
  the archive opened from the header (Import complementary: audio.fmt, shared with Julia).
  Music-table blocks and streamed SCOT parts are played as unverified. The header +0x24 bank
  is controller vibration (left/right motor envelopes), drawn as curves. AKAO banks are not
  played by the PC build.
- **Files / sections:** every section, raw editing, export and equal-size replacement.
  **Browse all imported files** exposes MA8 files and unresolved associations.
- **Pending changes:** destinations across all effects, including edits made before switching.

All views share one manager/byte image per resource, including undo/redo and the cinematic
engine. Separate identical executable blobs remain independent. Edits preserve section sizes;
there is no relocation/growth. The original MAG sweep covers 790 files, 58 cinematic roots
and 46 embedded tracks; see [MAG section formats](fujin-mag-sections.md).

## Native data

`effect_resources.json` describes 24 model containers, 26 complete TIMs and six camera
immediates. Resource fingerprints and surrounding instruction bytes are checked before
editing. These addresses are **English 2013 Steam only**. Existing executable camera tracks
retain EN/FR/DE/IT/ES support; MAG editing does not depend on executable language.

Carbuncle's native creature task (`0x681630`) directly writes camera coordinates and calls
`MAG_278_CameraSwingAboutLookAt`. Camera → Native parameters exposes these verified operands:

| Parameter | EN operand VA | Signed type | Original |
|---|---|---|---|
| Opening Y offset from floor | `0x681D35` | 32-bit | 3000 |
| Opening camera Z | `0x681D5E` | 16-bit | -4000 |
| Opening orbit radius | `0x681D93` | 32-bit | 4010 |
| Middle orbit radius | `0x681DE2` | 32-bit | 4000 |
| Middle orbit angle step | `0x681DE7` | 8-bit | -32 |
| Late orbit radius | `0x681F67` | 32-bit | 4150 |

Only immediate bytes are editable through these bindings. Other procedural camera code is
read-only research. Griever's summon reuses existing actors; edit `c0m122.dat` in Ifrit instead
of looking for a dedicated `mag068` model.

## Saving and CLI

**Save** writes modified MAG and TIM files over the imported files (the header line then says
what was saved; its tooltip lists the paths). Executable edits request one export
folder: `effects_EN.hext` (or the loaded language) combines camera/native data differences.
Resized tracks write `direct/exe/effect_NNN.bcam` under that folder. The
executable is never overwritten. Patches are cumulative against the loaded executable;
successful export clears unsaved state without losing that baseline. Failed/canceled saves
retain unsaved state. Reimport a saved effect Hext over the matching executable to continue;
all lines are validated before applying, including resource ownership. Structural `.bcam`
reimport is not implemented. Reverting a resized camera removes that session's old export
when saving to the same folder, provided it was not changed externally.

```powershell
python Fujin/ResearchScript/build_effect_resources.py extracted_files/FF8_EN.exe
python cli.py fujin effect --id 231
python cli.py fujin info -i extracted_files/magic/MAG230_B.00
python cli.py fujin native -i extracted_files/FF8_EN.exe --effect 278
python cli.py fujin native -i extracted_files/FF8_EN.exe --parameter Carbuncle_OpeningHeight --value 3500 -o camera.hext
python -m pytest tests/Fujin
```

`section`, `disasm`, `patch`, `timeline` and `opcodes` are also under `fujin`.
The former standalone `laguna` command, GUI entry and package have been removed: Fujin is the
only battle effect tool.

## Refresh the native code snapshot

Choreography → Native code shows `FF8GameData/Resources/json/magic_effect.json`: per effect,
its initializer and loader, the files the loader names, and each of its own functions (name,
address, function comment, Hex-Rays pseudocode). Its `_snapshot` entry records the database and
the date it was saved; Fujin never needs IDA. After improving the IDB (names, comments), save it
in IDA and re-export. The script opens a temporary copy with IDA 9's idalib, so the open
database is never touched, and it changes nothing in the IDB:

```powershell
$env:IDADIR = "C:\Program Files\IDA Professional 9.2"
$env:PYTHONPATH = "$env:IDADIR\idalib\python"
$env:IDAUSR = "$env:TEMP\idausr-empty"   # an empty folder: no user plugins (MCP server) start
python Fujin/ResearchScript/export_effect_functions.py --idb D:\FF8_EN.exe.i64
```

Run it with a Python that idalib supports (3.12 works). Inside IDA it also runs from **File →
Script file**. An effect's functions are those reached from its initializer (calls and task
callbacks, as `dump_magic_effects.py` walks them) plus every function named `MAG_<effect>_*`.
`dump_magic_effects.py` remains the script that also renames variables in the IDB.

## Synchronize the IDA research database

In the audited English IDA database, run **File → Script file** and select
`Fujin/ResearchScript/sync_effect_ida.py`. It validates the IDB input hash and all referenced
source bytes, saves the current database, makes a timestamped SHA-256-verified copy under
`Desktop/IDA_Backups`, and only then changes annotations. It preserves existing descriptive
names and unrelated comments. It saves again and writes an `effect-update-report.json` beside
the backup. A failed save or byte mismatch prevents annotation changes.

The plan covers 631 addresses: cinematic directories/handlers, native resource and camera
data, procedural camera operands, runtime/source relationships and Disease Breath's file
camera. It also defines five format types and adds 96 verified opcode-directory references.
References inside a directory structure are anchored to its defined item head, as required
by IDA; the report retains the exact source slot and handler address. Existing references
are reused. An undefined pointer is defined as a dword before adding a reference, and its
value is checked first. This avoids IDA's modal `bad call add_dref: no defined item at 'from'`
warning without splitting a directory structure.
Generate the plan without IDA to inspect it:

```powershell
python -m Fujin.ResearchScript.sync_effect_ida --emit-plan Temp/ida-effect-plan.json
python -m pytest tests/Fujin/test_ida_effect_annotations.py
```
