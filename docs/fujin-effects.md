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
  monsters, its caster and target - the **Party**, **Battle** (scene.out encounter or manual
  placement), **Caster** and **Target** pickers here are the same ones; opening Battle sets the
  battle up when its models are still waiting; imported characters fill the party one file per
  character, any other is picked in Party, its weapon in the Camera tab). These pickers sit in the
  **Battle actors** group, off by default and greyed while off: the effect alone is recorded, the
  actors picked there loaded but not drawn (the effect's code places itself on its caster and
  target) and no cast plays (what the effect
  redraws itself, as Cure its target, is left out too: the recorder drops the primitives drawn with
  the actors' palettes, so the effect's own models, as Protect's shield, stay). **Play** records first when there is no recording yet; edits of
  the effect's files, and of its camera (a keyframe, the Camera tab's script inputs: recorded again
  when the shot is not the one the recording was made with, each cached recording keeping its
  `.camera` lines), refresh the recording by themselves. Recording runs the effect's
  original code in FF8UltimateEditor's effect recorder
  (`Tools/fxrecorder`, a 32-bit program, never kept in git: the Windows release ships the one its
  CI builds; run from source, FF8UltimateEditor builds it in the background when it starts and
  the exe is missing or older than its source - a fresh clone, a pull that changed it - with the
  local Visual Studio C++ build tools, any version, through `Tools/fxrecorder/build.bat`
  (`Fujin/recorderbuild.py`; meanwhile Play waits and the status says so, and without the tools
  it says what to install; no FFNx needed). It maps
  the opened FF8_EN.exe and loads each actor through the game's own loaders into its battle slot
  (party 0-2, enemies 3-6): monsters with `battle_monster_dat_loader`, characters as the battle
  start does (`initWeaponAnim` 0x502670: body `Battle_isLoadSquallEtc` 0x5077B0, weapon
  `Battle_LoadWeaponry` 0x507BF0, on their normal animations), each standing
  and facing where the Camera tab's setup puts it. Record needs an imported caster and target
  model (an effect draws on its target: Cure redraws it); an actor the battle names but whose file
  is not imported (an encounter enemy, a weapon) is left out and named in the status. A battle
  never has one character twice (the game keeps a character's model data under its com id in
  `COMMAND_QUEUE_TABLE`), so a second one of the same character (Squall `d0c000` and his SeeD
  uniform `d0c001`) gets a free character id: the recorder gives its files itself. It runs the
  effect and records every
  PlayStation GPU packet and texture upload (the battle VRAM queue `Battle_FlushVramCommandQueue`
  0x505D20, read after each model load, direct uploads, and the battle's shared effect textures
  `a8def.tim`). Each tick also draws the battle's models as the entity task does, body and weapon
  in lockstep, one frame per tick, each playing what its sequences say - read by Fujin, not run
  (`FF8GameData/dat/actoranimplan.py`; a character's sequences are in its weapon file): its idle
  is sequence 1's loop (animation 0 of the normal set; the battle entrance, sequence 8, plays the
  body's section 7 animation and its `AC 00` restores the normal ones). The caster first plays
  its Magic cast, sequence 11 for a character (`computeCommandAction` 0x48D200 table
  `byte_B8150C`): what it plays until it sets the "start the effect" state flag 0x20
  (`BattleActionSequence_Tick_MagicCast` 0x50A9A0; the effect's files count as loaded at once),
  recorded too and seen wide (the Camera tab setup's starting view), then while the effect runs -
  Squall: animation 8, the step forward, after which he stands 792 units forward (the sequence's
  model-local offset, `E5 0x0D-0x0F`, turned by his facing as the entity task does at 0x502C25),
  18, 19, 20 (going on into the effect), then 21 looped
  (`Battle_QueueAnimation` 0x509520, `AdvanceAnimationBy1AndCheckCompletion` 0x5094F0,
  `BattleModel_RebuildBodyAndWeaponMatrices` 0x508F60, `BattleEntity_ComputeViewBounds` 0x5086F0,
  `BS_RenderBattleEntity` 0x502D40) unless the effect hides them (a hidden one still moves on,
  as the entity task does: Cure redraws its target in its current pose), and orders everything by depth
  from the GPU emulation's execution list; a draw-mode packet (E1, no depth) goes right before the
  primitives inserted ahead of it, which the console's ordering table runs after it (Cure's rays
  take their additive mode from one). The
  camera is the shot the Camera tab's preview plays for the effect (its track: exe, created or
  `.bcam`), so both previews show the same view. Fujin draws the recording with OpenGL at the
  battle's 15 frames per second (`FF8GameData/psxgpu/glrender.py`: VRAM as a 16-bit integer
  texture, the CLUT lookup and the four semi-transparency modes in the shader; about 40 ms a
  frame), or with the software GPU without OpenGL 3.3 (`FF8GameData/psxgpu/gpu.py`, the same
  picture, about 1 s a frame): polygons, sprites, lines, CLUT textures; FF8 PC's 3D output is in
  eighths of a pixel, the 320 x 224 window being 2560 x 1792 units.
  Files: only those opened in Fujin, one by one - nothing is read from their folders. FF8_EN.exe
  and the effect files from the header's Import (the recorder gets the effect's imported files as
  Fujin holds them, unsaved edits included, staged privately; a file the effect asks for and was not
  imported is named in the status), the models from Import complementary (Camera preview models),
  scene.out from Import complementary for the encounters, and optionally `a8def.tim` from Import
  complementary (a side file; battle file 163, the battle's shared effect
  textures the game loads at every battle start, `load_aA8defTim` 0x508660; without it the parts
  of an effect drawn with them are flat grey).
  Exact: shapes, colours, blending, timing. Approximated: the sequences' other actions (the
  cast's own small effect, sounds, moves) are not run, the camera during the cast is a fixed
  wide view (not the game's opening shot), the camera player is Fujin's (floating point). **Game window** shows the screen; **Fit the effect** frames
  everything drawn.
- **Camera:** executable tracks, embedded MAG tracks, and verified native parameters. MAG and
  executable tracks share the battle-context preview and caster/target imports. This previews
  the selected track, not additional procedural writes. Disease Breath (231) has a camera in
  `MAG230_B.00` at `0x870`: 3 blocks, 5 keyframe entries. Bone-driven motion is edited in scripts.
  The track's Script tab shows its camera script as **User-friendly** rows (commands, battle
  values, tests and jump targets picked from lists, described in `camera_script.json`) or as
  **Code**; its info button explains how the script picks the animation.
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
  **Part tabs** (one per part of an effect FFNx has a C++ port with parameters for; Cure:
  Emitter, Ring, Ground glow, Overlay, Sparkles, Motes, Glints, and the same for Potion, whose
  module is a relocated copy of Cure's; Hypnotize: Timing, Main layout,
  Rings, Target layouts, Sprites): the part's parameters as a form
  (bold = not the game's value, **Game values** resets them; a value in its unit when the port gives
  one - fx_params.h `Unit`: an angle in degrees, a size as x 1 = its own - the raw value greyed
  beside it; a fraction's value, as Cure's ring radius x / , greyed beside its divisor. Cure's
  ring: each tick it takes **Steps per tick** steps of **Step angle** around the target, drawn at
  the last one, a sparkle born at each) beside a small preview of that part
  alone, framed on where it goes. Under the preview, the part's **images**: each picture of video
  memory it takes texels from (a TIM, the target's own texture), whole, read with the depth and
  palette its primitives use, every piece it takes during the effect outlined and the ones it
  draws at the preview's tick filled (hover a piece: its place and ticks); an image the part's
  own values name is outlined dashed (Cure's overlay: the light picture it projects, the glow's
  disc - a pass the PC never draws). An image loaded from one of the effect's TIM files says so,
  and **Show in Textures** opens that TIM in the Textures tab, palette row chosen and the pieces
  outlined (`FF8GameData/psxgpu/texuse.py` finds them in the recording, `Fujin/partimages.py`
  shows them). Beside it, the **Sprite sequences** tab: the flipbooks the part draws its sprites
  from. They are data of FF8_EN.exe (about 330, signature `24 05 01 00`, file offset = address -
  0x400000: frame count, frame offsets, then per frame its pieces, 20 bytes each - texels u, v,
  size, palette, page, intensity, GPU code, place in the sprite, angle, scale -
  `FF8GameData/psxgpu/spritesequence.py`); the recorder hooks `InitEffectSequenceFromData`
  (0x571C80) and its 18 copies and writes, per tick, which part drew which sequence and frame (`Q`
  lines). Each sequence is a row of its frames, drawn from the recording's video memory (the frames
  the part never draws dimmed, those of the preview's tick framed blue); a click lists the frame's
  pieces and outlines them dashed orange on the Images tab (Cure: Ring `0x1641F78` and its ending
  `0x1641FCC`, Ground glow `0x1642504`, Sparkles `0x1642238`, Motes `0x164205C`; Potion has its own
  copies). The sequences are parameters too (FFNx `fx_params.h` field type `Seq`, Cure and Potion's
  **Sequence** fields): **Choose…** opens the exe's sequences (filter: those drawing from video
  memory the effect fills - every magic loads its pictures at the same places, so another
  effect's sequence draws this one's pictures cut its own way, as the list shows it); FFNx keeps
  the game's sequence for a value that is none (`fxp::sequence`) and a flipbook's last frame
  within its sequence (`fxp::last_frame`). A **Frames** field crosses the frames its sequence never
  plays (Sparkles: frames 9-26 of 27). **Browse all sequences…** lists them without choosing.
  Every field's **?** answers *What does it change?*: the preview shows the part twice, side by
  side - now, and with another value of that field (the game's when the field is not at it, else
  twice it; any value in the bar's box, Done to stop) recorded with the effect's other values as
  they are. A strip under the slider marks the ticks that change (red: this part; amber: only other
  parts - they draw from the same stream of random numbers, so a part drawing more or less shifts
  their rolls), a click goes there, and the bar says which parts change when
  (`FF8GameData/psxgpu/fxdiff.py`). The **Target** box draws the target as last drawn when the
  effect hides it (Cure hides it while its Overlay redraws it), merged by depth with the part, both
  framed together.
  The numbers come out of the port's code into one struct per
  part (FFNx `src/ff8/battle/fx/fx_params.h`: generic blocks every module can reuse - a tick
  window, a count per tick, a random range, a fraction, the effect library's glint style -
  `HealRingParams` in `mag_heal_ring.h`, shared by Cure and Potion - one struct, parts and field
  table, each module with its own live values, so Potion and Cure are edited apart -
  `HypnotizeParams` in `mag133_hypnotize.cpp`, defaults = the
  game's values) with a field table the recorder writes out (`fxrecorder <effect> schema=<file>`),
  so the forms are always those of the port it runs. A module with parameters registers itself
  for the recorder (`FX_LAB_MODULE`): `build.bat` compiles in every source file naming it. The previews are one more recording: the recorder runs the port instead of
  the exe's code (`native=1`; with the game's values it draws exactly what the original does,
  checked by the tests) with the edited parameters (`params=`), only the effect's target drawn
  (`actors=2`: no party, no cast) and each primitive tagged with the part that drew it
  (`FX_PART`, nothing in the game's build; untagged = part 0 = the target). Each preview's
  **Target** box adds the target (its file named on the box) as a reference, in every tab at
  once. The **Path** box (on by default) draws where each sprite of the part goes over the whole
  effect: a thin purple line from where it is drawn one tick to where it is drawn the next, a dot
  where it appears (Cure's ring: its helix, 8 ticks a turn; its sparkles: one line each, their
  dots on the ring's steps). The recorder writes each sprite's screen middle on its Q line and
  `EffectRecording.sprite_paths` joins a tick's sprites to the last tick's nearest ones of the
  same part, sequence and next frame (the recording does not say which particle drew one). A part that draws nothing (Cure's Emitter: when the sound plays, when the HP are given)
  shows the whole effect with its ticks marked under the picture. An edit records again; the
  Overview's preview runs the port with the edited parameters too. Save writes them as
  `effect_NNN.fxparams` (JSON, only the values not at the game's) into the export folder, with
  the patch; Import complementary reads them back. The ports come from FFNx's effect sources:
  the header's **FFNx** button in the External program bar (tick it, then Update; clicking it says
  what is installed - Choreography says so too when the recorder has no ports), the updater's
  **FFNxEffects** (Update downloads the folder `src/ff8/battle/fx` of FFNx's
  source - for now the `VanillaDecompiledStructRework` branch of HobbitDur/FFNx for both
  channels: `VanillaDecompiledForFutur30FPS` (the ports) plus the editor's parameter rework on
  top, such as Cure and Potion sharing `mag_heal_ring.h` - into `ExternalTools/FFNx/fx`, `SOURCE.txt` naming the commit, and the recorder is
  built again with them); the release's CI does the same before building the recorder.
  Cure's Overlay hides the target while the ring climbs and redraws it itself, twice per
  polygon: flat with its own texture (what the preview shows - the target as it is), and, where
  it faces the ring and falls in the projected window, gouraud with Cure's light texture
  projected from the ring. That second pass never draws on PC, in the game as well: the PC's
  software GTE (`GTE_RTPS` 0x45FAA0) returns screen coordinates in eighths of a pixel
  (`8·x·H/z + 8·OFX`), while the overlay tests them against the PSX window in pixels
  (96..223 × 56..183 around 160, 120) - every polygon falls outside.
  The same PC unit breaks Hypnotize's main layout (its purple swirl, ticks 0-29): its frame
  places it at the caster's screen position taken as PSX pixels (`(160 - sx) << 4`,
  `(120 - sy) << 4` at 12 H / 16 H), so on PC it lands eight times as far out, off screen - it
  never shows. Its **PSX screen units** parameter (Main layout tab, off by default = the PC as it
  is) takes the position back to pixels first: the swirl draws over the caster. The recorder sets
  the battle camera's projection distance (`0x1D8E038`, which the camera player keeps and many
  effects read) with the GTE's.
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
- **Every section has its tool tab** (no separate file tab): each tool's **Sections** sub-tab is
  the read-only reference of the sections it covers (named fields and bytes, with export) - a
  MAG file's header and object table (where its parts are) in Models / animation, a TIM's
  headers with its palettes and pixels in Textures, a MAG file's raw texture blocks in Textures
  too, and the undecoded workspace data of a MAG file in **Choreography → Workspace data**
  (shown only for the effects that have some). Every vanilla effect file belongs to an effect.
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
takes `effect_NNN.bcam` files, picked one by one (several at once in the dialog, never a whole
folder), and **Import previous** loads the same `.bcam` files again: each becomes that effect's camera - an override of its exe track
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
