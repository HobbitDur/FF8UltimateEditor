# MAG section editing inside Fujin

The [Fujin effect workspace](fujin-effects.md) opens MAG/MA8 files by their contents, including `.00`, `.01`, streamed numeric parts,
TIM textures with any suffix, indexed model/animation containers, SCOT/AKAO audio and undecoded
data. The bundled vanilla catalog contains 790 file names. **Import** also accepts additional
mod files; **Open folder** discovers MAG/MA8 names recursively. **Files / sections → Source**
keeps each loaded file's edits and undo history independently. Laguna is the internal document/
cinematic component; it no longer has a separate main-window entry.

## Sections

The **Files / sections** page contains one tab per mapped section. Pages are built when selected, and
large field/byte tables are paged rather than allocating a widget for every byte.

- **Header/directories:** named offsets, counts and packed table entries.
- **Cinematic script:** the dedicated **Script** tab retains the instruction/modifier/operand
  editor. The script ends at the next mapped section, including an embedded camera when present.
- **Camera:** editable camera VM source and structured sets/slots/blocks/keyframes, reusing
  Fujin's track parser and Watts' keyframe editor. Disease Breath (effect 231) opens
  `MAG230_B.00`, with its camera at `0x870`.
- **Meshes:** named mesh-header fields and signed vertex/normal coordinates. Recognized sprite
  lists expose offsets, durations and controls. Recognized embedded battle models have separate
  header, skeleton, geometry and animation tabs.
- **TIM:** separate header, CLUT header/data and image header/data tabs. CLUT entries expose
  BGR555/STP words; a texture preview uses the shared TIM decoder. Pixel data is editable as
  bytes, or can be replaced/exported as a section.
- **Sounds, voices, music, packed texture data, indexed parts, workspace and unknown bytes:**
  bounded byte editing and section export/replacement. A binary editor is not an audio encoder,
  an image painter or a complete decoder for every effect-specific structure.

Header values are file-relative; object directory values are object-table-relative; packed
texture/CLUT entries use their low 24 bits relative to their own table. Different tables must
not be rewritten as though they shared one offset base. Physical spans end at the next known
boundary and may include alignment/padding. Unreferenced bytes remain explicit sections.

Every edit and replacement keeps the existing byte size. Growing a section would require
relocating directories, script references and nested resource references, which this editor
does not do. A failed size/range check changes no bytes. Undo/redo covers all sections. Save
writes only modified loaded files; unedited files round-trip byte for byte. Modified companion
and streamed bytes are also used by the supported GF scene preview.

## Script dialects and playback

The English 2013 exe has 58 cinematic opcode tables corresponding to the 58 script-bearing
packed files in the audited corpus. `mag_cinematic_profiles.json` records per-effect null/stub
handlers and native-verified extra instruction encodings. Fourteen opcode variants which were
unused in the original seven-GF table are now decoded for effects whose handlers implement them.
All 58 reachable root programs decode without errors in the audit. This does not prove that
every unreferenced byte is code, or that every opcode's runtime behavior has been simulated.

Playback remains enabled for the seven previously verified GF summons. Other effects have
different draw handlers, battle dependencies and choreography; their sections and scripts are
editable without presenting an unverified simulation as game behavior. The **Opcodes** reference tab and instruction editor both use the selected file's effect profile. Mod files with unknown IDs use the base table and keep unsupported data raw.

## Reproduce the sweep

From the repository root, with original extracted game files available:

```powershell
python -m Laguna.ResearchScript.dump_mag_profiles extracted_files/FF8_EN.exe --out FF8GameData/Resources/json/mag_cinematic_profiles.json
python -m Laguna.ResearchScript.sweep_mag_files extracted_files --out docs/mag-file-census.json
python -m pytest tests/Laguna
```

The census contains file names, hashes, sizes, format/section counts, script results and camera
locations, but no game assets. The tests additionally write all 790 files to temporary outputs
and compare the bytes, exercise bounded edits/undo, and verify camera editing preserves every
byte outside the embedded track.

CLI access works for every format:

```powershell
python cli.py fujin info -i extracted_files/magic/MAG230_B.00
python cli.py fujin section -i extracted_files/magic/MAG230_B.00 --at 0x870 --export camera.bin
python cli.py fujin section -i extracted_files/magic/MAG230_B.00 --at 0x870 --replace camera.bin -o edited/MAG230_B.00
```
