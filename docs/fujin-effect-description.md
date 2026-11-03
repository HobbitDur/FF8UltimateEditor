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
     - **New effect from this…** (above Fujin's tabs) copies the shown description into a free
       slot; a free slot's **Copy an effect here…** asks which effect to copy. The copy has its own
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
       - Cure's: Emitter, Ring, Overlay, Ground glow, Sparkles, Motes, Glints, Files.
       - Hypnotize's: Timing, Main layout, Rings, Target layouts, Sprites.
     - A part is named as its tab: its part's title in its source effect's description.
     - Adding a part adds the parts it needs that the effect does not have yet (Sparkles on an
       empty effect: Emitter, Ring and Sparkles).
     - The description records its `template_parts`. Adding or removing a part rebuilds it from
       them; data edited in the Data tab is kept, hand edits to the JSON are not.
     - An effect with no start yet is saved with no program (`# incomplete`); the DLL leaves its
       slot alone.
     - Checked (`tests/Fujin/test_effect_templates.py`):
       - every valid combination compiles (66 of Cure's, 16 of Hypnotize's);
       - all of a family, added in reverse, compiles to exactly its effect;
       - Cure built by hand from an empty slot records exactly Cure;
       - Emitter, Ring and Sparkles alone draw only the ring and its sparkles;
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
7. **More effects, one at a time**, each one reusing the libraries where it can and adding only
   what nothing covers. Each is checked as Hypnotize is (`tests/Fujin/test_effect_program.py`): from
   its description it records exactly what the exe's code records; with parameters, exactly what
   FFNx's port records with them; as a free slot with no exe function, itself again.
   - **Antidote (294)** (FFNx 736a2d6c, 522e7ac4, 9b2e6c15), the first of the five status-cure item modules (292 Soft,
     293 Eye Drops, 294 Antidote, 295 Echo Screen, 296 Holy Water: one source built five times with
     different options). One prim layout played on the target; the target takes the result when
     it ends.
     - *Shared with Hypnotize:* the master director (arenas, pools at tick 1, one started task,
       the end when every queue is empty), plain nodes, the prim player, its layouts and their
       data editor, the `layout_end` condition, the effect's file and setup (no camera: an
       effect may have no `camera` resource, then it starts no camera track).
     - *Added to the libraries* (FFNx `fx_layouts.h`, the runtime, the compiler):
       - the anchor callback `AnchorPrimCallback`: each object's offset added to an anchor,
         through the camera. The record flags a build tests are an argument (0x100 diagonal
         scale, 0x200 offset as is, 0x400 ZYX angles, 0x8000 not turned with the camera, 0x40000
         YXZ angles), so all five modules can share it. Draw `layout_at_anchor` (depth, flags);
       - the input `AnchorPoint`: an entity's effect position, that point between two shares of
         its height (`HeightPoint`: y + (h x a + h x b) / 2), or the effect point of a bone.
         Director placement `target_anchor` (kind, bone, times a, share a, times b, share b,
         layout): the started task's `anchor` (a new node field, 8 bytes) on target 0 of action 0;
       - the director's own `events` on its counter, after its queues, or `events_first`, before
         them (`sound_at`: Antidote's sound plays on the root's clock, not a task's);
       - a task's `at_end` actions, run when its end condition holds (`heal_first_target`: target
         0 of action 0 takes the result when the layout ends).
     - *Inputs* (`StatusItemParams` in FFNx, the description's parameters): the sound, its tick
       and pan; the layout's depth; the anchor: its kind (0 the effect position, 1 between two
       shares of the height, 2 a bone's point), its bone, its two shares (1 / 2 and 1 / 2 in the
       game).
       The layout itself is data (`@layout`, 0x2B4C bytes in the exe, edited in the Data tab).
     - *Fujin:* its tabs (Timing, Layout); a third family in the + menu, "One layout on the
       target (Antidote's kind)": Layout (the start) and Timing (its sound).
   - **Soft (292)** (FFNx 522e7ac4, 9b2e6c15): Antidote with its own data and one more record flag tested
     (0x200: the anchor through the camera, then the object's offset as is, not turned).
     - *Shared:* everything. FFNx's `mag_status_item.h` writes the module once
       (`StatusItem<Layout>`, as `HealRing<Layout>` does for Cure and Potion): Antidote and Soft
       are only their layouts (functions, data, memory, the record flags their callback tests).
       Their descriptions differ in addresses, sizes and the draw's flags (0x48000, 0x48200).
     - *Inputs:* Antidote's (`StatusItemParams`); its layout (0x22B0 bytes), sound and texture
       name ("mag291.tim") as data.
   - **Eye Drops (293), Echo Screen (295), Holy Water (296)** (FFNx 9b2e6c15): the rest of the
     family, each a layout of `StatusItem<Layout>` too. What each adds is a build option of the
     shared module, a parameter's game value or a director switch, not code of its own:
     - Eye Drops: always turned with the camera, 0x100 (scaled by a diagonal matrix), anchor 2
       at bone 0xF0 (flags 0x40300);
     - Echo Screen: 0x400 (ZYX angles) and 0x1000 (each offset through a camera matrix of the
       effect's own, 0x67AAE0 of the camera every tick: the description's `camera_matrix`, memory
       `camera_matrix`, 0x20 bytes in a new effect), anchor 0 (flags 0x9500);
     - Holy Water: anchor 1 between 2 / 3 and 1 / 2 of the height ((2h / 3 + h / 2) / 2), its
       sound before the play queue (`events_first`; flags 0x40200).
     - The five descriptions differ only in addresses, sizes and those options. The program
       tests run all five: from its description each records exactly the exe's code;
       with parameters, FFNx's port; as a free slot, itself; with its own data and memory, the
       same draws and sounds.
   - **Silence (122)** (FFNx b972cad3), the first of the status spells whose root starts one target
     task per action, one every 10 ticks (Float, Silence, Haste, Slow, Petrify Stare, Dispel, Aura,
     Aero, Blind, Zombie, Flare, Reflect, Berserk...). Its task plays a layout at an effect point of
     the action's target, taken again every tick; the target is marked (flags word bit 0x2000) while
     it plays.
     - *Shared:* the anchor callback (flags 0x200 and 0x100: Soft's and Eye Drops' branches), plain
       nodes, the prim player and its data editor, the arenas, the file loader.
     - *Added:*
       - a third director kind, `cycle` (`every`: a parameter): at counter 1 of every n ticks the
         next action's task, placed by `action_target` (mark bits, layout): its `action` and
         `entity` (new node fields), the entity marked. Its setup (Silence's 0x6BD910): the camera
         and the texture upload only when the cast does not repeat (flags & 1);
       - plain nodes take every-tick actions: `anchor_at_bone` (this tick's anchor: an effect point
         of the node's entity, when the node keeps no anchor) and `sound_3d_at` (BdPlaySE3D at that
         anchor);
       - the draw `layout_on_target` (depth base, shift, flags, nearer object, by): the anchor
         callback at this tick's anchor, its depth from the target's size word
         (`DepthFromSize`: (base - size) >> shift), one object drawn nearer (object 4, 0x20);
       - `heal_action_at` (the node's action's target takes the result), the end condition
         `tick_above` (the counter, before its step, reached the value), `unmark_target`.
     - *Inputs* (`SilenceParams`): the cycle, the sound's tick and volume, the damage and end
       ticks, the bone, the depth's base and shift, the nearer object and how much nearer. Data:
       its layout (0x37A8 bytes), camera track (2600 bytes), sound, texture name ("mag121.tim").
     - *Fujin:* its tabs (Timing, Layout); a fourth family in the + menu, "One per action, on its
       target (Silence's kind)": Layout.
   - **Float (115)** (FFNx 0f34aacc): Silence's director; its task plays two layouts in frames of
     the action's target, turned with it and scaled by its size: the lift glyph at its feet, from
     tick 12 a second layout at its effect point 0xF0.
     - *Shared:* the cycle director and its setup, the action and entity fields, the 3D sound,
       the action's result, `tick_above`.
     - *Added:*
       - FFNx's frame callback `FramePrimCallback` (Float 0x6C9760; Haste's and Slow's ClockPart
         are the same code with more record flags tested): each object's offset scaled, through a
         frame of the target, composed with it. The flags a build tests are an argument (0x100,
         0x200, 0x1000, 0x2000, 0x4000, 0x8000), and so is its renderer (0x7043B0 with the
         header's depth, or 0x572200 without). Inputs: `TargetFrame` (turned with the target, at a
         point of it, composed with the camera), `SizeScale` (((size >> 1) + base) >> shift),
         `PointDepth` (a point's depth in the frame, by the target's size);
       - the draw `layout_turned` (layout, bone, on its feet, depth, depth point, scale base,
         shift, flags), a second layout node field `layout_b` (placed by `action_target`'s third
         value), the every-tick action `anchor_at_position` (the 3D sound at the target's
         effect position) and the draw limit `from_tick`.
     - *Inputs* (`FloatParams`): the cycle, the sound's tick and volume, the damage and end
       ticks, the size rule, the glyph's and the upper layout's bones, the upper layout's first
       tick. Data: its two layouts (0x1FE8, 0x21C0 bytes), the depth point, the camera track
       (2508 bytes), the sound, the texture name ("mag114.tim").
     - *Fujin:* its tabs (Timing, Glyph, Upper layout); a fifth family in the + menu, "One per
       action, turned with its target (Float's kind)": Glyph (the start), Upper layout.
   - **Slow (123), Haste (125)** (FFNx 73b62769): the two clock spells, one source built twice,
     now one FFNx module (`mag_clock_spell.h`, `ClockSpell<Layout>`). Silence's director, Float's
     frame callback with every record flag it knows (0x100, 0x200, 0x1000, 0x2000, 0x4000, 0x8000)
     and the engine's renderer 0x572200 (the header's depth not written): a clock at the target's
     feet and a second layout under its effect point 0xF0, lowered by its size (s / 16 + s / 4).
     - *Added:* the cycle director's `camera_matrix` (the effect camera matrix, 0x67AAE0 of the
       camera, every tick, before the queue); node fields `anchor` and `spawn` filled by
       `action_target` (the target's effect position, its effect point given by a fourth value);
       `layout_turned` grows its y rule (the point's, the feet, the spawn point lowered by the
       size), the node's anchor as its point (bone -1), its "scaled" source and the engine
       renderer; a task's layouts all finished end it (`layout_end` over every layout drawn that
       tick); `screen_fade_at`, `blink_target` (Slow: the target's flag bit 3 on the ticks
       e % (40 - e) == 0), `heal_action`.
     - *A vanilla read kept:* Slow's callback tests a "scaled" word its task never writes; it
       holds what 0x67AAE0 left on the stack, the effect camera matrix's m[1][0] (0 unless the
       camera rolls). Slow's description says so (`layout_turned`'s scaled value -1).
     - *Inputs* (`ClockSpellParams`): the cycle, the sound's tick and volume, the fade tick, the
       size rule, the blink's first tick and length (Haste: 0). Data: the two layouts, the camera
       track, the sound, the texture name ("mag122.tim", "mag124.tim").
     - *Fujin:* their tabs (Timing, Clock, Lower layout); a sixth family in the + menu, "One per
       action, a clock on its target (Haste's kind)": Clock, Lower layout.
   - **Dispel (109)** (FFNx b572dbe9): the cycle director again, a second task kind (particles),
     the screen flash.
     - *Shared:* the cycle director, the action / entity / anchor fields, the anchor callback for
       its ring (flags 0x40000 and 0x8000: its callback's "scaled" word is never written, so 0,
       and the scaling branch is dead), the 3D sound, the fade, the action's result, the sequence
       sprite renderer (Hypnotize's) for its particles.
     - *Added:*
       - `action_target` waits while a task of that kind at a given tick or before runs on that
         target (the cycle restarts) and can give the anchor a size word ((size + base) x
         times); its values are now mark, layout, layout b, spawn bone, busy tick, size base,
         size times;
       - `["pad", n]` node fields (bytes the effect leaves alone), `end` and `seq` fields;
       - `screen_flash_curve` (rise, level, fall, end) and `screen_flash_off`;
       - the placements `random_around` (Dispel's sparkles: CRT rand in the original's order,
         spread by the anchor's size word) and `rising_circle`;
       - the draw `node_sequence_sprite` (the node's own sequence and size), the end
         `tick_at_node_end` (its own frame count), a task's `after_draws` actions (the sound and
         the result after the ring);
       - a plain task's draws leave no part tag behind (what it does after them is no part's).
     - *Inputs* (`DispelParams`): the cycle and the busy tick, the sound, the fade / damage / end
       ticks, the flash curve, the ring's depth and size word, each particle kind's window,
       every, lift, size, frames and sequence, the circle's points a turn. Data: the ring layout
       (0x2E10 bytes), two sequences, the camera track (2088 bytes), the sound, "mag108.tim".
     - *Fujin:* its tabs (Timing, Ring, Sparkles, Circle); a seventh family in the + menu, "One per
       action, a flash and a ring (Dispel's kind)": Ring (the start), Sparkles, Circle (they share
       the particle task: it stays while either does).
   - **Aura (111)** (FFNx 58dce00e): the cycle
     director with Dispel's busy-target wait; a layout at the target's feet, flames, a glow.
     - *Shared:* the cycle director, the action / entity fields, the 3D sound at the target's
       effect position, the result, `tick_above`, the sequence sprite renderer (the glow), the
       busy wait.
     - *Added:*
       - FFNx's table callback `TablePrimCallback`: each object's draw mode is a word of a table
         (exe data, one per object; bit 0x10000000: its offset through the frame, its rotation
         kept), the engine's renderer. Draw `layout_table` (words, bone, size shift) in the frame
         `SqrtSizeFrame` (a diagonal of sqrt(size << shift) at the target's feet);
       - spinning models (Aura's flames): the placement `spinning_ring` (count, bone, lift, angle
         step, radius / speed / strength as base + (rand & mask): one angle and speed for the
         tick's flames, CRT rand in the original's order), node fields `radius`, `angle`,
         `speed`, `fade`, the draw `spinning_model` (`DrawSpinningModel`: a prim model turned about
         the view's axis, scaled by the radius, faded in and out by `FadeInOut`, its own draw
         mode and depth offset) and the event `spin`;
       - the draw `sequence_at_feet` (sequence, from, frames, bone, lift, size, angle);
       - `screen_fade_at` takes the engine fade's four values (Haste, Slow and Dispel: 0, 1, 1,
         0x60; Aura: 0, 1, 0, 0x80).
     - *Inputs* (`AuraParams`): 32 values: the cycle, the busy tick, the sound, the damage and end
       ticks, the aura's bone and size shift, the flames' spawning, radius, turn, strength, fade,
       depth, draw mode and life, the glow's ticks, lift, size and angle. Data: the aura layout
       (0x43BC bytes), its 10 object words, the flame model, the glow sequence, the camera track
       (2172 bytes), the sound, "mag110.tim".
     - *Fujin:* its tabs (Timing, Aura, Flames, Glow); an eighth family in the + menu, "One per
       action, at its target's feet (Aura's kind)": Aura (the start), Flames, Glow.
   - **Aero (118)** (FFNx 0f520235): the cycle director with the effect camera matrix; a whirlwind
     at the target's feet and a gust at its effect position, scaled by its size; leaves.
     - *Shared:* the cycle director, its camera matrix (Haste's), the anchor callback with its
       0x1000 branch (Echo Screen's), the depth from the target's size (Silence's), the size
       scale (Float's), the 3D sound, `layout_end` over both layouts (Haste's), `heal_action`.
     - *Added:*
       - the anchor callback takes a scale (each record's offset and the object scaled by the
         target's size; Dispel's ring has the same branch, dead there) and a 16-bit row scale
         option (Aero's inlined copy of the record scale: it is not scale3DMatrix's result).
         Draw `layout_scaled_on_target` (layout, where: the anchor's x / z on the feet or the
         effect position now, depth base / shift, scale base / shift, flags, 16-bit scale);
       - whirl leaves: the node field `leaf` (0x30 bytes: the library's `WhirlLeaf`), the
         placement `whirl_leaf` (size, turn, climb speed, reach base / shift: CRT rand in the
         original's order), the every-tick action `whirl_leaf_move` (climb until, faster from:
         circling and climbing while its spawner is young, then falling, bouncing, shrinking),
         the draw `tumbling_model` and the end `leaf_gone`.
     - *Inputs* (`AeroParams`): the cycle, the sound, the wind's first tick, depth and size rules,
       the leaves' window, first size, turn and climb, when they fall and when they speed up.
       Data: the two layouts (0x4354, 0x149C bytes), the leaf model, the camera track (3348
       bytes), the sound, "mag117.tim".
     - *Fujin:* its tabs (Timing, Wind, Leaves); a ninth family in the + menu, "One per action, a
       wind on its target (Aero's kind)": Wind (the start), Leaves.
   - **Blind (121)** (FFNx 0ff34b84): the cycle director; a layout at the target's effect point
     0xF0, followed for 20 ticks then left there; a screen flash all the target tasks raise.
     - *Shared:* the cycle director, the anchor callback (record flags 0x200, 0x100: Silence's),
       the 3D sound, the screen fades (Haste's), `heal_action_at`, `layout_end`.
     - *Added:*
       - the anchor callback's flag 0x800 (the offset turned by the object's own rotation
         first), its engine renderer option (0x572200, the depth not written, an OT shift) and its
         additive objects (a bit each: those drawn by the library's `AdditiveQuads`, Blind's
         0x6BE4E0: only the model's flat and gouraud textured quads, each after an additive
         draw-mode packet). Draw `layout_engine_at_anchor` (record flags, depth shift, two
         additive objects, -1: none);
       - the every-tick actions `follow_bone` (bone, until: the node's anchor at that point
         while the tick is below `until`) and `flash_level_raise` (from, peak, to, up, down:
         the library's `ScreenFlashRiseFall`, the memory word `flash_level` raised to it);
       - `sound_3d_at_position` (tick, sound, volume: at the entity's default effect position);
       - the cycle director runs director events too: `flash_level_clear` (events_first) and
         `screen_flash_level` (events: the screen flash set to the level every tick, started or
         not).
     - *Inputs* (`BlindParams`): the cycle, the sound, the damage tick, the bone and how long the
       layout follows it, the depth shift, the two additive objects, the flash's ramp and the
       three fades' ticks and values. Data: the layout (18272 bytes), the camera track (2096
       bytes), the sound, "mag120.tim".
     - *Fujin:* its tabs (Timing, Layout, Flash); a tenth family in the + menu, "One per action,
       left on its target (Blind's kind)": Layout (the start), Flash.
     - The recorder logs a hooked insertion its render-list walk misses (Blind's last draw-mode
       packet of a tick) with its order-table bucket index, not the bucket's address.
   - **Petrify Stare (120, 127)** (FFNx 12df3d5d; one module built twice: the Glacial Eye's and the
     Cockatrice's, FFNx's `PetrifyStare<Layout>` in `mag_petrify_stare.h`): the cycle director
     with ONE target node (only the first action plays); a "stare" layout at the caster, a
     "stone" layout on the target from tick 14.
     - *Shared:* the cycle director with Blind's screen flash events (the level stays 0), the
       anchor callback (record flag 0x200; 120's rotation flag 0x400, 127's 0x40000: Echo
       Screen's and Holy Water's), the depth from a size (Silence's), the screen fade, the 3D
       sound and `follow_bone` (Blind's), `heal_action_at`, `tick_above`.
     - *Added:*
       - `"setup": "master"` for a cycle director: set up as the master is (the caster's entity
         kept: memory `caster`; the texture upload first, the camera always);
       - `follow_bone` and `sound_3d_at_position` take whose point (0: the node's entity, 1:
         the caster);
       - the every-tick action `point_at_position` (tick: the node's `point` = the entity's
         default effect position on that tick);
       - the draw `layout_on_point` (layout, the anchor or the point, whose: the node's entity
         or the caster, ahead: the point moved ahead of that entity's facing by the unit circle
         >> it, the library's `AheadOfFacing`, -1: none; depth base / shift from that entity's
         size; record flags);
       - a draw limit `"within": [from, count]` (from .. from + count - 1);
       - the cycle director starts the next action only once its task spawned (its pool full:
         it tries again on the next cycle), as the originals.
     - *Inputs* (`PetrifyStareParams`): the cycle, the sound, the damage, end and fade ticks and
       the fade's four values, the stare's bone, follow time, step ahead and depth, the stone's
       window and depth. Data: the two layouts (120: 9768 / 15804 bytes, 127: 17608 / 22568), the
       camera track, the sound, "mag119.tim" / "mag126.tim".
     - *Fujin:* their tabs (Timing, Stare, Stone); an eleventh family in the + menu, "From the
       caster, then on its target (Petrify Stare's kind)": Stare (the start), Stone.
   - **Zombie (114)** (FFNx 4a39cb68): the cycle director (waiting while ANY target task of 40
     ticks or less runs); a mist layout at the target's effect position scaled by its size; over
     ticks 30..59 the target redrawn lifted and swayed.
     - *Shared:* the cycle director and its busy wait (Dispel's), the scaled layout draw
       (`layout_scaled_on_target`: Aero's, at the effect position now), the additive quads
       (Blind's), the depth and size rules, `sound_3d_at_position`, `heal_action_at`, `tick_above`.
     - *Added:*
       - the director's place takes a ninth value, busy on any target (1: Zombie's; the other
         cycle effects 0);
       - the anchor callback's rotation flag 0x20000 (angles in XZY order, 0x701530) and the
         additive quads' gouraud-only variant (list 8 alone, its depth + the header's, clamped at
         0: Zombie's 0x6CA0E0 / 0x6CA1B0); `layout_scaled_on_target` takes two additive objects
         (-1: none; Aero's none);
       - the library's sway overlay (`fx_sway.h`: Zombie's 0x6CA560, the entity's model redrawn
         lifted and swayed sideways by an s16 [4096] wave table, flat additive polygons from black
         to its tint), drawn by `sway_overlay` (from, ticks, the wave table, reach base / shift,
         lift shift, amplitude base / step, phase step, the cast flags that skip it);
       - the actions `mark_ring_from` (from, bits: those bits on every entity of the node
         entity's +0x8C ring from that tick) and `unmark_ring` (bits).
     - *Inputs* (`ZombieParams`): the cycle and its busy tick, the sound, the damage and end
       ticks, when the mark starts, the mist's depth, size and additive objects, the overlay's
       window, lift, sway and wave step. Data: the layout (13772 bytes), the camera track (2396
       bytes), the sound, the wave table (8192 bytes), "mag113.tim".
     - *Fujin:* its tabs (Timing, Mist, Overlay); a twelfth family in the + menu, "One per
       action, its target swaying (Zombie's kind)": Mist (the start), Overlay.
   - **Flare (124)** (FFNx a7cf09e1): the cycle director with the effect camera matrix and the screen
     flash events (Blind's), not while a task of 60 ticks or less runs on that target; per target
     a flash, two fades, the target turned red and back, a burst and a ring layout scaled by its
     size, over ticks 40..79 the target hidden and redrawn rippled, collapsing sparks.
     - *Shared:* the cycle director, its busy wait (Dispel's), camera matrix (Haste's) and flash
       events (Blind's), the scaled layout draw (Aero's, Zombie's), the anchor callback, the depth
       and size rules, `sound_3d_at`, `screen_fade_at`, `heal_action_at`, `unmark_target`,
       `layout_end`.
     - *Added:*
       - the node field `colour` (the target's colour before the task): the director fills it,
         from the target or from an older task still on it (Flare's hand-over);
       - the actions `flash_level_hold` (rise, up, level, fall after, end, down: the library's
         `ScreenFlashRiseHoldFall`), `flash_level_set` (tick, level), `mark_target` (bits, every
         tick) and `tint_target` (the tint, from, ticks, shift, back from, back ticks, back shift:
         the library's `TintEntity`);
       - `layout_scaled_on_target`: at 2 (the node's anchor as is), a depth shift of -1 (the base
         as is), two far objects (at a quarter depth: Flare's 2 and 3; the anchor callback's
         `far_objects`); the anchor callback tests 0x1000 before 0x200 (Flare's order: no other
         build honours both);
       - the library's ripple silhouette (`fx_ripple.h`, Flare's 0x6BC8A0: the entity hidden and
         redrawn flat in its colour, its vertices rippled around a point, after its shadow, into
         the frame arena), drawn by `ripple_silhouette` (from, ticks, its three tables as one data
         block: the distance lookup reads one row past its own table) with the node field
         `ripple` (the last draw's largest offset);
       - the library's collapsing sparks (`CollapseSpark*`): the node field `spark`, the
         placement `collapse_sparks` (count, collapse window, turn, sprite size, scale base /
         shift; stops when the pool is full), the actions `spark_step` (burst, fade) and
         `spark_move`, the draw `spark_sprite` (sequence), the end `spark_gone`.
     - *Inputs* (`FlareParams`): the cycle and its busy tick, the sound, the damage tick, the
       flash's curve, fade and set ticks, the tint's two ramps, the layouts' depth and size, the
       silhouette's window, the sparks' ticks, count, collapse window, turn, sprite size, burst
       and fade ticks. Data: the spark sequence, the two layouts (39352 / 2812 bytes), the camera
       track (3548 bytes), the sound, the ripple tables (29696 bytes), the red, "mag123.tim".
     - *Fujin:* its tabs (Timing, Burst, Ring, Silhouette, Sparks); a thirteenth family in the +
       menu, "One per action, a burst on its target (Flare's kind)": Burst (the start), Ring,
       Silhouette, Sparks.
   - **Reflect (106)** (FFNx dcb47aa1; Carbuncle's Ruby Light's "ruby" part in its own copy): the cycle
     director starting one barrier per action at counter 0 (not while one of 35 ticks or less runs on
     that target); a frame turned with the target, a wall model growing up through it, hexagons
     orbiting a point climbing the wall, rings above the target. No magic buffer: its pools and
     packet arenas are module memory.
     - *Shared:* the cycle director and its busy wait, `sound_3d_at_position`, `heal_action_at`,
       `tick_above`, the plain spawns (every few ticks of a window).
     - *Added:*
       - the director's `"spawn_tick"` (the counter it starts a task at; Reflect 0) and
         `"seed_shared_rand"` (the setup seeds the effects' shared LCG, 0x2557098, with a CRT
         rand, as Reflect's _Init); the memory `packet_arena_a` / `packet_arena_b` (0x10000 bytes
         each) for arenas of the effect's own, with no `magic_buffer`;
       - the library's barrier (`fx_barrier.h`): the node fields `barrier` (its frame, view and
         climbing centre: the director puts it at the middle of the target's effect points 0xF0
         / 0xF1), `orbit` and `growth` (a hexagon's and a ring's, each pointing at its barrier);
         the actions `barrier_frame` (size shift), `barrier_center` (wall, ticks, steps),
         `dead_beams` (ticks, count, the beam pool: Reflect's vanilla dead beams, never drawn,
         still drawing shared rands while their pool has room), `orbit_move`, `growth_step`
         (least growth); the placements `orbit_spawn` (count, tilt, angle step, turn, tilt speed
         base / mask: shared rands) and `growth_spawn` (wall, wall from, grow, size, growth,
         brake, size shift); the draws `barrier_wall` (wall, from, ticks, grow, fade: the wall's
         textured quads, gouraud triangles and gouraud quads between texture windows, its V
         scrolling, its vertices drawn up to its growing top: the height range measured from the
         model as _Init does), `orbit_model` (model, fade from / ticks, draw mode, sin / cos
         table) and `growth_model` (model, fade ticks, draw mode).
     - *Inputs* (`ReflectParams`): the cycle and its busy tick, the sound, damage and end ticks,
       the frame's size shift, the wall's window, growth and fade, the hexagons' count, climb,
       tilt, angle step, turn, tilt speed, end and fade, the rings' spacing, last tick, size,
       growth, brake, end and fade, the dead beams' count. Data: the wall, hexagon and ring
       models, the camera track (1968 bytes), the sound, the sin / cos table, "mag105.tim".
     - *Fujin:* its tabs (Timing, Wall, Hexagons, Rings); a fourteenth family in the + menu, "One
       per action, a wall around its target (Reflect's kind)": Wall (the start), Hexagons, Rings.
   - **Berserk (108)** (FFNx 2049d2ec): the cycle director (not while a main task of 43 ticks or less runs
     on that target); per action ribbons spiralling in, a flash and a pulsing glow, a burst layout at
     the target's feet, embers rising, sparks, light rays turning around the target; the result at
     43, the end once the rays are gone.
     - *Shared:* the cycle director and its busy wait, the table callback (Aura's: one word per
       object for its draw mode; now with an offset, Berserk's spawn point, the camera its frame),
       the sequence sprite, the texture windows and the Z rotation (Reflect's), `screen_fade_at`,
       `sound_3d_at_position`, `heal_action_at`, the plain spawns (windows, every few ticks).
     - *Added:*
       - the library's light rays (`fx_rays.h`, Berserk's 0x6D0B40 / 0x6D0600: a table of 32 rays,
         each a Gouraud triangle + quad turning around a point, fading, growing): the node fields
         `rays` (0x600 bytes) and `drawn` (the rays drawn this tick), the action `ray_spawn` (from,
         ticks, count, colours, turn, length, its speed and brake, width, its speed and brake), the
         draw `light_rays`, the end `rays_done` (after a tick, once no ray was drawn);
       - the library's swirl ribbon (`fx_ribbon.h`, 0x6D0C20: up to 32 positions spiralling in,
         textured Gouraud quads between texture windows): the node field `ribbon`, the placement
         `ribbon_start` (angle, step a spawner tick, wave), the draw `ribbon` (push ticks, per
         tick, angle step, fade, the two windows' RECTs), the end `ribbon_done` (after a tick, fewer
         than two positions);
       - the library's sprite motes (0x6D1250: a sequence in place, frame its counter; rising ones
         decelerate): the node field `mote`, the placements `ember_ring` (count, sequence, scale,
         angle step, distance base / mask, lift shift, acceleration base / mask: CRT rand in the
         original's order) and `spark_near` (sequence, scale, mask, offset), the action `mote_step`
         (rising, frames), the draw `mote_sprite`, the end `mote_done` (frames); the original's one
         particle task is two here (embers and sparks, one pool);
       - the draws `sequence_at_anchor` (sequence, from, rotation a, b), `pulse_model` (model,
         from, ticks, scale base, fade base, draw mode: the library's `PulseModelDraw`) and
         `layout_table_at_spawn` (the words); the action `spawn_to_feet` (tick: the spawn point's
         height on the entity's feet).
     - *Inputs* (`BerserkParams`): the cycle, sound, damage, end and fade ticks, the swirls (last
       tick, angle, step, wave, pushes, fade, end), the flash, glow and burst windows (the glow's
       size and fade), the embers and sparks (windows, count, spacing, distance, lift, acceleration,
       spread, frames), the rays (window, count, turn, length, width and their motion). Data: the
       three sequences, the glow model, the burst layout (15892 bytes), the camera track (2360
       bytes), the sound, the texture windows, the ray colours, the burst's words, "mag107.tim".
     - *Fujin:* its tabs (Timing, Swirls, Flash, Glow, Burst, Embers, Sparks, Rays); a fifteenth
       family in the + menu, "One per action, rays around its target (Berserk's kind)": Rays (the
       start), Swirls, Flash, Glow, Burst, Embers, Sparks.
   - **Fire (2)** (FFNx 48a76e86): a fourth director kind, the chain: one director task per action,
     each starting the next action's at its own tick 12; several targets: one flame around each, the
     result on all of them, the sound panned; a lone target: its director waits until no other Fire
     burns on it (the 7 "target free" words), then 4 flames around it, the result, the sound at its
     effect position, the target free again at its end (22). Each flame a flipbook over a ground
     glow, at its first frame 4 embers and 10 sparks.
     - *Shared:* `heal_action_at`, `sound_3d_at_position` (its entity now the node's slot's when it
       has no entity field), the plain spawns (every tick of a window), `tick_at_least`.
     - *Added:*
       - the director `chain` (several targets' task, the lone target's): the setup (the cast, its
         attacker, every slot free, a root of 0x10 bytes, the pools, action 0's director; the camera
         and the texture upload unless the cast repeats), the root (`packet_arena_a` / `_b` by its
         counter's parity, the queues, the end when they are empty); the action `chain_next` (tick:
         the next action's director when the node's chain counter is at it), the hold
         `claim_target` (a task's `hold`: its tick stops there while it holds), the action
         `release_target`; the node fields `slot` and `chain`;
       - a task's `draw_only` (what it does while the battle only draws: `skip`, nothing;
         `after_draws`, its first draws only) and its `delay` field (a plain node waits it out,
         not counting while the battle only draws);
       - the library's fire (`fx_flames.h`, Fire's 0x629C10 / 0x62A0A0 / 0x629F90; Firaga's area
         flame draws as the flame): the node fields `flame`, `ember`, `fire_spark` and `life`; the
         placements `flames_on_targets` (all targets or the lone one, count, delay, spread, lift,
         size), `flame_embers` and `flame_sparks` (around the spawner's flame, CRT rand in the
         original's order); the draws `flame` (its flipbook, then its ground glow, its grey from the
         flame's height), `ember`, `fire_spark` (a shared effect sprite, its frame from its life);
         the actions `ember_rise`, `fire_spark_move`, `heal_action_all_at`, `sound_pan_at` (BdPlaySE
         with a volume and a pan); the end `life_out`.
     - *Inputs* (`FireParams`): the chain, flames, sound, damage and end ticks, the sound's volume
       and pan; the flames (count, delay, spread, lift, size, frames, the ground glow's tilt, mode,
       grey); the embers and the sparks (count, delay, spread, speeds, size, frames or life, their
       sprite, drag and shrinking). Data: the three sequences, the sound, the camera track (1584
       bytes), "mag001.tim".
     - *Fujin:* its tabs (Timing, Flames, Embers, Sparks); a sixteenth family in the + menu, "One
       director per action, flames around its targets (Fire's kind)": Flames (the start), Embers,
       Sparks.
   - **Thunder (3)** (FFNx 4d26eb84): the cycle director (every 5 ticks, not while a bolt of 15 ticks
     or less runs on that target), the bolt at the target's effect point 0xF1: a screen flash quad
     at its first tick, the strike's sprite sequence layers each over its own ticks (one lowered
     copy), a layer on a plane at the target's feet, smoke; the sound at 1, the result at 5, the
     end at 25. Its texture is exe data uploaded as it is: no file.
     - *Shared:* the cycle director and its busy wait, its spawn point (an effect point of the
       target), `heal_action_at`, `tick_at_least`, the draw limit `within`.
     - *Added:*
       - a texture `"tim"` (data, kind `tim`): the setup uploads it as it is, the file loader
         loads nothing (the program's `texture_data`); Fujin's Data tab shows its size;
       - the library's lightning strike (`fx_bolt.h`, Thunder's 0x700DE0 / 0x7011A0): the draws
         `screen_quad` (a colour word, a render-list bucket: a flat semi-transparent quad over the
         whole screen), `point_layer` (sequence, from, lift, size: a frame at the node's spawn point,
         its 4th word the camera offset) and `ground_layer` (sequence, from, tilt, push: on a plane
         at the entity's feet); the actions `spawn_size_word` (tick, base, shift: the spawn point's
         4th word from the entity's size) and `sound_3d_at_spawn`.
     - *Inputs* (`ThunderParams`): the cycle, the busy tick, the effect point, the camera offset,
       the sound, damage and end ticks; each layer's window (from, frames), the strike's size and
       lowering, the ground plane's tilt and push. Data: the eight sequences, the screen quad's
       colour, the sound, the TIM (165920 bytes), the camera track (1424 bytes).
     - *Fujin:* its tabs (Timing, Screen flash, Strike, Ground, Smoke); a seventeenth family in the
       + menu, "One per action, a bolt on its target (Thunder's kind)": Strike (the start), Screen
       flash, Ground, Smoke.
   - **Double (4)** (FFNx 6887b441): the heal ring's director in a short form (Double's root: four
     phases, its packet arenas memory words set in the magic buffer; its setup), one emitter per
     target in turn: a sequencer spawns five runes around the target, one a tick, each with a glow
     on the ground; a rune fades in (motes spiralling in, a column at its tick 3), then shrinks out;
     a column widens, rises, settles and flashes; the last one's signals its emitter: a screen fade
     and the big rune (sprites, two morphing rings), the glows and columns pulse; a flash quad jumps
     on the target's top; the result.
     - *Shared:* the effect-library nodes and their phases, `follow_target`, `spawn`,
       `unblock_director`, `heal`, `done`, `sound_at`, the `sprite` draw (the motes).
     - *Added:*
       - node variables: an effect node's header fields (pos, counter, flags, phase) and its
         `body` (laid out from 0x30, typed: i16, i32, u8, grey, u16, i8), named as the node's own,
         `emitter.`, `child.` (the node a spawning action or the spawn whose `init` this is just
         made) and `name.k`; compiled to tokens (base << 20 | type << 16 | offset);
       - their actions `add`, `set`, `copy`, `flags`, `set_when`, `add_when`, `add_below`,
         `add_var`, `spin_var`, `rand_mask`, `rand_hop`, `index_times`, `tick_times`,
         `circle_place` / `circle_place_var` (a centre, an angle, a radius, a divisor),
         `anchor_xz` / `anchor_top` (the emitter's target anchors), `turned_offset`, `wrap`,
         `spawn_when`, `spawn_unless_target_bits`, `screen_fade_when`; the conditions `at_most`,
         `at_least`, `equals`, `never`, `at_least_var`, `at_least_when`, `equals_when`;
       - a negated parameter `-$key`; a task's `after_phase` actions (after its phase, before its
         draws and spawns); a spawn's `init` actions; a draw's `when` condition; the part tag
         cleared after every task's draws (it was after a plain task's only);
       - the library's runes (`fx_runes.h`, Double's 0x8D5440 / 0x8D5950 / 0x8D57C0 / 0x8D6790):
         the draws `prim_model` / `prim_model_as` (a model at the node, its angles, scale, colour,
         fade), `sprite_turned`, `ground_flipbook_colour` (the ground flipbook in a colour word of
         the node), `screen_tex_quad`; the actions `fade_pulse` (the column's flash), `grey_pulse`
         (the glow's), `morph` (a model's vertices blended between two vertex sets).
     - *Inputs* (`DoubleParams`): the emitter (sound, the next action's tick, the screen fade, the
       target bits that skip the flash); the runes (count, angle step, height, radius, fades,
       shrinking, spin); the columns (tick, fades, widths, rise, peak, settle, the flash's two
       fades and steps, spin, orbit speed); the motes, glows, big rune, sprites, morphing rings and
       flash (ticks, counts, radii, greys, steps, the quad's texture). Data: the three sequences,
       the five models, the two vertex sets, the sound, the camera track (1584 bytes), "mag003.tim".
     - *Fujin:* its tabs (Emitter, Runes, Columns, Motes, Glows, Big rune, Sprites, Morphing rings,
       Flash); an eighteenth family in the + menu, "Around one target at a time, runes (Double's
       kind)": Runes (the start), Columns, Motes, Glows and Big rune (with Columns), Sprites and
       Morphing rings (with Big rune), Flash. Removing a part drops a spawning action naming its
       task with the child actions after it.
   - **Phoenix Down (5)** (FFNx 468bcfea; the revive module, Life's too: one source built twice,
     `mag_revive.h`): the short director again, its setup uploading the texture even when the cast
     repeats and starting no camera; one emitter per action whose phases animate its spawn
     parameters (a disc's radius, a height spread, the sparkles' size ramp, a ring's height) and
     which, while spawning, spawns sparkles rising from the disc, revive sparkles scattered above,
     sparkles orbiting up a ring, sparkles falling and the effect library's glints, each on its
     ticks; the revive once the sparkles' size has faded.
     - *Shared:* the node variables and their actions (Double's), `follow_target`,
       `unblock_director`, `heal`, the `flipbook_end` condition, the `glint` placement and its rate
       schedule, `sound_at`.
     - *Added:*
       - the director's `"upload": "always"` (the program's `per_action ... short upload_always`);
       - the condition `above` (a variable over a value: the emitter's phases on its tick);
       - an every-n-ticks spawn's `if` (the program's `spawn_gate`, a line of its own: Double's
         spawns ignored it, their windows all fell while spawning);
       - the library's revive sparkles (`fx_revive.h`, Phoenix Down's 0x8D4700..0x8D4E60): the
         placements `revive_rising`, `revive_at`, `revive_scatter`, `revive_ring`, `revive_fall`
         (each spawns its own node under the emitter, CRT rand in the original's order), the action
         `revive_ring_step` (the ring sparkle's orbit), the draws `revive_sparkle` (its size a
         variable) and `revive_sparkle_sized`.
     - *Inputs* (`ReviveParams`): the emitter (sound, the size ramp, the grow / spread / fade
       phases' ticks and steps); the rising and revive sparkles (ticks, counts, frames, camera
       offsets, height, steps); the ring (ticks, frames, its radius divisor, spin, rise); the falling
       sparkles (ticks, frames, circle, height, speed); the glints (ticks, four rates, their style).
       Data: the five sequences, the sound, "mag004-034.tim"; no camera track.
     - *Fujin:* its tabs (Emitter, Sparkles, Ring, Falling sparkles, Glints); a nineteenth family
       in the + menu, "Around one target at a time, sparkles rising (Phoenix Down's kind)":
       Sparkles (the start), Ring, Falling sparkles, Glints.
   - **Mega Phoenix (7)** (FFNx 997aee97; the actor/heal library's act family, Mega-Potion's kind):
     Cure's per-action director in the act family's form, one emitter per target of the action in
     turn, each spawning an actor system: the particle actors its actor data defines (flipbooks and
     prim models, placed by the caster and its target), drawn into the module arena; the revive;
     the stage's fade layers up while it plays and down after its last target. No camera track.
     - *Shared:* Cure's director phases and setup (the root of 0x64 bytes, its arenas in the texture
       file), `follow_target`, `unblock_director`, `heal`, `sound_at`, the node variables
       (Double's).
     - *Added:*
       - the director's `"each": "target"` (the program's `per_target`: its task for each target of
         the action, not each action), `"arena_size"` (each packet arena's size: 0xA000 here) and
         `"act"`: the actor pools carved from the arena top at state 2 and cleared (`act_pool`,
         `act_zero`), the stage fade tasks and the wait before the fade out (`act_stage`, either
         fade may be left out), u16 counters cleared before the queues every tick (`act_clear`),
         the parts of the actors' draws (`act_parts`: the system's, each definition's from
         `first_part`);
       - the actor system (FFNx `fx_actors.h` / `fx_actors.cpp`, Mega Phoenix's copy
         0x8CE970..0x8D41E0, on the program's memory words): the actions `actor_setup` and
         `actor_step`, the condition `actor_done`; the stage fades: the actions `stage_clear` and
         `stage_fade` (a level variable by a step to a limit, then done);
       - the exe data kind `actors`: the actor data whole (its header and, from `body`, what its
         tables point at); an own copy is the program's `data_actors` line, its pointers moved to
         the copy (the tables the game left all zero, in the exe's zero-filled data: a zero block
         of its own);
       - `patches`: values written into data before every cast (the program's `patch` lines):
         every field of the actor definitions, at its offset from the header.
     - *Inputs* (`MegaPhoenixParams`): the emitter (sound, the master's release tick, the revive
       tick); the actor system (start tick, length, mode, skip mask); the fades (the wait, steps,
       levels); each of its five definitions (`DefParams`, 76 fields): where its emitter sits and
       faces, when and how many it emits and how they spread, its particles' kind, orientation,
       rotation, depth, end and timer, angles, motion (speed, gravity, damping, velocity,
       acceleration), follow-up and sub-emitters. Data: the actor data, the sound, "mag006.tim".
     - *Fujin:* its tabs (Emitter, Actors, Stage fades, Actor 0, 1, 2, 3, 5); a twentieth family in
       the + menu, "Around one target at a time, an actor system (Mega Phoenix's kind)": Emitter (the
       start: the emitter and its actor system), Stage fades.
   - **Doom (8)** (FFNx d8a49954; the act family, Tonberry's kind with Death's reaper; its parts the
     port's code): the director's phases call up the reaper rising from the ground in the dark, its
     aura's actor system, dust and smoke, then the scythe and the doom clock round the target with
     its strike, a screen tint, the stage wobbling.
     - *Shared:* Cure's per-action director in the act family's form (Mega Phoenix's actor pools and
       counters), `follow_target`.
     - *Added:*
       - `"module"`: a port module whose code runs on the program's memory - its effect, its memory
         (`from`, `size`) and the exe data words pointing into it (the engine's global index, the
         word); a copy (`new_effect`) keeps the module's memory addresses and gets one block of its
         own (the program's `module ... own`: every address in it moved there, the descriptor's
         globals too); the port's parameters are set from the program's of the same keys;
       - the action `call` (a port function by its original address, on the node): the engine's
         emitter and the phase director are their state tables, a phase per state, each calling
         its state function (which steps the phase itself: `"wait": ["never"]`), the director's
         bookkeeping an every-tick call; the parts the port spawns run as its ports (the program's
         own task when one mirrors that original: a task's `code`);
       - the director's `"release_file"` (states 7 and 8: its file's release asked and waited for);
       - FFNx: `act_engine.h` `R()`, `Spawn`, `Callback` (a copy's own memory, its tasks), Doom's
         module memory through them; the host and the recorder build the ports with parameters in
         (the recorder's lab keeps its sprite hooks: a port of a sprite reader is left out).
     - *Inputs* (`DoomParams`): the director (sound, texture wait, phase tick); the reaper (rise,
       height, turn, hold, fade); the aura (start, length, mode); the dust (flipbook, frames, ticks,
       distance, height, speed); the smoke (ticks, scale, tilt, fades); the scythe (tick, offset, the
       clock's model step); the stage wobble (after, step, level, out); the tint (delay). Data: the
       sound, the dust flipbook, the camera track, "mag007.tim".
     - *Fujin:* its tabs (Timing, Reaper, Aura, Dust, Smoke, Scythe, Stage wobble, Screen tint); no
       + menu family (its parts are the port's code, spawned by it).
   - **Ray-Bomb (10)** (FFNx 60896e12; X-ATM092's attack; its tasks the port's code): a muzzle in front of
     the caster charging, dust blown from it, a muzzle flash, the beam to the targets with its sparks,
     smoke, a shockwave ring and debris at the targets, the party thrown up and bounced back.
     - *Added:* the director kind `"port"` (the program's `director port` and `port <setup> <loader>
       <root>`): the port's file loader, setup and root run on the program's memory (`"module"`, its
       block in a copy); the root is the program's director (the module current every tick), the
       tasks it spawns its ports. FFNx: `fx_port.h` `own::` (any port: `R()`, `Fn()` - the program's
       own task or the port of an original -, the ports a program may run), Ray-Bomb's memory and
       spawns through it, its setup and file loader ported.
     - *Inputs* (`RayBombParams`): the sounds, the muzzle, the charge glows, the dust, the muzzle
       flash, the beam, the smoke, the shockwave, the debris, the bounce, the screen flash ramps and
       the end. Data: the two sounds, "mag009.tim".
     - *Fujin:* its tabs (Timing, Charge, Muzzle flash, Beam, Blast, Bounce); no + menu family.
   - **Storm Breath (11)** (FFNx 352bade2; Elvoret's attack; a port director, Ray-Bomb's kind): a breath
     stream from the caster's mouth sweeping its targets in turn, layouts at the mouth, mist and rings blown
     along it, hit sparks on the targets, sparks and debris off the stream.
     - *Inputs* (`StormParams`): the sound and the end, the stream (start, ticks, sweep, its angles), the
       layouts at the mouth, the hit sparks, the stream's sparks and debris, the mist and rings. Data: the
       sound, "mag010.tim".
     - *Fujin:* its tabs (Timing, Stream, Sparks, Mist and rings); no + menu family.
   - **Blade Shot (12)** (FFNx 1f598a55; Mesmerize's attack; a port director, Ray-Bomb's kind): a blade
     thrown from the caster's hand at its target and back, its after-images, the impact's sprites, rings,
     wings, sparks, glints and streaks. Its packet arenas are in its module's memory (moved with a copy).
     - *Inputs* (`BladeParams`): the two sounds, the blade's tilt and spin, the catch sprite's height, the
       after-images, the impact's sparks, glints and streaks. Data: the sounds, "mag011.tim".
     - *Fujin:* its tabs (Blade, Impact); no + menu family.
   - **Dark Mist (13)** (FFNx f65b4c97; Anacondaur's Dark Mist / Poison Mist; a port director, Ray-Bomb's
     kind; effect-library nodes): one emitter per action - a swirl at the caster's mouth, a mist controller
     throwing a cloud, mist puffs and streams toward the target, puffs round it, the target redrawn
     wobbling; the damage.
     - *Inputs* (`MistParams`): the emitter's sound, its mist controller and damage ticks; the controller's
       ticks (puffs, streams, puffs round the target, the overlay, its end). Data: the sound, "mag012.tim".
     - *Fujin:* its tabs (Emitter, Mist); no + menu family.
   - **Death (14)** (FFNx ece8c5b6; the act family, the Boko summons' kind; Doom's description): the reaper
     appears in front of its target, fading in in the dark with its aura's actor system and the stage
     wobbling, strikes - the dark actor system and dark spark bursts - and vanishes.
     - *Inputs* (`DeathParams`): the two sounds, the reaper's fades and animation frames (dark until, the
       strike, the vanish), the aura's and the strike's actor systems (ticks, mode). Data: the sounds, the
       camera track, "mag013-073-344.tim".
     - *Fujin:* its tabs (Reaper, Actor systems); no + menu family.
   - **Draw (15)** (FFNx c493b814; Lefty's attack; the act family, Doom's description): one emitter per
     action - its sounds, an actor system and the drawn magic: twisted ribbons from round the target to the
     caster, their sparks; the damage.
     - *Added:* a task's `"native"` (the program's `native <original>`): its body the port's task function
       (the module's own emitter), its module current.
     - *Inputs* (`DrawParams`): the emitter's three sounds (sound ids), the master's release tick, the actor
       system's ticks and mode, the ribbons' twist and spread. Data: the camera track, "mag014.tim".
     - *Fujin:* its tabs (Emitter, Ribbons); no + menu family.
   - **Recover (16)** (FFNx 3bb57355; command ability; the act family, Doom's description; Revive 61 is
     the same source): one emitter per action - the director's cuts: an actor system and the stage
     darkening, the sound, the action's result.
     - *Inputs* (`RecoverParams`): the director's sound and result cue, the actor system (start, ticks,
       mode), the stage darkening (step, level, hold, out step). Data: the sound, the camera track,
       "mag015.tim".
     - *Fujin:* its tabs (Director, Stage darkening); no + menu family.
   - **Elvoret's entrance (17)** (FFNx 772f80cc; Elvoret's AI's own animation; a port director, Ray-Bomb's
     kind): Elvoret coming down from above, its wings' particles and sounds, a ring burst at its landing.
     - *Added:* a port director's file loader and the texture may be left out (the setup uploads exe data).
     - *Inputs* (`ElvoretParams`): the two sounds, the start height and descent, the ring burst, the end.
       Data: the sounds.
     - *Fujin:* its tab (Entrance); no + menu family.
   - **Elvoret's death (18)** (FFNx 6d733541; Elvoret's AI's own animation; the first of the GF cinematic
     engine's clones): Elvoret's model copy falling apart polygon by polygon - its pieces, dots and particles.
     - *Added:* `"setup_exe": true` on a port director (`port <setup> <loader> <root> exe`): the program calls
       the module's own setup - the cinematic engine's state block is shared, one clone at a time - and
       re-points the root it queued at the program's director; `"shared": true` on the module (a copy keeps
       the same memory). File parameters reach the port (`ProgramFiles` in `gfc_engine.h`: the clone's file
       loader reads them).
     - *Inputs* (`ProgramFiles<18>`): its two script files (MAG017_B.00 / .01; empty: the game's).
     - *Fujin:* its tab (Files); no + menu family.
   - **Raldo Throw (19)** (FFNx 082a049f; Granaldo's Raldo Ball / Raldo Throw; the act family, Doom's description):
     Granaldo takes the Raldo standing at it, morphs it into a ball and throws it at its target - the ball's
     actor system, the stage wobble, debris at each landing - then the ball rolls back with two bounces and
     the Raldo is given back.
     - *Inputs* (`RaldoParams`): the sound and its tick, the ball's radii, the throw (progress, spin, morph,
       lifts, gravity), the rebound (progress back, bounce lift, unmorph), the debris spawners' ticks, the
       ball's actor system (start, mode), the wait before the Raldo turns back. Data: the sound, the camera
       track, "mag018.tim".
     - *Fujin:* its tabs (Raldo, Ball actors); no + menu family. The lab's monsters carry their com id
       (entity +4), which the effect finds its Raldo by.
   - **NORG Pod opening (20)** (FFNx 69e43bd4; the NORG Pod's enemy attack; the act family with Drain's master):
     the stage light ramps up, the pod's shell (the caster's bone 1) is thrown off - the stage wobble, the
     caster's chain transformation, debris sprites and prim-model chunks - the damage; after the last
     action a wait, the light ramps down.
     - *Added:* an act director without actor pools (`act` with only `stage_in` / `stage_out` / `wait`);
       native tasks as its stage tasks; a port's engine task reading its node's function (its state
       table) finds the program's task's `code` (act_engine.h `g_orig_hook`), so it also runs in a copy.
     - *Inputs* (`NorgParams`): the emitter's sound, release and damage ticks, the master's wait, the stage
       light ramps (step, level), the lid's flight (start, ticks, velocity, gravity, spins), the debris
       sprites (frames, colour). Data: the sound, the camera track, "mag019.tim".
     - *Fujin:* its tabs (Emitter, Lid); no + menu family.
   - **Triple (21)** (FFNx 2201fd70; the spell, Double's bigger sibling; a port director, Ray-Bomb's kind):
     one emitter per action - eight runes around the target, two opposite a step, each with its glow,
     motes and a rising column; the last column starts a screen fade and the big rune; a flash quad
     jumps on the target's top; the result.
     - *Inputs* (`TripleParams`): the emitter's sound and release tick, the runes' step, height, spin,
       fades, shrink and column tick, the motes (until, radius). Data: the sound, "mag020.tim".
     - *Fujin:* its tabs (Emitter, Runes); no + menu family (Double's family describes its sibling).
   - **Bio (22)** (FFNx b2602950; the spell; a port director, Ray-Bomb's kind): one emitter per action -
     the stage wobbling, acid pools morphing around the target, bubbles and splashes, a boiling acid
     blob (its palette cycling) bursting into droplets and a flash, mists, the target redrawn wobbling;
     the damage once the blob burst.
     - *Inputs* (`BioParams`): the emitter's sound and its spawns' ticks (bubbles, pools, blob, mists,
       overlay), the blob's cycles and spin. Data: the sound, "mag021.tim".
     - *Fujin:* its tabs (Emitter, Blob); no + menu family.
     - *Lab:* the recorder and host builds list their modules in a response file (more of them than
       a command line holds).
   - **Psycho Blast (23)** (FFNx 8f6af7a5; NORG's enemy attack; the act family, Doom's description): the
     director's actor system and the stage wobble, a psychic orb with its ring in front of the caster
     flying at the target, its burst and debris; the damage once it burst. Its geometry block's word (exe
     data pointing into the module) is moved with the module's memory.
     - *Inputs* (`PsychoParams`): the director's sound and its tick, the stage wobble's ticks, the actor
       system (start, length, mode), the orb (appear tick, speed, how short of the target), the debris
       (counts, colour). Data: the sound, the camera track, "mag022.tim".
     - *Fujin:* its tabs (Director, Orb); no + menu family.
   - **Esuna (24)** (FFNx a52b9400; the spell; the act family with Drain's master, NORG Pod opening's
     description with actor pools): once its children are gone the actor pools and the stage wobble
     in, one emitter per action - its sound, the actor system around its target, the master's
     release, the result; after the last action a wait, the stage wobble out.
     - *Inputs* (`EsunaParams`): the emitter's sound, release and result ticks, the master's wait, the
       actor system (start, length, mode), the stage wobble out (level, step). Data: the sound, the
       camera track, "mag023-066.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Cura (25)** (FFNx ed581f49; the spell; the act family's framework with Double's short root): one
     emitter per action - its sound, a glow with swirl sparks and trail motes, four aura players fading
     in turn, spinning rings, rising sparkles, the light, the target overlay, falling particles; the heal.
     - *Added:* a port module under Double's short root (`"root": "short"` with `"module"` and its
       `"magic_buffer"` arenas).
     - *Inputs* (`CuraParams`): the emitter's sound, particle and heal ticks, the later aura players'
       fade bases, the glow's lift and swirl sparks, the sparkles' and particles' spread. Data: the
       sound, the camera track, "mag024-050.tim".
     - *Fujin:* its tabs (Emitter, Glow); no + menu family.
   - **Clash (26)** (FFNx 737b3cce; X-ATM092's enemy attack; a port director, Ray-Bomb's kind, on an act
     engine port): one emitter per target - bursts of rings and sparks at the caster's bones, two shock
     waves, dust, a screen flash, the target knocked back (thrown up spinning, landing, walking back), the
     result.
     - *Inputs* (`ClashParams`): the emitter's sound and its tick, its start and end, the dust count, the
       bursts' ticks, sparks and radius, the knock-back's gravity. Data: the sound, "mag025.tim".
     - *Fujin:* its tabs (Emitter, Bursts); no + menu family.
   - **Full-life (27)** (FFNx 6e5ffdfe; the spell; the act family with Drain's master, Esuna's
     description): once its children are gone the actor pools and the stage fade in, one emitter per
     action - its sound, the actor system around its target, the master's release, the revive; after
     the last action a wait, the stage fade out.
     - *Inputs* (`FullLifeParams`): the emitter's sound, release and result ticks, the master's wait,
       the actor system (start, length, mode), the stage fade (level, step). Data: the sound, the
       camera track, "mag026.tim".
     - *Fujin:* its tabs (Emitter, Stage fade); no + menu family.
   - **Curaga (28)** (FFNx fb79703c; the spell; the act family with Drain's master, Esuna's description):
     once its children are gone the actor pools and the stage wobble in, one emitter per action - its
     sound, a screen flash, the actor system around its target, the master's release, the heal; after
     the last action a wait, the stage wobble out.
     - *Inputs* (`CuragaParams`): the emitter's sound, flash, release and result ticks, the master's wait,
       the actor system (start, length, mode), the stage wobble (amplitude, step). Data: the sound, the
       camera track, "mag027-051.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Wind Blast (29)** (FFNx 1ad1591d; Thrustaevis' enemy attack; the act family with Drain's master, no
     stage tasks): once its children are gone the actor pools, one emitter per action - its sound, the
     wind's actor system, the master's release, the damage of its targets.
     - *Added:* an act director with actor pools and no stage tasks (`act` without `stage_in` /
       `stage_out` / `wait`).
     - *Inputs* (`WindBlastParams`): the emitter's sound, release and damage ticks, the actor system
       (start, length, mode). Data: the sound, the camera track, "mag028.tim".
     - *Fujin:* its tabs (Emitter, Actor system); no + menu family.
   - **Counter Laser-Eye (30)** (FFNx e068fc2e; Belhelmel's enemy attack; the act family with Drain's
     master, Esuna's description): the actor pools and the light ramp up, one emitter per action - its
     sound, the actor system, a laser beam from the caster's eye to its target with its sparks, the
     damage; after the last action a wait, the light ramp down.
     - *Inputs* (`LaserEyeParams`): the emitter's sound, release and damage ticks, the master's wait, the
       actor system, the beam (appear tick, grow, hold until, shrink), the stage light (level, step).
       Data: the sound, the camera track, "mag029.tim".
     - *Fujin:* its tabs (Emitter, Laser); no + menu family.
   - **Heartbreak (31)** (FFNx e498b9c6; Creeps' enemy attack; the act family with Drain's master, Esuna's
     description): the actor pools and the light ramp up, one emitter per action - its sound, two screen
     flashes, a heart, a ring, an arrow flying to the target and a burst, sparks, the actor system, the
     damage; after the last action a wait, the light ramp down.
     - *Lab:* its matrices read stack words earlier code left (the port models them, g_shadow), among
       them its own memory's addresses: a copy with memory of its own draws some sparks differently (the
       own-copy check is the one it does not pass). The recorder's buffers are at fixed addresses now, so
       such a read is the same every run.
     - *Inputs* (`HeartbreakParams`): the emitter's sound, two flash ticks, release and damage ticks, the
       master's wait, the actor system, the stage light (level, step). Data: the sound, the camera track,
       "mag030.tim".
     - *Fujin:* its tabs (Emitter, Stage light); no + menu family.
   - **Protect (32)** (FFNx cf3cf809; the spell; the act family with Drain's master, NORG Pod opening's
     description): the stage wobble in, one emitter per action - its sound, a screen flash, the shield
     model played on the target, particles thrown out, the result; after the last action a wait, the
     stage wobble out.
     - *Inputs* (`ProtectParams`): the emitter's sound, flash, release and result ticks, the master's
       wait, the particle spawner's ticks (20..24: its count table a tick), the stage wobble (level,
       step). Data: the sound, the camera track, "mag031.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Shell (33)** (FFNx 69f851c6; the spell; the act family with Drain's master, Esuna's description):
     the actor pools and the stage darkening in, one emitter per action - its sound, the shield model on
     the target (its size the actor particles' scale), the actor system, the result; after the last
     action a wait, the darkening out.
     - *Inputs* (`ShellParams`): the emitter's sound, release and result ticks, the master's wait, the
       actor system, the stage darkening (level, step). Data: the sound, the camera track, "mag032.tim".
     - *Fujin:* its tabs (Emitter, Stage darkening); no + menu family.
   - **Pain (34)** (FFNx e5312c05; the spell; the act family with Drain's master, no actor pools nor stage
     tasks): one emitter per action - its sound, two prim-model players on the target, the damage.
     - *Inputs* (`PainParams`): the emitter's sound, release and damage ticks. Data: the sound, the camera
       track, "mag033.tim".
     - *Fujin:* its tab (Emitter); no + menu family.
   - **Life (35)** (FFNx 7c3b5ca4; the spell; the act family's framework with Double's short root, Cura's
     description): one emitter per action - its sound, sparkles rising, reviving, ringing round and
     falling on its target, glints, its phases growing and spreading them; the result.
     - *Inputs* (`LifeParams`): the emitter's sound and result tick, its grow phase (until, scale, radius)
       and spread phase (until, radius, height spread, ring height). Data: the sound, the camera track,
       "mag004-034.tim".
     - *Fujin:* its tab (Emitter); no + menu family.
   - **Confuse (36)** (FFNx 4f772f37; the spell; the act family with Drain's master, Wind Blast's
     description): the actor pools, one emitter per action - its sound, the actor system around its
     target, the target's chain transformation, a camera shake and a screen overlay, the result.
     - *Inputs* (`ConfuseParams`): the emitter's sound, shake, chain, release and damage ticks, the actor
       system. Data: the sound, the camera track, "mag035.tim".
     - *Fujin:* its tabs (Emitter, Actor system); no + menu family.
   - **Drink Magic (37)** (FFNx ca15b370; Ochu's enemy attack; the act family, Draw's description): one
     emitter per action - its sound, an actor system and the drunk magic: streaks and five twisted ribbons
     with their sparks from round the target to the caster, the swelling orb at the caster fading out and
     back in; the damage.
     - *Inputs* (`DrinkParams`): the emitter's sound, release and damage ticks, the actor system, the
       ribbons' ticks, spread and twist, the streaks' ticks and acceleration, the orb's tick, scale, fade,
       hold and spin. Data: the sound, the camera track, "mag036.tim".
     - *Fujin:* its tabs (Emitter, Ribbons, Orb); no + menu family.
   - **Quake (38)** (FFNx 8ab7c8a5; the spell; a port director, Ray-Bomb's kind): the stage ground
     rebuilt as a mesh - the caster's side darkened, the ground cracking, rippling and settling, rocks,
     dust, chips and debris thrown, the targets bounced, the camera shaking; without a stage ground two
     sounds and the shake only; the damage.
     - *Inputs* (`QuakeParams`): the two sounds, the sequence's wait and fades, the ripples' length and
       the most debris, rocks and dust alive, the targets' bounce, the shake's start, the fallback's sound
       and end. Data: the sounds (its texture is exe data, its file loader the engine's nullsub).
     - *Fujin:* its tabs (Ground sequence, Fallback); no + menu family.
     - *Lab:* the recorder has no battle stage, so its checks run the fallback; the ground sequence is
       the same port code on the program's memory, not recorded.
   - **Drain (39)** (FFNx 05e2e937; the spell; the act family, the master Esuna's and the others' copy):
     the actor pools and the stage wobble in, one emitter per action - its sound, two screen flashes, the
     actor system streaming from the target to the caster, the damage; after the last action a wait, the
     stage wobble out.
     - *Inputs* (`DrainParams`): the emitter's sound, flash, release and damage ticks, the master's wait,
       the actor system, the stage wobble's level and steps in and out. Data: the sound, the camera
       track, "mag038-055.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Scan (40)** (FFNx 95aa38f1; the spell; a port director, Ray-Bomb's kind): one emitter per action -
     its sound, the reticle closing on the target with its brackets and ring, the screen dimmed, the scan
     bars, the camera to the target, the viewer (name and scan text, turned and zoomed with the pad) until
     confirmed, the camera back; the result.
     - *Inputs* (`ScanParams`): the sound, the camera's blend steps and projection, the brackets' follow
       ticks and growth, the scan bars' fade step and level. Data: the sound, "mag039-067.tim".
     - *Port:* its camera state is reached through an exe data word (0x15CDDE8) holding a module address:
       the port moves that word's value with `own::R()`; the scanner's spawn (two functions by the
       target's record) goes through `own::Fn()` too.
     - *Fujin:* its tab (Scanner); no + menu family.
   - **Dribble (41)** (FFNx b9506b73; Wendigo's enemy attack; the act family, Draw's description): one
     emitter per action - the grab sound, an actor system and the dribble: the target grabbed, morphed into
     a ball and bounced in the caster's hand, thrown, landing with dust, walking back; the damage.
     - *Inputs* (`DribbleParams`): the grab and landing sounds, the emitter's sound, release and damage
       ticks, the actor system, the ball's grab ticks, morph, throw tick, lift, gravity and unmorph. Data:
       the sounds, the camera track, "mag040.tim".
     - *Fujin:* its tabs (Emitter, Ball); no + menu family.
   - **Shoot (42)** (FFNx 2d463a4f; Wendigo's enemy attack; the act family, Draw's description): one
     emitter per action - the kick sound, the ball's prim models, an actor system and the ball: party slot
     1 grabbed and morphed into a ball, passed between slots 0 and 2 with kick bursts (the exe's pass and
     kick scripts), shot away, landing with dust, walking back; the damage.
     - *Inputs* (`ShootParams`): the kick and landing sounds, the emitter's sound, release and damage
       ticks, the actor system, the ball's grab ticks, morph, passes tick, shot distance, lift, gravity
       and unmorph. Data: the sounds, the camera track, "mag041.tim".
     - *Pools:* listed in the master's queue order (emitters, actors, the ball tasks, the prim models): a
       kick spawned by the ball runs in the same tick only when its pool comes after the ball's.
     - *Lab:* recorded with three party members (slots 0-2) and Wendigo (c0m032) casting it.
     - *Fujin:* its tabs (Emitter, Ball); no + menu family.
   - **Melting Bubble (43)** (FFNx fa3feca6; Grand Mantis' enemy attack; the act family with Drain's
     master, Wind Blast's description): the actor pools, one emitter per action - its sound, the bubbles'
     actor system (their first speed by the caster -> target distance), the damage of its target.
     - *Inputs* (`BubbleParams`): the emitter's sound, release and damage ticks, the actor system, the
       bubbles' reach (the distance's clamp and factor). Data: the sound, the camera track, "mag042.tim".
     - *Fujin:* its tabs (Emitter, Actor system); no + menu family.
   - **Junk (44)** (FFNx 34c2dc9e; Tonberry King's enemy attack; a port director, Ray-Bomb's kind): its
     sound, smoke waves at the caster with a camera shake, the targets bouncing, junk falling round them,
     bouncing and breaking into smoke, the big item above every target (its debris, the damage); the
     battle textures restored at the end.
     - *Inputs* (`JunkParams`): the sound, the shake word and the targets' bounce, the falling items'
       first tick, span and step, the big item's tick, the gravity. Data: the sound, "mag043.tim".
     - *Fujin:* its tab (Controller); no + menu family.
