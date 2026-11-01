# Effects as data: what Cure still decides in code

Goal: an effect is fully described by data (its *description*), and one generic runtime (a host
DLL Fujin ships) builds and runs any description. A new effect is then a new description, with no
code written for it. The test of success: Cure and Potion produced from their descriptions alone
pass the existing port-equality tests (frame by frame against the original code), then Hypnotize,
whose parts are different, does too.

This file audits the FFNx port of Cure (`src/ff8/battle/fx/mag001_cure.cpp` and
`mag_heal_ring.h` on VanillaDecompiledStructRework; Potion's port is the same code with other
values) and lists every decision that no parameter covers yet, then sketches the description that
would cover them.

## What the parameters cover today

`HealRingParams` (about 100 fields, one struct per part) holds the *numbers* of Cure's behaviours:
ticks and windows, spawn counts per tick, speeds and random ranges, radius and climb scales,
colours, sizes, flipbook sequences and last frames, the sound and its tick and pan, the projected
image's VRAM place and window, the glint style. Every number the task code reads is one of them.

What they do not cover is everything below: which parts exist, how they are linked, which law
each part follows, what it is measured against, how it is drawn, where its resources come from,
and the engine work around it.

## A. Structure: which parts exist, who spawns whom (all code)

| Decision | Where | Today |
|---|---|---|
| The effect is a root (director) task, emitters, particles (ring, sparkles, motes) and glints, in three queues | Init (exe), `RootTask` | code |
| One emitter per action, in turn: the root spawns it (phase 3), waits until the ring clears `busy` (phase 4), goes to the next action, last = max(target count - 1, action count - 1) | `RootPhase` 3-4, Init | code |
| The root ends once all three queues are empty (phase 6), then done (9) | `RootPhase` | code |
| The emitter spawns the ring (after `ring.start.delay`) | `EmitterTask` phase 0 | code + param |
| The ring spawns a sparkle at each step, motes and glints per tick, while its "spawning" flag is on (from its init to its end) | `RingTask`, `Ring_Spawn*` | code + params |
| The glow and the overlay are drawn by the ring itself, not separate tasks | `RingTask` | code |
| A task ends when flagged done and it has no live children (child counts through the parent) | every task | code (engine rule) |
| Pool sizes: 2 roots x 0x64, 4 emitters x 0x58, 300 particles x 0x6C, 100 glints x 0x5C | Init (exe) | code |

**Needed in the description:** a list of parts, each with a kind, the part that spawns it, and a
spawn rule (at tick, per step, count schedule per tick, once per action), plus the director's
"one target after another" rule as a director kind.

## B. Behaviours: how each part moves and lives (code, numbers are params)

| Part | Law | Today |
|---|---|---|
| Root | phases 0..10 above; follows the caster's bones every tick | code |
| Emitter | follows the target's anchor and model bounds every tick; sound at `sound_tick`; HP given at `heal_tick` (`ApplyActionResultToTarget`); done | code + params |
| Ring | phase 0 init; phase 1 waits for `ending.tick`, switches to the ending flipbook; phase 2 runs it to its last frame, then clears the root's `busy`, unhides the target, stops spawning and the overlay, done | code + params |
| Ring position | helix: `centre + (sin, cos)(n x angle) x radius`, `y = centre + n x climb`, recomputed from the counter at every step `n` | code (`RingPlace`) |
| Sparkle | at birth a random velocity per axis (x, z, y), then position += velocity each tick until the flipbook's last frame | code + params |
| Mote | born on a circle around the target at a random angle, below the ring by a random share of its height over the target's top; rises at a random speed; flipbook to its last frame | code + params |
| Glint | the shared effect-library glint task (grow, shrink, spin left or right at random) | code (`fx_glint.cpp`) + params |
| Glow | while ring tick < `ticks`: grey = start - tick x fade, one byte (wraps) | code + params |
| Overlay | on while the ring's flag 8 is set (ring init to ring end); the target is hidden (entity flag 4) and redrawn by it | code |
| Lifetime | flipbook frame +1 per tick; past the last frame: hidden, done | code |

**Needed:** a library of behaviour kinds, each with its own parameters: `director_per_action`,
`follow_target`, `helix_climb`, `burst_then_drift` (random velocity then integrate),
`spawn_on_circle_rise`, `glint`, `fade_glow`, `flipbook_life`, and phase rules
("at tick T switch flipbook", "at flipbook end do X").

## C. Inputs: what each value is measured against (code)

| Value | Measured from | Where |
|---|---|---|
| Ring centre x / z | the target's anchor (`CopyAnchorXZFromSource`) | `Ring_State0_Init` |
| Ring start y | the target's bounds max y (`BoundsMaxWorldY`, the feet: y is down) minus `start.above` | `Ring_State0_Init` |
| Ring radius | the target's bounds radius (`BoundsRadius`) | `Ring_State0_Init` |
| Ring climb | the target's bounds height (`BoundsHeight`) | `Ring_State0_Init` |
| Mote circle radius | the target's bounds radius | `Ring_SpawnMotes` |
| Mote height | the ring's y and the target's bounds max y | `Ring_SpawnMotes` |
| Projector position | the ring's position, every tick | `RingTask` |
| Overlay height offset | the ring's y | `RingTask` |
| Root position | the caster's bones | `RootTask` |
| Heal | the action and target the emitter was spawned for | `EmitterTask` |

**Needed:** named inputs (target anchor, bounds top / bottom / radius / height, caster bones,
parent position, part tick, action / target index) a value can be bound to, with the scale and
offset parameters that already exist (`fxp::Scaled`, offsets).

## D. Renderers: how each part is drawn (code)

| Renderer | Where | Notes |
|---|---|---|
| Camera-facing flipbook sprite | `DrawSprite` | colour, size, `shade` (depth offset); layer `RenderOT(0x44)` |
| Flipbook frame on a tilted plane on the ground | `DrawAdditiveGlow` | tilt, height, frame, colour from the glow behaviour |
| Projector overlay: the target model redrawn with a projected texture | `DrawTargetModelWithOverlay`, `Overlay_RenderModel`, about 300 lines | shadow first; body and weapon models; projected window, light distance, colour, back-face switch |
| Glint streaks | `fx_glint.cpp` | shared with other effects |

**Needed:** a renderer library chosen by name per part. These four already exist as functions; the
work is giving each a stable interface (inputs: position, flipbook state, colour, size...) instead
of reading Cure's own nodes and globals.

## E. Resources (exe data and fixed names)

| Resource | Today |
|---|---|
| Texture file `mag000-049.tim` (name string at 0x164252C, loaded by `MAG_001_CURE_FL`) | exe, fixed |
| Camera track 0x16417C8 (started by Init) | exe, fixed |
| Five sprite sequences (ring, ring end, glow, sparkle, mote) | params, pointing at exe data |
| Sound block | param, pointing at exe data |
| Projected image (VRAM place, palette, window) | params |

**Needed:** the texture file name and the camera track as description fields (a file, or a
reference to exe data); new sprite sequences and sounds from files (until then only existing ones
can be picked).

## F. Engine work around the effect (code, outside the ported tasks)

1. **Init and the loader are not ported.** FFNx ports the task functions (root, emitter, ring,
   mote, sparkle); `MAG_001_CURE_Init` (queues and pools, the root node, the target loop bounds,
   the camera, the TIM upload, the packet arenas) and `MAG_001_CURE_FL` still run from the exe. A
   new slot has no exe Init, so both must be ported first.
2. **Memory.** The module's memory is Cure's own in the exe (0x277AEC0..0x2792E78: texture file,
   packet cursor and arenas, queues and pools, overlay vertex buffer, sprite block and context) and
   the effect library's glint cursor 0x2792E74 and camera snapshot 0x2793E58. The port reaches it
   through accessors (`PacketCursor()`, `QParticles()`, `Overlay()`...); a host must point them at
   its own memory.
3. **Packet arenas:** two, swapped each tick by the root (`tick & 1`).
4. **Random numbers:** `CrtRand` call order is part of the result: sparkle x, z, y; per mote angle
   then drop; per glint the spin side. A description must keep the order its parts call in.
5. **Integer details** the port keeps for exactness: truncating divisions (`/ -20`, `/ -48`), the
   glow grey wrapping as a byte, the glow colour's 4th byte taken from the node address (a stack
   quirk of the original).
6. **Handshakes:** the root's `busy` flag (set by the root, cleared by the ring), entity flag 4
   (hide / show the target), the heal call.

## A description for Cure (sketch)

```json
{
  "slot": 1,
  "resources": { "texture": "mag000-049.tim", "camera": "exe:0x16417C8" },
  "director": { "kind": "per_action", "spawns": ["emitter"] },
  "parts": {
    "emitter": { "behaviour": "follow_target",
                 "events": [ { "at": "emitter.sound_tick", "do": "sound" },
                             { "at": "emitter.heal_tick", "do": "heal" } ],
                 "spawns": [ { "part": "ring", "at": "ring.start.delay" } ] },
    "ring":    { "behaviour": "helix_climb", "renderer": "sprite",
                 "bind": { "centre": "target.anchor", "start_y": "target.bounds_bottom",
                           "radius": "target.bounds_radius", "climb": "target.bounds_height" },
                 "phases": [ { "at": "ring.ending.tick", "do": "flipbook ring.ending" },
                             { "at": "flipbook_end", "do": ["unblock_director", "end"] } ],
                 "spawns": [ { "part": "sparkle", "per": "step", "window": "sparkle.window" },
                             { "part": "mote", "per": "tick", "count": "mote.count" },
                             { "part": "glint", "per": "tick", "count": "glint.count" } ],
                 "draws": [ "glow", "overlay" ] },
    "glow":    { "renderer": "ground_flipbook", "behaviour": "fade_glow" },
    "overlay": { "renderer": "projector_overlay", "bind": { "projector": "ring.position" } },
    "sparkle": { "behaviour": "burst_then_drift", "renderer": "sprite" },
    "mote":    { "behaviour": "spawn_on_circle_rise", "renderer": "sprite",
                 "bind": { "radius": "target.bounds_radius", "below": "ring.height_over_target" } },
    "glint":   { "behaviour": "glint", "renderer": "glint" }
  },
  "params": "the HealRingParams values, as today"
}
```

Potion's description is the same with its own sequences and sound.

## Work, in order

1. **Port Init and the loader** for Cure and Potion, so the whole effect runs from FFNx code, and
   route all module memory through the accessors. Check: the port tests still pass.
   *Done (FFNx edcbd086):* both modules port their `Init` and `FL`, registered like the task
   functions; FFNx's `install()` points every dispatch slot whose original has a port at the port
   (the recorder replaces them with a jump, as for the tasks). Every module address is named in the
   module's address block. The recordings of both effects stay identical to the original's.
2. **Resources as parameters:** texture file name, camera track.
   *Done (FFNx bcc75c05):* the texture is `files.texture`, a new parameter type (`File`, a
   magic-folder file name, empty = the game's) the ported loader reads; the recorder takes it as
   text and Fujin shows it in a **Files** tab. The camera needs no parameter: FFNx already plays
   `<direct>/exe/effect_NNN.bcam` for any effect id (FFNx PR #1047, `effect_camera.cpp`), and it
   wraps whatever setup the dispatch slot holds, so the ported one and a new slot's alike.
   Found on the way: FFNx never loads parameters in game. They only reach the ports in the
   recorder (`params=`); Fujin's exported parameters had no reader yet. The host (step
   4) has to load them, the same way as the camera files.
3. **Split the heal ring into the libraries above** (behaviours, renderers, inputs), each with a
   stable interface, Cure rebuilt from them in C++. Check: port tests.
   *Done (FFNx 26bea9eb):*
   - `fx_parts.h`: the effect library's node header and calls; the inputs (target anchor, bounds
     bottom / radius / height, caster bones); behaviours (`FlipbookExpired`, `Drift`,
     `RollVelocity`, `OnCircle`, `HelixPlace`, `FadingGrey`); renderers (`DrawSprite`,
     `DrawGroundFlipbook`, `SpawnGlint`). Each takes plain values, not a module's nodes or memory.
   - `fx_overlay.h`: the projector overlay renderer, its look (colour, distance, back faces)
     passed in.
   - `mag_heal_ring_code.h`: `HealRing<Layout>`, the heal-ring module written once from those
     pieces. A `Layout` says where one copy is: its original functions, its exe data, its memory.
     `mag001_cure.cpp` and `mag050_potion.cpp` are now only their layouts (about 2,300 lines of
     duplicated code gone). Recordings of both stay identical to the original's.
   - What is still code in the module: the phase order of each task, which part spawns which,
     and which input feeds which value. That is what the description (step 4) has to carry.
   - The True30FPS branch's per-module 30 fps memos (`mag001_cure_held.inc`...) have to follow
     the template when that branch takes this one.
4. **The description format and its loader**, and the runtime that builds an effect from it. Check:
   Cure and Potion from their descriptions alone pass the port tests.
   *Done:*
   - **Descriptions:** `FF8GameData/Resources/json/effects/effect_001.json` (Cure) and
     `effect_050.json` (Potion). Each holds the parameters with the game's values, parts and
     groups (what Fujin's part tabs show), and the tasks: each task's pool, every-tick actions,
     phases (each-tick actions, a wait condition, actions), motion, per-step and per-tick spawns
     (window, count schedule, placement), events and draws (part tag, flag gate, tick limit,
     renderer). It also says where an effect of the exe has its copy (the functions it stands in
     for, its memory).
   - **Compiler:** `Fujin/effectprogram.py` resolves names (`$key` parameters, tasks, pools, parts,
     flags), checks every operation's arguments, and writes a program: one directive per line.
   - **Runtime:** `Tools/fxhost/fxprogram.h` (C++, uses FFNx's parts library). Each directive is a
     call into the library; a task's tick runs every-tick actions, phase, motion and step spawns,
     spawns, events, draws, then counter and end. Also the per-action director, the setup and the
     file loader. The recorder runs it with `program=<file>`, `params=` setting its parameters.
     It is C++ because effects run as native code next to the game's engine functions, in the
     recorder for the preview and, later, in the game itself: one runtime for both.
   - **Checked** (`tests/Fujin/test_effect_program.py`):
     - Cure and Potion run from their programs record exactly what the exe's code records.
     - With parameters, a program records exactly what FFNx's port records with the same values.
     - Cure's description with no exe functions, set as effect 224 (a free slot), runs as a new
       effect and records exactly Cure.
     - Editing the description changes the effect (the ring without per-step sparkles: no
       sparkles; motes with a sparkle's random velocity).
   - Still tied to the exe: a description uses existing memory (Cure's) and exe data (flipbooks,
     sound, camera). Own memory and data from files come with the host DLL (step 6).
5. **Hypnotize** through the same path, adding what its parts need to the libraries. This measures
   how general the libraries really are.
   *Done:* almost nothing of the heal ring fit Hypnotize, so the libraries grew instead of bending:
   - **FFNx `fx_layouts.h`** (parts library, prim-model layouts): the prim-player callback,
     `Play`, the frames (`ViewFrame` on the caster's screen point, `BonePoint` + `CameraAnchor` at
     a point of the caster's bones, `ScaledCamera`), the inputs (`RandomEntity`,
     `RandomBonePoint`) and `DrawSequenceSprite`. `mag133_hypnotize.cpp` is rebuilt from them
     (its port test still records the original).
   - **Runtime and compiler**, what the description can now say:
     - *Plain nodes:* a task lists its `node` fields (`counter`, `pos`, `scale`, `point`,
       `targets`, `["layout", size]`), laid out in that order after the engine's node header. It
       has an `end` condition (`tick_at_least`, `layout_end`) and `draws_first`. The heal ring's
       nodes stay the effect library's.
     - *Master director* (`kind: master`): alternates the two `magic_buffer` arenas, sets up the
       pools at `start_tick` (storage `in_magic_buffer`), and starts one task with the targets of
       action 0 (`action_targets` and its layout). Its setup is Hypnotize's `Init`.
     - *Spawns:* a spawn can come `every` n ticks of its window. New placements:
       `table_point`, `random_target_bone`, `random_target_point`.
     - *Draws:* `layout_on_screen`, `layout_at_caster_bone`, `layout_scaled`, `sequence_sprite`;
       a draw limit `while_tick_at_most`.
     - *Events:* `heal_all_at`.
   - **Description:** `effect_133.json`.
   - **Checked** (`tests/Fujin/test_effect_program.py`):
     - Hypnotize from its description records exactly what the exe's code records.
     - With parameters, it records exactly FFNx's port with the same values.
     - As effect 225, a free slot with no exe function, it records Hypnotize.
   - **What it shows:** two effects that share no part now run from one runtime. Each new family
     of parts still costs library code once (a renderer, a placement, a director kind). After
     that, an effect built from existing parts costs only a description.
6. **Fujin:** edit the description (parts, links, bindings) beside the parameters, and write the
   host DLL's files for a free slot (224, 225, 346-400; the game's dispatcher `Magic_GetIDLoad`
   0x50AF20 reads `MagicList_Logic` / `MagicList_TextureLoad` and falls back to slot 0 when empty).
   *Done:*
   - **`FujinEffects.dll`** (`Tools/fxhost/fxhost.cpp`): one generic DLL for every effect.
     - The recorder's `build.bat` builds it from the same sources (FFNx's effect sources and
       `fxprogram.h`); CI ships it in the release (`Tools/fxhost`).
     - On load it starts a thread (no file reading inside `DllMain`). The thread reads
       `<game>/FujinEffects/effect_NNN.fxprog` with `CreateFileW`, which Junction VIII redirects to
       a mod folder's file. The folder is the DLL's own: FFNx reads nothing in it (FFNx's
       `direct/exe` holds only what FFNx reads, such as the `.bcam` cameras).
     - For each program found, it points the effect's two dispatch slots at that slot's own file
       loader and setup. The program then runs by itself: the `function` addresses are dropped, and
       its own director, setup and tasks run.
     - A vanilla effect with a program (Cure with edited parameters) is replaced by it. A free slot
       becomes a new effect.
     - Programs carry their parameter values, so **parameters now reach the game**.
     - Each slot also gets its own director function, which selects its program every tick, so
       several programs can be installed at once.
     - It coexists with FFNx: FFNx only rewrites a slot that still holds an original it has a port
       for, and its camera files wrap any setup.
     - Messages go to `%LOCALAPPDATA%\FujinEffects.log`.
     - The recorder loads it as the game does: `host=<dll> hostdir=<game folder>`.
   - **Install for the game:** Fujin's Save folder is the mod's content. Put `FujinEffects.dll` at
     the mod's root, with `<LoadLibrary>FujinEffects.dll</LoadLibrary>` in its `mod.xml`. The
     `FujinEffects/*.fxprog` files go in the mod's folder. A new effect plays when a kernel.bin entry
     names its effect id (SolomonRing: the spell's or attack's effect).
   - **Fujin:**
     - Choreography has a **Description** tab: the effect's description as JSON. Apply checks that
       it compiles; an edited description of Fujin's goes back with *Fujin's description*.
     - **New effect from this…** copies the shown description into a free slot. It has its own
       name, keeps its parameters, and records `base` (whose files and exe data it uses; its memory is its own).
     - Its part tabs and both previews run from its program (`program=` in the recorder).
     - **Save** writes:
       - **one file per effect**, `FujinEffects/effect_NNN.fxprog`, for every described effect
         with a change (edited parameters, edited description, new effect):
         - first, the program with its parameter values: what the DLL runs;
         - then one `#source` line (JSON) the DLL skips, holding what Fujin reopens the effect from
           (Import complementary, Fujin effects): the edited values, and the description when it
           was edited or is new. Its own data's bytes are not repeated there: Fujin takes them back
           from the program's `data` lines.
         - The earlier `.fxparams` and `.fxdesc` files are gone. A file of an earlier Save whose
           effect is back to the game's is removed.
       - `FujinEffects.dll`.
   - **Checked** (`tests/Fujin/test_effect_host.py`):
     - The DLL in the recorder, from a saved-style game folder:
       - Cure copied as effect 224 records Cure;
       - Cure with edited parameters records FFNx's port with them;
       - Hypnotize records itself.
     - The Description tab: apply errors, edit, New effect, Save, Import, reset and delete.
   - **Own memory:** a new effect works in memory of its own, not its base's exe memory.
     - `own_memory` lists, in the description, each name its base's copy had and its size in bytes:
       words 4, the root queue 0x10, the root pool 2 x 0x64 (per-action) or 0x14 (master), the
       overlay context 0xF8, its draw descriptor 0x40, its vertex buffer 0x6400 (Cure's room).
     - Its pools are `own` (queue and storage allocated); Hypnotize's storage stays in the magic
       buffer, at its offsets.
     - The runtime allocates one zeroed block per program after parsing it.
     - Checked: Cure's and Hypnotize's copies (224, 225) record exactly the originals, through
       `program=` and through the DLL.
   - **Own data:** a new effect made with the exe open reads no exe data.
     - Each shipped description lists `exe_data`: every exe item it reads, with address, size and
       kind. Its values name them `@key`.
       - Cure and Potion: 5 sprite sequences, the sound block, the texture file name, the camera
         track.
       - Hypnotize: its sequence, main layout, 8 ring and 8 target layouts, the ring points, the
         two layout tables (`pointers`), the sound, the name, the camera.
       - Sizes come from the formats: a sequence's last frame, a camera track's header. Layouts
         come from the module's contiguous data; each checked against the next item's address.
     - `new_effect(..., exe)` copies them into `data`: bytes as `hex`, tables as `pointers` to
       other keys, `from` = where each came from. The program carries `data` / `data_pointers`
       lines, and the runtime allocates them and resolves `@key`. A program file is then
       self-contained.
     - Part tabs show the exe copy (`from`) of a sequence or sound parameter. Picking another exe
       sequence still works: the game value stays the effect's own.
     - The recorder logs a sound's world id with its block (`S t address id`), so the preview
       plays a new effect's sounds.
     - Checked: Cure's and Hypnotize's copies with their own data draw exactly what the originals
       draw and play the same sounds. Only the recorded addresses of sequences and sound blocks
       differ. No exe address is left in their programs.
   - **Part by part** (`Fujin/effecttemplates.py`): a free slot shows **Create a new effect
     here**, which makes an empty effect. Choreography's **+** tab (always the last tab) adds
     parts; right-clicking a part's tab removes it, with the parts that need it.
     - Each part is a piece of an effect Fujin describes. Each owns:
       - its parameters (by part key);
       - its tasks;
       - the actions it adds to its host's phases (the overlay: `overlay_start`, `hide_target`,
         `show_target`, `overlay`);
       - its draws (by part);
       - its spawns (by task / pool);
       - its data (what remains named).
     - An effect is built from its source effect's whole description, keeping what its parts
       bring, in the source's order. So all of a family's parts are that effect exactly, in any
       order, and a subset is a smaller effect of the same kind.
     - Two families do not mix: their nodes and directors differ.
       - Cure's: Emitter, Helix ring, Projector overlay, Ground glow, Sparkles, Motes, Glints,
         Texture file.
       - Hypnotize's: Main, Layout in front of the caster, layouts at the caster's or targets'
         bones, Sprites around a target.
     - The description records its `template_parts`. Adding or removing a part rebuilds it from
       them; data edited in the Data tab is kept, hand edits to the JSON are not.
     - An effect with no start yet is saved with no program (`# incomplete`); the DLL leaves its
       slot alone.
     - Checked (`tests/Fujin/test_effect_templates.py`):
       - every valid combination compiles (66 of Cure's, 16 of Hypnotize's);
       - all of a family, added in reverse, compiles to exactly its effect;
       - Cure built by hand from an empty slot records exactly Cure;
       - Emitter, Helix ring and Sparkles alone draw only the ring and its sparkles;
       - Fujin's create button, + menu, add / remove, Save and Import.
   - **Data editors:** Choreography's **Data** tab (`Fujin/effectdataview.py`) edits a new
     effect's own data by kind. Apply writes an entry back; the previews record again.
     - `seq`: palette-row parameters, frames (add / remove), and each frame's pieces in a table:
       width, height, u, v, CLUT, x, y, angle, flags, scale, intensity, GPU code. Pieces can be
       added and removed. Frames are drawn from the last recording's VRAM. It re-encodes with
       `encode_sequence`: 301 of the exe's 326 sequences come out byte for byte; the rest have
       gaps or shared frames in the exe but parse back the same.
     - `sound`: the world sound id, its audio.dat entry and Play.
     - `table`: int16 values, 4 a row (Hypnotize's ring points).
     - `name`: the file name.
     - `pointers`: each entry picked among the data keys (Hypnotize's ring and target layouts).
     - `layout`: a prim-model layout's animation (`FF8GameData/psxgpu/primlayout.py`).
       - Editable: its length in frames; each object's flags (low byte = its model, 0x200 = its
         offset not rotated); its tracks (add / remove); each track's keys (add / remove, frame
         and values).
       - Tracks: position, rotation, scale and colour, each as value / velocity / acceleration;
         channel A (fade); channel B (vertex-frame blend).
       - 16.16 values show as decimals; 5 places give the int32 back exactly.
       - Its models (vertex frames, polygons) are kept as they are.
       - Format, from FFNx's player twin:
         - model table at +8, header offset at +4;
         - header: object count, frames, object offsets;
         - object: flags, track flags, one key-table offset per track flag set;
         - key tables: keys in frame order, then a 4-byte −1.
       - All 17 of Hypnotize's layouts encode back byte for byte.
     - `camera`: a read-only summary (the Camera tab edits it; its `effect_NNN.bcam` replaces it in
       the game).
     - Checked (`tests/Fujin/test_effect_data.py`): each editor's Apply reaches the program. A
       sequence, a sound and a layout edited change what the recorder draws and plays.
   - **Not done yet:**
     - Tried in the real game.
     - Editing a layout's models (vertex frames and polygons: their format, drawn by 0x7043B0, is
       not decoded yet).
     - New data from scratch: today it is the exe's, copied, then edited.
     - A structured editor: the description is edited as JSON text.
