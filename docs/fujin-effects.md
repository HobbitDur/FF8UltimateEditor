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
  **Effect preview** (below the Overview) shows what an effect run by the exe's own code (Cure,
  Fire, most spells, enemy attacks) draws, tick by tick at 15 per second, in a real battle: the
  Camera tab preview's (its party with their weapons, its encounter's enemies or its imported
  monsters, its caster and target - the **Battle** (scene.out encounter or manual placement),
  **Caster** and **Target** pickers here are the same ones; opening Battle sets the battle up when
  its models are still waiting). **Play** records first when there is no recording yet.
  **Record** runs the effect's original code in FF8UltimateEditor's effect recorder
  (`Tools/fxrecorder`, a 32-bit program shipped with the Windows release; from source,
  `Tools/fxrecorder/build.bat` builds it with Visual Studio's C++ tools - no FFNx needed). It maps
  the opened FF8_EN.exe and loads each actor through the game's own loaders into its battle slot
  (party 0-2, enemies 3-6): monsters with `battle_monster_dat_loader`, characters as the battle
  start does (`initWeaponAnim` 0x502670: body `Battle_isLoadSquallEtc` 0x5077B0, weapon
  `Battle_LoadWeaponry` 0x507BF0, animations bound by `setComFileData` 0x502270), each standing
  and facing where the Camera tab's setup puts it. Record needs an imported caster and target
  model (an effect draws on its target: Cure redraws it); an actor the battle names but whose file
  is not imported (an encounter enemy, a weapon) is left out and named in the status. It runs the
  effect and records every
  PlayStation GPU packet and texture upload (the battle VRAM queue `Battle_FlushVramCommandQueue`
  0x505D20, read after each model load, direct uploads, and the battle's shared effect textures
  `a8def.tim`). Each tick also draws the battle's models as the entity task does (body and weapon
  on animation 0: `Battle_QueueAnimation` 0x509520, `BattleModel_RebuildBodyAndWeaponMatrices`
  0x508F60, `BattleEntity_ComputeViewBounds` 0x5086F0, `BS_RenderBattleEntity` 0x502D40) unless the
  effect hides them, and orders everything by depth from the GPU emulation's execution list. The
  camera is the shot the Camera tab's preview plays for the effect (its track: exe, created or
  `.bcam`), so both previews show the same view. Fujin draws the recording with a software GPU
  (`FF8GameData/psxgpu`: polygons, sprites, lines, CLUT textures, the four semi-transparency modes;
  FF8 PC's 3D output is in eighths of a pixel, the 320 x 224 window being 2560 x 1792 units).
  Files: only those opened in Fujin, one by one - nothing is read from their folders. FF8_EN.exe
  and the effect files from the header's Import (the recorder gets the effect's imported files as
  Fujin holds them, unsaved edits included, staged privately; a file the effect asks for and was not
  imported is named in the status), the models from Import complementary (Camera preview models),
  scene.out from Import complementary for the encounters, and optionally `a8def.tim` from Import
  complementary (a side file; battle file 163, the battle's shared effect
  textures the game loads at every battle start, `load_aA8defTim` 0x508660; without it the parts
  of an effect drawn with them are flat grey).
  Exact: shapes, colours, blending, timing. Approximated: actors hold their first pose, the camera
  player is Fujin's (floating point). **Game window** shows the screen; **Fit the effect** frames
  everything drawn.
- **Camera:** executable tracks, embedded MAG tracks, and verified native parameters. MAG and
  executable tracks share the battle-context preview and caster/target imports. This previews
  the selected track, not additional procedural writes. Disease Breath (231) has a camera in
  `MAG230_B.00` at `0x870`: 3 blocks, 5 keyframe entries. Bone-driven motion is edited in scripts.
  **Create a camera:** an item/command effect that starts no camera (5 Phoenix Down, 7 Mega
  Phoenix, 40 Scan, 53, 58, 59, 183 Defend, 292-296) can be given one, from a copy of another
  effect's track (Life, 35, is suggested for 5 and 7) or a minimal one (`play(0)`,
  `end_clear()`, one slot with a 2-keyframe shot). It has no exe address: it is edited and
  previewed like any track, listed as ".bcam camera" and in Pending changes, and saved as
  `direct/exe/effect_NNN.bcam`, which FFNx (#1047) starts right after the effect starts;
  **Remove this camera** deletes it. Other camera-less effects are not offered one: they may
  move the camera with their own code (GF summons, Shot, Duel, Zell's finishers, Angelo,
  Gilgamesh...), and the Camera tab says so.
- **Choreography:** editable MAG instructions using each effect's opcode profile, scene
  playback (verified for the seven GFs; every other cinematic script replays with the same
  engine model as a labelled, untextured approximation that names the draw handlers it shows as
  markers only), and native decompilation read-only.
- **Models / animation:** a 3D view of every object of the selected file (meshes, morph
  targets as points, embedded battle models and the standard battle models of indexed
  containers such as `mag186_b.dat`, which play their own animations). Untextured: texture
  placement is known for the seven GFs only; sprite lists are listed, not drawn.
  **Export .glb…** writes the selected mesh, morph target or battle model (with its
  animations, through Ifrit's exporter) for Blender; **Import .glb…** brings an edited file
  back by moving the vertices in place: the MAG keeps its size, so no face may be added,
  removed or split (the triangles are matched in order; a changed file is refused with the
  reason), and faces, colours, UVs, bones and animations stay. One import is one Undo step.
  A battle model (the 8 embedded in packed MAGs, and the indexed containers' models such as
  `mag186_b.dat`: 28 in the vanilla files) also has a **Skeleton** table (each bone's length and
  rest rotation, written in place) and a **Pose (this frame)** table for the animation and frame
  picked above (root position, bone rotations). A frame stores the change from the previous one,
  so an edit re-encodes that animation only (the others keep their exact bytes) and must fit the
  model's animation section: the MAG keeps its size, and the room left (often 0-3 bytes, the
  slack after the animations) is shown; an edit needing more is refused with the bytes missing.
  Every vanilla model round-trips byte-identical. glTF import does not bring animations back:
  the exporter bakes rotations into float quaternions that do not map back to FF8's raw values.
- **Textures:** every TIM of the selected file (Carbuncle's `mag277.tim` holds two) as its
  picture over a checkerboard and its palette (CLUT: the colours a 4/8-bit TIM's texels index,
  one row per alternate colouring; the game picks a row per sprite; a 16-bit TIM has none).
  Double-click the picture or the palette (or use its buttons) to replace it with a PNG of the
  same size: a new picture is mapped onto the selected palette row (texels that kept their
  colour keep their index), and a palette PNG with fewer rows than the TIM replaces the rows
  you pick. **Export PNGs…** writes `<name>.png` (the picture
  in the selected row) and `<name>_palette.png`, laid out like the swatches: 16 colours per
  line, each palette row under the previous one (a 256-colour row is 16 lines). The import takes
  that layout back, or one palette row per line. The CLUT bytes are written from the palette
  image (5 bits per channel, fully transparent = colour 0).
  **Semi-transparency** (the PSX STP bit: blended when the effect draws the sprite with
  blending on) travels as PNG alpha: 128 = semi-transparent, 255 = opaque, 0 = transparent;
  black always keeps the bit (without it, it would be transparent). Click a palette colour to
  see it and switch its **Semi-transparent** box; a corner dot marks those colours.
  **Video memory position** sets where the TIM asks for its picture and palette to be loaded
  (1024 × 512 16-bit units; a palette's X is a multiple of 16).
  **Restore original** puts the TIM back as it is on disk; Undo / Redo cover every edit. No raw
  bytes are edited. A MAG file's textures are raw VRAM blocks whose size and depth come from
  the game code, so they are not drawn here.
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
  played by the PC build. **Change to** points the selected block at another `audio.dat`
  entry (Preview plays it first; the world id is rewritten in its category when that reaches
  the entry, else as category 0). Each vibration point has a **Strength %** (the level the
  engine sends x2, max 255) and a **Ramp to next** in ticks (15 per second); the number of
  points is fixed, the curve follows every edit.
- **Files / sections:** every section of the effect's files as a read-only reference (named
  fields and bytes) with export; Fujin edits only through its decoded views (a camera section
  keeps its camera editor). A TIM is not repeated there: it points to Textures, and the tab
  is greyed while only TIM files are imported.
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
all lines are validated before applying, including resource ownership. **Import** (header) also
takes `effect_NNN.bcam` files, several at once, or a folder (FFNx's `direct/exe` and
`direct/<lang>/exe` included), and **Import previous** loads the same `.bcam` files again: each becomes that effect's camera - an override of its exe track
(".bcam only" when it no longer fits the exe) or a created camera. A file FFNx would refuse
(header count 2 and script offset 8, size field = file size, keyframe offset and sets inside,
keyframes filling the file exactly), or not named `effect_NNN.bcam`, is refused with the reason.
Export, reimport and save give the same bytes back. Reverting a resized camera removes that
session's old export when saving to the same folder, provided it was not changed externally.

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
