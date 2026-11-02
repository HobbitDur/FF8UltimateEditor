# MAG section editing inside Fujin

The [Fujin effect workspace](fujin-effects.md) opens MAG/MA8 files by their contents, including `.00`, `.01`, streamed numeric parts,
TIM textures with any suffix, indexed model/animation containers, SCOT/AKAO audio and undecoded
data. The bundled vanilla catalog contains 790 file names. **Import** also accepts additional
mod files; **Open folder** discovers MAG/MA8 names recursively. Each tool tab's **Source** picker
keeps each loaded file's edits and undo history independently. The MAG document
(`Fujin/magdocument.py`) and its editor (`Fujin/magdocumentwidget.py`) are part of Fujin.

## Sections

Each tool tab's **Sections** sub-tab holds one tab per mapped section it covers (the header and
object table in Models / animation, undecoded workspace data in Choreography → Workspace data). Pages are built when selected, and
large field/byte tables are paged rather than allocating a widget for every byte.

- **Header/directories:** named offsets, counts and packed table entries.
- **Cinematic script:** the dedicated **Script** tab retains the instruction/modifier/operand
  editor. The script ends at the next mapped section, including an embedded camera when present.
- **Camera:** editable camera VM source and structured sets/slots/blocks/keyframes, reusing
  Fujin's track parser and Watts' keyframe editor. Disease Breath (effect 231) opens
  `MAG230_B.00`, with its camera at `0x870`. Keyframes and script can grow or shrink: the file
  makes room (see [Resizing a part](#resizing-a-part-packedmag)). Where it cannot, the camera
  keeps its bytes, the info line says why, and the script and the keyframes share that room.
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

## Resizing a part (PackedMag)

`FF8GameData/magcine/packedmag.py` (`PackedMag`) is the one class for a packed MAG file. It
gathers the section map, objects, sounds, vibration, script and camera, and it alone knows
every offset the game follows into the file:

| Offset | Relative to |
|---|---|
| Header `+0x04`..`+0x24` | the file (0 = absent) |
| Texture, CLUT and music table entries (low 24 bits) | their own table |
| Object table entries | the object table |
| Sprite frame lists (`s32`) | the object table |
| Sound table entries | the sound table |
| Vibration bank entries | the bank |
| Script jumps, calls, spawns and particle starts | their instruction |

A part replaced by one of another size moves what follows it. Every offset is then rewritten,
the following parts stay 4-byte aligned (zero padding), and each part the game reaches is
checked to still hold its bytes. Shrinking back gives the original bytes.

FF8_EN.exe reads nothing else. The effect code uses header `+0x04`, `+0x18`, `+0x20` and
`+0x24` of the `.00` and `+0x1C` of the `.01`, never a fixed offset past the header. Each
effect's files are loaded one after the other at the start of the 1 MB magic buffer
(`IO_GetFile_MAGIC` 0x571B80), so a bigger `.00` only pushes the `.01` further.

A resize is refused, saying why, when:

- the file has no script (the `.01` and streamed parts): the raw positions the `.00` script
  holds into them are not known;
- a script operand holds a raw position past the part: opcode 0x29 bit 14, VRAM upload from
  slot + 4 KB page; opcode 0x06, a file streamed into slot + page or an exe descriptor offset;
- an offset is stored inside the part, or a sprite frame offset (classified by shape) would
  have to change;
- the files would reach a fixed work buffer of the script (opcode 0x21, bit 15 clear, an
  absolute offset in the magic buffer), or the 1 MB. The `.01` beside the `.00` is needed for
  that check. MAG218 and MAG222 already reuse the memory of their texture-only `.01` and keep
  their size.

44 of the 46 vanilla stage cameras can grow or shrink this way.

Other edits keep the byte size. A failed size/range check changes no bytes. Undo/redo covers
all sections. Save writes only modified loaded files; unedited files round-trip byte for byte.
Modified companion and streamed bytes are also used by the supported GF scene preview.

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
python -m Fujin.ResearchScript.dump_mag_profiles extracted_files/FF8_EN.exe --out FF8GameData/Resources/json/mag_cinematic_profiles.json
python -m Fujin.ResearchScript.sweep_mag_files extracted_files --out docs/mag-file-census.json
python -m pytest tests/Fujin/test_mag_sections.py tests/Fujin/test_mag_cinematic.py
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
