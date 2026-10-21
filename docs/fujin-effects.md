# Fujin: battle effect workspace

Select **Battle → Fujin (Battle effect editor)**, then an effect ID. Fujin replaces the
separate effect explorer and Laguna GUI. The 400-slot list uses shared attack-animation
names. The underlying Laguna modules provide MAG documents and cinematic tools.

## Components

- **Overview:** native initializer/loader, runtime family and dependencies. Loader references,
  verified runtime resources and filename-family hints are distinct. A matching filename does
  not prove ownership; verified shared resources can appear under several effect IDs.
- **Camera:** executable tracks, embedded MAG tracks, and verified native parameters. MAG and
  executable tracks share the battle-context preview and caster/target imports. This previews
  the selected track, not additional procedural writes. Disease Breath (231) has a camera in
  `MAG230_B.00` at `0x870`: 3 blocks, 5 keyframe entries. Bone-driven motion is edited in scripts.
- **Choreography:** editable MAG instructions using each effect's opcode profile, seven-GF
  scene playback, and native decompilation read-only.
- **Models / animation:** file and embedded model sections, skeleton scales and bone
  parent/length/rotations, animation directories/frame counts, plus bounded byte editing.
  Compressed skeletal animation authoring is not fully decoded here.
- **Textures / palettes:** complete consecutive TIM images, including Carbuncle's second
  image in `mag277.tim`. Palette words and pixel bytes are editable; this is not an image painter.
- **Sound:** recognized audio sections and bounded bytes; audio encoding remains undecoded.
- **Files / sections:** every section, raw editing, export and equal-size replacement.
  **Browse all imported files** exposes MA8 files and unresolved associations.
- **Pending changes:** destinations across all effects, including edits made before switching.

All views share one manager/byte image per resource, including undo/redo and the cinematic
engine. Separate identical executable blobs remain independent. Edits preserve section sizes;
there is no relocation/growth. The original MAG sweep covers 790 files, 58 cinematic roots
and 46 embedded tracks; see [MAG section formats](laguna-mag-editor.md).

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

**Save** writes modified MAG files to imported paths. Executable edits request one export
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
python -m pytest tests/Fujin tests/Laguna
```

`section`, `disasm`, `patch`, `timeline` and `opcodes` are also under `fujin`.
The former standalone `laguna` command and GUI entry have been removed.

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
Generate the plan without IDA to inspect it:

```powershell
python -m Fujin.ResearchScript.sync_effect_ida --emit-plan Temp/ida-effect-plan.json
python -m pytest tests/Fujin/test_ida_effect_annotations.py
```
