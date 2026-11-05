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
     - **Port effects** (director `port`) read their data through their parameters too, so a new
       effect made from one plays its own copy:
       - FFNx's `fx_params.h` has the field types `Seq`, `Sound` and `Layout` (a prim-model
         layout: the shared prim player's keyframed models). The port reads each one through
         `fxp::sequence`, `fxp::sound` or `fxp::layout(value, game, capacity)`; a value that is
         not one in the exe image or in a registered data block falls back to the game's.
       - The program host registers every `data` blob it allocates as a data block
         (`fxp::add_data`) and drops them with its program (`Release`).
       - A layout is decoded into a block of the port's of a fixed size. Its exe data entry
         says it (`capacity`, bytes). `fxp::layout` keeps the game's layout when the edited one
         needs more player state (`primlayout.state_size`), and the Data tab refuses to apply
         one that does.
       - A port's flipbook plays a fixed number of frames (its code counts them). Its exe data
         entry says it (`frames`); `fxp::sequence` keeps the game's flipbook when the edited one
         has fewer, and the Data tab does not remove a frame below it.
       - 50 port effects have their layouts as parameters (139 layouts), 137 their flipbooks (373).
       - Checked: each one's own copy draws as the exe, and with its layouts' scale and spin or
         its flipbooks' intensity changed, draws otherwise.
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
   - **Stare (45)** (FFNx ba0fbeac; Vysage's enemy attack; the act family without an actor system, Doom's
     description): one emitter per action - the director's phase: its sound, two eye stares in front of
     the caster's eyes, the target's mark, the stage darkening; the damage at its cue.
     - *Added:* a pool's `"before"` (the program's `pool_before <function> <args>`): a module function
       the master calls before that pool's queue runs, its arguments numbers or `@memory` names (a
       copy's moved). Stare's master builds its view-axis matrix there, between its third and fourth
       queues; the lab's run of Stare records the same without it (no record of its layouts is placed
       along the view axes), so the call is kept for faithfulness, not checked by a recording.
     - *Inputs* (`StareParams`): the director's sound and damage cue, the eyes' offset, the stage
       darkening's level, steps and hold. Data: the sound, the camera track, "mag044.tim".
     - *Fujin:* its tabs (Director, Stage darkening); no + menu family.
   - **Sigh (46)** (FFNx 6fc85b79; Vysage's enemy attack; the act family with Drain's master): the actor
     pools and the stage wobble in, one emitter per action - its sound, the actor system, the sigh (two
     prim models with scrolling textures in front of the caster, the breath's rising puffs), the damage
     of its targets; after the last action a wait, the stage wobble out.
     - *Inputs* (`SighParams`): the emitter's sound, release and damage ticks, the master's wait, the
       actor system, the sigh's show and fade ticks and the breath's first burst, the stage wobble's level
       and steps. Data: the sound, the camera track, "mag045.tim".
     - *Fujin:* its tabs (Emitter, Sigh, Stage wobble); no + menu family.
   - **Curse (47)** (FFNx 983a91c1; Vysage's enemy attack; the act family, Doom's description without
     its reaper): one emitter per action - its load script and the director's phases: the sound; phase 1
     the curse's prim models at Vysage's hands (Lefty and Righty, com ids 0x37 / 0x38) and between them,
     the stage darkening, the damage cue; phase 2 an actor system.
     - *Inputs* (`CurseParams`): the director's sound, phase ticks and damage cue, the middle curse's
       start, phase 2's actor system, the stage darkening's level and steps. Data: the sound, the camera
       track, "mag046.tim".
     - *Lab:* checked with Vysage and both hands in the battle, and in the default cast (no hands: the
       hands' models are not found).
     - *Fujin:* its tabs (Director, Stage darkening); no + menu family.
   - **Magma Breath (48)** (FFNx bae38507; Iguion's enemy attack; the act family with Drain's master,
     Counter Laser-Eye's description): the actor pools and the stage light ramp up, one emitter per action
     - its sound, a red screen flash, the lava stream's actor system, the damage; after the last action a
     wait, the light ramp down.
     - *Inputs* (`MagmaParams`): the emitter's sound, flash, release and damage ticks, the master's wait,
       the actor system, the stage light's level and steps. Data: the sound, the camera track,
       "mag047.tim".
     - *Fujin:* its tabs (Emitter, Stage light); no + menu family.
   - **Resonance (49)** (FFNx 27ad7eec; Iguion's enemy attack; the act family without an actor system,
     Stare's kind): one emitter per action - the director's phase: its sound, the screen warp (the scene
     drawn off-screen, copied back through a waving grid), two prim models at the monsters of slots 3
     and 4, a hit task per target (its reaction, the damage). The warp block's exe word (pointing into
     the module) is moved with the module's memory.
     - *Inputs* (`ResonanceParams`): the director's sound and its tick, the screen warp's start, steps
       and hold, the targets' reaction cues, the prim models' placing tick. Data: the sound, the camera
       track, "mag048.tim".
     - *Lab:* the module registries now hold every effect (the lab's module list and the parameter
       registry kept 64: past them the last modules lost their parameters, FFNx a6c4a957).
     - *Fujin:* its tabs (Director, Screen warp); no + menu family.
   - **Hi-Potion (51)** (FFNx ae7a28ae; the battle items Hi-Potion and Hi-Potion+; a relocated copy of
     Cura's module, Cura's description): one emitter per action - its sound, a glow with swirl sparks and
     trail motes, four aura players fading in turn, spinning rings, rising sparkles, the light, the target
     overlay, falling particles; the heal.
     - *Inputs* (`HiPotionParams`): Cura's - the emitter's sound, particle and heal ticks, the aura
       players' fade bases, the glow's lift and swirl sparks, the sparkles' spread. Data: the sound, the
       camera track, "mag024-050.tim".
     - *Fujin:* its tabs (Emitter, Glow); no + menu family.
   - **X-Potion (52)** (FFNx 400c08d4; the battle item; the act family with Drain's master, Curaga's
     code without its stage wobble): the actor pools, one emitter per action - its sound, a screen flash,
     the actor system, the heal.
     - *Inputs* (`XPotionParams`): the emitter's sound, flash, release and heal ticks, the actor system.
       Data: the sound, the camera track, "mag027-051.tim".
     - *Fujin:* its tabs (Emitter, Actor system); no + menu family.
   - **Mega-Potion (53)** (FFNx 25dd0a50; the battle item; the act family with Drain's master,
     Full-life's code with one emitter per target): the actor pools and the stage fade in, one emitter
     per target - its sound, the actor system on that target, the heal; after the last target a wait,
     the stage fade out. It plays no camera track.
     - *Inputs* (`MegaPotionParams`): the emitter's sound, release and heal ticks, the master's wait, the
       actor system, the stage fade's level and steps. Data: the sound, "mag052.tim".
     - *Lab:* checked on one party member and on three (slots 0-2).
     - *Fujin:* its tabs (Emitter, Stage fade); no + menu family.
   - **Everyone's Grudge (54)** (FFNx ec2d51d6; Tonberry's enemy attack; the act family with Drain's
     master, Esuna's description): the actor pools and the stage wobble in, one emitter per action - its
     sound, the actor system round its target, the damage; after the last action a wait, the stage
     wobble out.
     - *Inputs* (`GrudgeParams`): the emitter's sound, release and damage ticks, the master's wait, the
       actor system, the stage wobble's level and steps. Data: the sound, the camera track, "mag053.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Aqua Breath (55)** (FFNx e80fe206; Chimera's enemy attack; the act family, Resonance's kind with
     Drink Magic's orb): one emitter per action - the director: the stage darkening, the sound; phase 1 the
     water ball at the caster, the stream of drops thrown from it, a splash and a rain of drops per target;
     the damage at its cue.
     - *Port:* the drops' sprites are read by the module's own sequence reader (0x80BB50, a copy of the
       engine's), as the game calls it: the port called the engine's and its recording lacked them.
     - *Inputs* (`AquaParams`): the director's sound and damage cue, the stage darkening's level, steps
       and hold, the water ball's fades and hold, the splash and rain windows. Data: the sound, the
       camera track, "mag054-071.tim".
     - *Fujin:* its tabs (Director, Water ball, Drops); no + menu family.
   - **Absorb (56)** (FFNx 963b802a; the command ability; a relocated copy of Drain's module, Drain's
     description): the actor pools and the stage wobble in, one emitter per action - its sound, two
     screen flashes, the actor system streaming from the target to the caster, the damage; after the
     last action a wait, the stage wobble out.
     - *Inputs* (`AbsorbParams`): Drain's - the emitter's sound, flash, release and damage ticks, the
       master's wait, the actor system, the stage wobble's level and steps. Data: the sound, the camera
       track, "mag038-055.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Treatment (57)** (FFNx ad6e13ac; the command ability; a relocated copy of Esuna's module, Esuna's
     description): the actor pools and the stage wobble in, one emitter per action - its sound, the actor
     system round its target, the result (the heal, the status cure); after the last action a wait, the
     stage wobble out.
     - *Inputs* (`TreatmentParams`): Esuna's - the emitter's sound, release and result ticks, the master's
       wait, the actor system, the stage wobble out. Data: the sound, the camera track, "mag056.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Elixir (58)** (FFNx 0cece0a2; the battle item; Mega-Potion's code with other sizes and timings,
     Mega-Potion's description): the actor pools and the stage fade in, one emitter per target - its
     sound, the actor system on that target, the heal; after the last target a wait, the stage fade out.
     - *Inputs* (`ElixirParams`): Mega-Potion's. Data: the sound,
       "mag057-058.tim".
     - *Fujin:* its tabs (Emitter, Stage fade); no + menu family.
   - **Megalixir (59)** (FFNx 4cadd0ac; the battle item; Mega-Potion's code with other sizes and timings,
     Mega-Potion's description): the actor pools and the stage fade in, one emitter per target - its
     sound, the actor system on that target, the heal; after the last target a wait, the stage fade out.
     - *Inputs* (`MegalixirParams`): Mega-Potion's and the emitter's sound tick. Data: the sound,
       "mag057-058.tim".
     - *Fujin:* its tabs (Emitter, Stage fade); no + menu family.
   - **Raijin's strike (60)** (FFNx 8d06d1aa; Raijin's enemy attack; the act family, Psycho Blast's
     kind): one emitter per action - the director's phase: its sound, two actor systems at the caster's
     bone, the strike (the target turned and pushed back, the strike and its impact, the target sliding
     back), debris off the target, the stage darkening; the damage at its cue.
     - *Port:* the debris sprites are read by the module's own sequence reader (0x7F2050), as the game
       calls it.
     - *Inputs* (`RaijinParams`): the director's sound and damage cue, the actor systems' starts, ticks
       and mode, the strike's push tick and distance and its hit tick, the debris window, the stage
       darkening's start, level, step and hold. Data: the sound, the camera track, "mag059.tim".
     - *Fujin:* its tabs (Director, Strike, Stage darkening); no + menu family.
   - **Revive (61)** (FFNx fa94e654; the command ability; Recover's code at its own addresses with a larger
     actor pool, Recover's description): one emitter per action - the director's cuts: an actor system
     and the stage darkening, the sound, the action's result (the revive).
     - *Inputs* (`RecoverParams`, Revive's own): the director's sound and result cue, the actor system,
       the stage darkening. Data: the sound, the camera track, "mag060.tim".
     - *Fujin:* its tabs (Director, Stage darkening); no + menu family.
   - **Devour (62)** (FFNx 3ba28300; the command ability; the act family with Pain's master): one emitter
     per action - the cast: one of three pictures and the title strip scrolling over the screen, the stage
     and the entities darkened (the devoured target hidden), the music faded, the outcome's sound (the
     exe's table by the result); the master's release, the result.
     - *Added:* `resources.files` (the program's `load_file <memory> <name> [first]`): more files the
       program's file loader loads into memory words of the copy (moved with it), before its texture
       when `"first"` (as Devour's loader does) or after it; each name an exe data entry.
     - *Inputs* (`DevourParams`): the emitter's release, result and outcome sound ticks, the picture's
       start, scroll, fade start and step, the darkening's start, hold and step, the music fade's start,
       step and return. Data: the camera track, "mag061.tim" and its four pictures' names.
     - *Fujin:* its tabs (Emitter, Picture, Darkening); no + menu family.
   - **Helix's beam (63)** (FFNx 747947de; Helix's enemy attack; a port director, Ray-Bomb's kind): the
     master - its sound, layouts at two points of the caster and their midpoint, two curving beams to
     the target then two straight ones fading, the screen flash, a white tile, particles and the impact
     at the target; the damage.
     - *Inputs* (`HelixParams`): the sound, the damage and end ticks, the flash level, the impact's
       offset towards the caster. Data: the sound, "mag062.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Model breaking apart (64)** (FFNx 809e037c; Ultimecia's enemy attack, Griever's tail; a port director,
     Ray-Bomb's kind): the master - its sound, 18 bone scripts moving, turning and hiding the caster's
     bones and throwing layouts and sprites off them, three white flashes, the caster drawn with its pose
     offsets; at its end the caster shown whole and the party drawn again.
     - *Inputs* (`TailParams`): the sound and its tick, the voice release and end ticks, the three
       flashes' ticks. Data: the sound, "mag063.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Great Attractor (65)** (FFNx ecc2193c; Ultimecia's enemy attack; a port director, Ray-Bomb's kind): the
     master's 0x228-tick timeline - the star backdrop, the caster sinking then swinging, layouts, beams and
     rays, the targets and the caster pulled to their centre, the vortex rings with ribbons, sprites and
     particle models, the flashes, the battle camera moved all along; the damage, then everything put back.
     - *Port:* the loop restoring the entities' flags ends at the module's end address (0x2545014): it is
       moved with the module's memory too (a copy otherwise skipped it).
     - *Inputs* (`AttractorParams`): the six sounds, the caster's sinking a tick, the targets moved away,
       the damage tick. Data: the sounds, "mag064.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Griever's death (66)** (FFNx 683105ee; Ultimecia's enemy attack, her transformation; a port
     director, Ray-Bomb's kind): the master's 0x341-tick timeline - its camera script, the caster's chain
     transformations, the damage, the caster melting face by face into flying shards, sparks, dust,
     glows, waves, rings, flares, billboards, the screen flashes and feedback; the camera put back.
     - *Port:* its master-task helper (0x622CD0) takes the task as an argument: it goes through
       `own::Fn()` too (a copy otherwise ran the exe's spark task on the original memory).
     - *Inputs* (`GDeathParams`): the damage, voice release and end ticks, the shards' push, the
       screen flash's ticks. Data: "mag065.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Remedy (67)** (FFNx 63f1dd44; the battle items Remedy and Remedy+; a relocated copy of Esuna's
     module, Esuna's description): the actor pools and the stage wobble in, one emitter per action - its
     sound, the actor system round its target, the result (the status cure); after the last action a
     wait, the stage wobble out.
     - *Inputs* (`RemedyParams`): Esuna's. Data: the sound, the camera track, "mag023-066.tim".
     - *Fujin:* its tabs (Emitter, Stage wobble); no + menu family.
   - **Scan (enemy) (68)** (FFNx bf469dc7; Tri-Point's enemy attack; the spell Scan's library reduced to
     its short sequence; a port director, Ray-Bomb's kind): one emitter per action - its sound, the reticle
     closing on the target with its brackets and ring, the camera circling the target, the spinner, the stat
     board and the scan text until closed, the camera back; the result.
     - *Inputs* (`ScanParams`): the sound, the camera's blend steps and projection, the brackets' follow
       ticks and growth (no scan bars in this copy). Data: the sound, "mag039-067.tim".
     - *Port:* its camera state is reached through an exe data word (0x1591C40) holding a module address:
       the port moves that word's value with `own::R()`.
     - *Fujin:* its tab (Scanner); no + menu family.
   - **Griever (69)** (FFNx dc1bf923; Ultimecia's summon of Griever; a port director on the module's own
     setup, its memory shared - the module's helpers run at their exe addresses on it): its camera track,
     the 127-tick timeline - the intro prim model at the attacker, the attacker drawn by the module, the
     two battle stage models broken face by face into flying shards, the rising sparks, the white fade
     while the attacker sinks, the stage model swap.
     - *Inputs* (`GrieverParams`): the sound and the voice, the voice release and end ticks, the
       shattering's growth and cap, the attacker's sinking, the sparks (ticks, a tick, life). Data: the
       two sounds; no texture file.
     - *Recorder:* it shatters the battle stage's models: recorded with `stage=142` (Ultimecia's stage,
       loaded by the exe's own stage code), its cycle test too.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Shockwave Pulsar (70)** (FFNx 72c1a7e3; Ultimecia's final form's enemy attack; a port director,
     Ray-Bomb's kind): the master's 0x106-tick timeline - the screen flash, the targets rising and lifted
     (their models redrawn spinning and scaled), the layouts at the targets and their centre, the shockwave
     layout, sparks and model shards, the white tile, the battle camera moved; the damage, then the targets'
     positions and flags restored.
     - *Inputs* (`PulsarParams`): the voice and the three sounds, the damage, voice release and end ticks.
       Data: the four sounds, "mag069-259.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Laser Eye (Quistis) (71)** (FFNx d4c4e0d1; Quistis' Blue Magic; Counter Laser-Eye's library
     relocated; the act family with Drain's master, Esuna's description): the actor pools and the light
     ramp up, one emitter per action - the actor system, the caster task (her cast animation bound, the
     sound, two laser beams from her eyes to the target with their sparks), the damage; after the last
     action a wait, the light ramp down.
     - *Inputs* (`LaserEyeQParams`): the emitter's release and damage ticks, the caster task's sound, its
       tick and the lasers' tick, the master's wait, the actor system, the beams (appear tick, grow, hold
       until, shrink), the stage light (level, step). Data: the sound, the camera track, "mag070.tim".
     - *Fujin:* its tabs (Emitter, Caster, Laser); no + menu family.
   - **Aqua Breath (Quistis) (72)** (FFNx 8a32993b; Quistis' Blue Magic; Aqua Breath's library relocated;
     the act family, Resonance's kind with Drink Magic's orb, Aqua Breath's description): one emitter per
     action - the director: the stage darkening and her cast animation (the module's animation set bound to
     her), the sound; phase 1 - the water ball at her bone, the stream of drops, a splash and a rain per
     target; the damage at its cue.
     - *Inputs* (`AquaQParams`): Aqua Breath's, and the director's wait after the cast animation starts.
       Data: the sound, the camera track, "mag054-071.tim".
     - *Fujin:* its tabs (Director, Water ball, Drops); no + menu family.
   - **Mighty Guard (Quistis) (73)** (FFNx dfb83d53; Quistis' Blue Magic; Mighty Guard's library without
     its particle scale; the act family with Drain's master, Esuna's description): the actor pools, the
     stage darkening in and her cast animation, one emitter per action target - its sound, the actor system
     round its target, the result (the statuses); after the last target a wait, the darkening out.
     - *Inputs* (`MightyGuardQParams`): the emitter's sound, its tick, the release and result ticks, the
       master's wait, the actor system, the stage darkening (level, step). Data: the sound, the camera
       track, "mag072-077.tim".
     - *Added:* the act director's `"calls"` (the program's `act_call`): functions its master calls once
       after the stage in task, their arguments numbers, `@caster` (the caster's entity) or `@name` (a
       memory word's address: here `bind_block`, the module's 0x20-byte bind block) - here
       BS_BindEntityModelFromComData 0x5022C0 (the module's animation set onto the caster) and
       QueueChainTransformation 0x505C00 (her chain 1: the cast animation).
     - *Fujin:* its tab (Emitter); no + menu family.
   - **LV?Death (Quistis) (74)** (FFNx 67891849; Quistis' Blue Magic; Death's library relocated; the act
     family, Death's description with `"each": "target"`): one emitter per target - a reaper appears in
     front of it (the first after her cast animation: the module's animation set bound to her, a 0xC-tick
     wait), fading in in the dark with its aura's actor system and the stage wobbling, strikes - the dark
     actor system and dark spark bursts - and vanishes; its target's damage.
     - *Inputs* (`LvDeathQParams`): Death's, and the first reaper's wait. Data: the two sounds, the camera
       track, "mag013-073-344.tim".
     - *Fujin:* its tabs (Reaper, Actor systems); no + menu family.
   - **Hell's Judgement (75)** (FFNx 891f2b7e; Ultimecia's enemy attack; a GF cinematic engine clone,
     Elvoret's death's description kind): the clone run from its two script files - its bones, prims,
     sprites and particles, the radial light wave on a mesh (Eden's draw 61) and the shattering mesh (draw
     66: its polygons flying off).
     - *Inputs* (`ProgramFiles<75>`): its two script files (MAG074_B.00 / .01; empty: the game's).
     - *Lab:* the recorder and the host build mag_eden.cpp in when a lab module borrows Eden's draw
       handlers (`apply_eden_b`).
     - *Fujin:* its tab (Files); no + menu family.
   - **Ultimecia's final form appears (76)** (FFNx e2ec252b; her enemy attack; a port director, Ray-Bomb's
     kind): the intro - the caster hidden high, the screen flash, the victory fanfare, the battle stage model
     swap, the music stream - then the master's 0x29A-tick timeline: the camera script, her chains, shown
     and sinking, the bursts, spins, rises, halo, flashes, battle messages, the screen fade, the hit, the
     ring, debris and the white feedback; the damage, the camera saved.
     - *Inputs* (`FinalFormParams`): the voice and the hit sound, her sinking a tick, the voice release and
       end ticks, the halo (scale, growth), the ring (spin, size). Data: the two sounds, "mag075.tim".
     - *Recorder:* the victory fanfare (BS_R0win_QueueVictoryFanfare 0x501A20) done the next tick, the
       music stream (0x46CBB0) and the battle messages (0x4876F0) stubbed: the recorder runs no anim-seq
       queue, no stream, no message window; the stage model load / swap were stubbed already.
     - *Fujin:* its tab (Master); no + menu family.
   - **Ultimecia's final form death (77)** (FFNx b8035c21; her enemy attack; a GF cinematic engine clone,
     Elvoret's death's description kind): the clone run from its two script files (and mag076_b.02, loaded
     by its VM) - her final form disintegrating polygon by polygon (draw 22), Eden's handlers it borrows,
     the battle states it sets on the slot entities.
     - *Inputs* (`ProgramFiles<77>`): its two script files (MAG076_B.00 / .01; empty: the game's).
     - *Recorder:* every slot entity gets status visual counters (+0x88; updateEntityStatusFlags 0x509D10
       clears the ones a status turns on); the lab build takes mag_eden.cpp for any `apply_eden_*` user.
     - *Fujin:* its tab (Files); no + menu family.
   - **Mighty Guard (78)** (FFNx 6aad8afe; Iron Giant's and Behemoth's enemy attack; the act family with
     Drain's master, Esuna's description, Shell's scaled particles): the actor pools, the stage darkening
     in, one emitter per action target - its sound, the actor system round its target (its particles
     scaled by the target's height), the result (the statuses); after the last target a wait, the
     darkening out.
     - *Inputs* (`MightyGuardParams`): the emitter's sound, its tick, the release and result ticks, the
       master's wait, the actor system, the particle scale (times the target's height, min, max), the stage
       darkening (level, step). Data: the sound, the camera track, "mag072-077.tim".
     - *Fujin:* its tab (Emitter); no + menu family.
   - **Ultimecia's final form dies (79)** (FFNx bfb89256; her enemy attack; the act family, Siren's kind,
     Death's description): one emitter per action - the director's three cuts: the caster's model copied
     and thrown as a ball, debris, flakes and sparks, the light levels, the actor system and three
     prim-model sequences, the party hidden meanwhile; the damage at its cue. After the last action the
     master's own tail: battle/MAG078_B.9M0 loaded and handed to the fanfare player, the music volume, the
     unload waits.
     - *Inputs* (`GrieverDeathParams`): the three sounds, the damage cue frame, the actor system's length.
       Data: the sounds, the camera track, "mag078.tim".
     - *Added:* the act director's `"tail"` (the program's `act_tail`): after the last action the
       module's own master states from its state 6 on, called with the root as its master calls them (each
       moves the root's state +0x29 on itself) - here the file load, the fanfare hand-over, the music, the
       unload waits and its finish.
     - *Port:* its file load calls the port's callback in a copy (it sets the copy's load flag); its two
       sprite draws call the module's own sequence reader 0x7BBFD0.
     - *Own copy:* not equal to the exe from the debris burst on - a stack residue the original reads
       (UNINIT 0x7BC782) holds module addresses (the particle queue, task nodes), a copy's differ;
       Heartbreak's case. The free slot 225 records the exe's.
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultimecia junctions to Griever (80)** (FFNx aed7f172; her enemy attack; the act family, MiniMog's
     kind, Death's description): the caster put above its target, then one emitter per action - the
     director's four cuts: the junction (the target's model copied, caster and target hidden, the actor
     sequences, the junction prim model), the stage wobble, the prim model rising on the caster and its
     orbiting particles, the wobble out, the monsters hidden meanwhile; the damage at its cue.
     - *Inputs* (`JunctionParams`): the two sounds, the caster's lift above its target, the damage cue
       frame. Data: the sounds, the camera track, "mag079.tim".
     - *Added:* the act director's `"states"` (the program's `act_state <phase> <function>`): a master
       phase the module's own state stands in for, called with the root (it moves the root's state on
       itself) - here state 1, which puts the caster 0x6E8 above its target.
     - *Own copy:* not equal to the exe from tick 54 on - the module's MiniMog-family code reads
       uninitialised stack words (a primitive's texture word: the exe's holds a garbage F877 where its
       neighbours hold 0x3800), which pick up other values in a relocated copy; that copy then draws
       fewer sprites and does not end within the recorder's 3000 ticks. The free slot 225 records the
       exe's.
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultimecia's attack (81)** (FFNx 01b180e5; her enemy attack 335; the act family, Magma Breath's kind,
     Death's description): one emitter per action - the director's cuts: the actor system (sprite and model
     actors), the stage wobble, the screen tint, the voice and the sound; the damage at its cue.
     - *Inputs* (`Ultimecia81Params`): the director's sound, its damage cue frame, the actor system's
       length. Data: the sound, the camera track, "mag080.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultimecia's attack (82)** (FFNx a8866967; her enemy attack 337; the act family, the same build as 81
     with Raijin's stage darkening, Death's description): one emitter per action - the director's cuts: the
     actor system (sprite and model actors), the stage darkening, the screen tint, the sound; the damage at
     its cue.
     - *Inputs* (`Ultimecia82Params`): the director's sound, its damage cue frame, the actor system's
       length. Data: the sound, the camera track, "mag081.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultimecia absorbs into time (83)** (FFNx da009e5c; her enemy attack 336; the act family, 81's
     build with Boko's master, Death's description): one emitter per action - the director's cuts: the
     creature (appearing below, sinking, its two animations, rising, fading out), the actor system, the
     target absorbed polygon by polygon (its model pulled apart, spinning, falling, shrinking), the stage
     light, the sound; the damage at its cue.
     - *Inputs* (`Ultimecia83Params`): the director's sound, its damage cue frame, the actor system's
       length. Data: the sound, the camera track, "mag082.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **The End (85)** (FFNx 2992ac11; Selphie's Slot; the act family, MiniMog's kind, Death's
     description): one emitter per action - the cut machinery: the load script (its battle files, the summon
     stream) and the director's six cuts: the stage fade, wobble and darkening, the music fade, the meteors,
     the ground, the prim plays with the monsters' shadows, the petals, the glow and the black bars; the
     sounds, the screen tint, the battle UI off and on; the damage at its cue.
     - *Inputs* (`TheEndParams`): the two sounds, the damage cue frame. Data: the sounds, the camera track,
       "mag084.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Angelo Cannon (86)** (FFNx e12ed2d9; Rinoa's limit break; the act family without actor pools,
     Death's description): one emitter per action - the director block, the module data block, the load
     script and the director: Angelo loaded into Rinoa's launcher (her chain transformations, his steps
     raising dust rings and puffs), the muzzle glow, Angelo fired at the enemies (his dash, its glow, two prim
     plays), the strike at the monsters' centre (a third prim play), his jump back; the damage at the done
     flag.
     - *Inputs* (`CannonParams`): the two sounds (loaded, fired), the done flag's frame. Data: the sounds,
       the camera track, "mag085.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Angelo Strike (87)** (FFNx 7cd17211; Rinoa's limit break; the act family, Death's description):
     one emitter per action - the director block, the module data block, the load script and the director:
     the camera task, Angelo running at the target, digging in under it (a ground capture of the stage),
     lifting it, swinging it round over his head and slamming it down (debris, dust, an impact play),
     jumping back to Rinoa; the damage at the done flag.
     - *Inputs* (`StrikeParams`): the two sounds (run, slam), the done flag's frame. Data: the sounds,
       "mag086.tim" (no engine camera animation: its camera task drives the camera).
     - *Port:* its descriptor names two exe words, the director block's and the camera block's
       (`pointers` 2 and 3): both moved with the copy.
     - *Fujin:* its tab (Director); no + menu family.
   - **Invincible Moon (88)** (FFNx af99083b; Rinoa's limit break; the act family, Death's description):
     one emitter per action - the director block, the module data block and the director: Angelo howling at
     the moon with Rinoa's double, the moon and its glows rising behind the party, a halo, dust rings, a
     screen flash, the moon's prim play and an actor system, the camera script; the party made invincible
     at the done flag.
     - *Inputs* (`MoonParams`): the two sounds (howl, the moon rising), the done flag's frame. Data: the
       sounds, "mag087.tim" (no engine camera animation).
     - *Fujin:* its tab (Director); no + menu family.
   - **Wishing Star (89)** (FFNx 5021725d; Rinoa's limit break; a port director, Ray-Bomb's kind, no
     file loader): the director's 0x10F-tick timeline - Rinoa riding Angelo up into a starry sky, the screen
     shattered and falling, the stars twinkling, Angelo diving through the targets eight times (eight damage
     waves) under a rain of sparkles, the landing, the white fade; the camera all along.
     - *Inputs* (`WishingStarParams`): the three sounds. Data: the sounds (its two TIMs are exe data).
     - *Recorder:* each wave applies `target count / 8` target records (the battle gives the action eight
       per target); the recorder's action has one per target, so no wave hits there (a cycle-test
       exemption from the damage line).
     - *Fujin:* its tab (Director); no + menu family.
   - **Tonberry (90)** (FFNx 416d5252; the GF's Chef's Knife; the act family without actor pools, Death's
     description): one emitter per action - the load script and the director's phases: Tonberry walking up
     (his ring particles and sparks), the knife, the prim-model particles and actors, the entity fades, the
     camera's keyed moves; the damage.
     - *Inputs* (`TonberryParams`): the two sounds. Data: the sounds, "mag089_0.tim" and the two more TIMs
       its loader reads ("mag089_1.tim", "mag089_2.tim").
     - *Added:* an extra file's `"upload": true` (`load_file <word> <name> upload`): the setup queues its TIM
       after the texture's, as Tonberry's does.
     - *Port:* the library's canonical module (its descriptor MOD_090 in act_engine.cpp); its master sets it.
     - *Fujin:* its tab (Director); no + menu family.
   - **Angelo Rush (91)** (FFNx 02b560df; Rinoa's Angelo command; the act family, Death's description):
     one emitter per action - the director's phases: Angelo dashing in (his foot rings and dust puffs, the
     dash play following his bone), the screen flash and the actor system; the damage.
     - *Inputs* (`RushParams`): the dash's sound. Data: the sound, "mag090.tim" (Angelo's texture, shared
       with the Angelo effects) and the engine camera animation.
     - *Port:* the module's own sequence reader (0x761330) called through `callo`, as the game calls it.
     - *Fujin:* its tab (Director); no + menu family.
   - **Angelo Search (92)** (FFNx da0b9a17; Rinoa's Angelo command; the act family without actor pools,
     Death's description): one emitter per action - the director's phase: Angelo walking in and sniffing
     (rings and dust puffs), walking to Rinoa (her chain transformations 1 and 2), the found item's play; the
     found item at the done flag.
     - *Inputs* (`SearchParams`): the three sounds (arrive, walk, found), the done flag's frame. Data: the
       sounds, "mag091.tim" and the engine camera animation.
     - *Port:* its own master (a hand port, 7 queues); the module's own sequence reader (0x7583C0) called
       through `callo`, as the game calls it.
     - *Fujin:* its tab (Director); no + menu family.
   - **Angelo Recover (93)** (FFNx db358603; Rinoa's Angelo command; the act family, Death's description):
     one emitter per action - the director's phase: Angelo jumping in by the target, the actor system, the
     stage light, the heal particles falling onto the target; the heal at the done flag.
     - *Inputs* (`RecoverParams`): the two sounds (jump, heal), the heal sound's and the done flag's frames.
       Data: the sounds, "mag092.tim" and the engine camera animation.
     - *Fujin:* its tab (Director); no + menu family.
   - **Angelo Reverse (94)** (FFNx cd6d4f3d; Rinoa's Angelo command; Angelo Recover's twin, the act family,
     Death's description): one emitter per action - the director's phase: Angelo jumping in by the target,
     the actor system, the stage light, the particles falling onto the target; the revival at the done flag.
     - *Inputs* (`ReverseParams`): the two sounds (jump, revive), the revival sound's and the done flag's
       frames. Data: the sounds, "mag093.tim" and the engine camera animation.
     - *Fujin:* its tab (Director); no + menu family.
   - **Siren (95)** (FFNx f5143077; the GF's Silent Voice; the act engine's own module, Death's description):
     one emitter per action - the load script and the director's 28 states over its cut script: the wave,
     the notes and sparkles, Siren with her harp and particle actors, the water surfaces and orbit sprites,
     the target sparks and particle systems, the camera script; the damage.
     - *Inputs* (`SirenParams`): the four sounds (wave, arrive, sparks, song). Data: the sounds, "mag094.tim"
       (no engine camera animation: the camera script task drives the camera).
     - *Port:* the engine master a_739F40 (Siren's, also Choco Meteor's and Chocobocle's) resets g_reloc like
       the module masters; the sprite draws call the module's own sequence reader 0x7435E0 through `callo`.
     - *Exe quirk (copies):* the splash task's spawner picks surface vertices up to the row count inclusive,
       reading past the vertex table 0x258EC70 into the load-script pool's nodes (their pointers): a copy's
       are its own, so a few far splash sprites (sequences 0x15331D0 / 0x1533328 / 0x15334A0) land elsewhere
       (the description and slot 225 from frame 290, slot 224 from frame 236); nothing else differs.
     - *Fujin:* its tab (Director); no + menu family.
   - **MiniMog (96)** (FFNx 988d5df9; the GF's Moogle Dance; the act family, Death's description): one
     emitter per action - the load script and the director's phase script: MiniMog dancing (his texture
     animation), the prim-model sparkles, the particle actors, the screen and entity fades, the music
     volume; the heal.
     - *Inputs* (`MiniMogParams`): the two sounds (the first cue, MiniMog appearing). Data: the sounds,
       "mag095.tim" (no engine camera animation; 2 exe words: pointers 2 and 3).
     - *Added:* a director's `"native"` (gen_act): the module's own director task runs as the port's code -
       MiniMog's draws a draw-mode packet after its states (every tick, OT bucket +0x4484).
     - *Port:* its master sets its descriptor (MOD_096) and resets g_reloc.
     - *Fujin:* its tab (Director); no + menu family.
   - **ChocoFire (97)** (FFNx b0c9a637; Boko's; the act family on the shared Boko port, Death's description):
     one emitter per action - the load script and the director's phase script: the chocobo running in, its shadow, the prim-model fire plays, the emitter stage; the damage.
     - *Inputs* (`BokoParams`, one set a summon): the prim play's, the chocobo's call, the fire's sounds. Data: the sounds, "mag096-097-098-099.tim"
       (no engine camera animation; 2 exe words: pointers 2 and 3).
     - *Port:* the shared code reads its module's memory through BG(), which moves the module's own addresses
       with g_reloc; the director word through the engine's G word.
     - *Fujin:* its tab (Director); no + menu family.
   - **ChocoFlare (98)** (FFNx b0c9a637; Boko's; the act family on the shared Boko port, Death's description):
     one emitter per action - the load script and the director's phase script: the chocobo, its shadow, the prim-model flare plays, the camera script; the damage.
     - *Inputs* (`BokoParams`, one set a summon): the prim play's, the chocobo's call, the flare's sounds. Data: the sounds, "mag096-097-098-099.tim"
       (no engine camera animation; 2 exe words: pointers 2 and 3).
     - *Port:* the shared code reads its module's memory through BG(), which moves the module's own addresses
       with g_reloc; the director word through the engine's G word.
     - *Fujin:* its tab (Director); no + menu family.
   - **ChocoMeteor (99)** (FFNx b0c9a637; Boko's; the act family on the shared Boko port, Death's description):
     one emitter per action - the load script and the director's phase script: the chocobo, its shadow, the meteor with its trails and sparks, the prim-model plays, the camera script; the damage.
     - *Inputs* (`BokoParams`, one set a summon): the prim play's, the chocobo's call, the meteor's two sounds. Data: the sounds, "mag096-097-098-099.tim"
       (no engine camera animation; 2 exe words: pointers 2 and 3).
     - *Port:* the shared code reads its module's memory through BG(), which moves the module's own addresses
       with g_reloc; the director word through the engine's G word.
     - *Fujin:* its tab (Director); no + menu family.
   - **ChocoBocle (100)** (FFNx b0c9a637; Boko's; the act family on the shared Boko port, Death's description):
     one emitter per action - the load script and the director's phase script: the chocobo and the chicobo, the target's wobble, the prim-model plays, the camera scripts; the damage.
     - *Inputs* (`BokoParams`, one set a summon): the prim play's, the chocobo's call, the summon's two sounds. Data: the sounds, "mag096-097-098-099.tim"
       (no engine camera animation; 2 exe words: pointers 2 and 3).
     - *Port:* the shared code reads its module's memory through BG(), which moves the module's own addresses
       with g_reloc; the director word through the engine's G word.
     - *Fujin:* its tab (Director); no + menu family.
   - **Trauma's grab (101)** (FFNx 3bee79ff; Trauma's enemy attack; a port director, Ray-Bomb's kind): the
     root pulls the target in front of Trauma (its chain transformation), then the grab: the target shrunk,
     held at Trauma and turned, the grab's layout, the screen flash, the sound; the target put back where it
     was. No damage (the attack's result is the engine's).
     - *Inputs* (`GrabParams`): the sound, the screen flash's level. Data: the sound, "mag100.tim".
     - *Fujin:* its tab (Grab); no + menu family.
   - **Thundara (102)** (FFNx 2aef19dc; the spell; a port director, Ray-Bomb's kind): every 15 ticks the
     bolt of the next action on its first target - twenty sparks around the target thrown outwards, a
     full-screen flash, the strike's sprite layers and three prim models (two tilted glows, the column, the
     flash ball), flash sprites around the target, the 3D sound; the damage at the bolt's frame 26.
     - *Inputs* (`ThundaraParams`): the sound, the bolt's damage frame. Data: the sound, "mag101.tim".
     - *Fujin:* its tab (Bolt); no + menu family.
   - **Blizzara (103)** (FFNx 6ef14a2d; the spell; a port director, Ray-Bomb's kind): every 20 ticks the
     ice block of the next action on its first target - four ice pillars, the burst, the block growing out
     of the ground with falling chunks and mist, then breaking from the top into spinning shards, the 3D
     sound; the damage at the block's tick 60.
     - *Inputs* (`BlizzaraParams`): the sound, the ice block's damage tick. Data: the sound, "mag102.tim".
     - *Fujin:* its tab (Ice block); no + menu family.
   - **Blizzaga (104)** (FFNx 4e70fa8a; the spell; a port director, Ray-Bomb's kind): every 50 ticks the
     freeze of the next action on its first target - the target frozen from the bottom up, ribbons and
     spirals swirling round it, an ice block growing then breaking from the bottom into 320 falling, spinning
     shards, a ring, a flash model, mist and flakes, the screen flash, the 3D sound; the damage at tick 68.
     - *Inputs* (`BlizzagaParams`): the sound, the freeze's damage tick. Data: the sound, "mag103.tim".
     - *Port:* its setup also computes the freeze band (the ice block's lowest vertex, its height + 1/16).
     - *Fujin:* its tab (Freeze); no + menu family.
   - **Thundaga (105)** (FFNx c1290fc2; the spell; a port director, Ray-Bomb's kind): every 46 ticks the bolt
     of the next action on its first target - the lightning's prim-model play, the target flashed white, the
     screen flash, at frame 28 the screen shattering (the scene rendered into a texture on fourteen shard
     meshes, thrown and breaking into debris), rings of sparks, flash sprites, the 3D sound; the damage and
     the bolt's end at frame 64.
     - *Inputs* (`ThundagaParams`): the sound, the bolt's damage frame. Data: the sound, "mag104.tim".
     - *Port:* the offscreen render's prims are accessors (a static would keep the game's address in a copy).
     - *Fujin:* its tab (Bolt); no + menu family.
   - **Demi (107)** (FFNx 798394e8; the spell; a port director, Ray-Bomb's kind): every 45 ticks the target
     task of the next action on its first target - motes circling in, two sprite sequences, a screen fade,
     the target hidden and drawn as a silhouette pulled towards its middle, the vortex's prim-model play
     with its orbs and sparks, the 3D sound; the status at tick 86.
     - *Inputs* (`DemiParams`): the sound, the status tick. Data: the sound, "mag106.tim".
     - *Fujin:* its tab (Target); no + menu family.
   - **Biggs and Wedge's first death (110)** (FFNx 61dbab10; their death scripts' effect at the Dollet
     tower; a port director, Ray-Bomb's kind): a storm from above sweeping the targets (Storm Breath's
     stream turned round), its sparks, debris and rings, the targets hit, pushed and blown away (their
     reactions and battle texts), then hidden; the wind's sound. No damage.
     - *Inputs* (`StormParams`): the wind's sound. Data: the sound, "mag010.tim" (Storm Breath's).
     - *Port:* the sound position is an accessor (a static would keep the game's address in a copy).
     - *Recorder:* the slot's battle text 0x487750 is stubbed (no message window); the cycle test casts it
       on two monsters (`CYCLE_MONSTERS`: the sweep needs its second target).
     - *Fujin:* its tab (Storm); no + menu family.
   - **Meteor Barret (112)** (FFNx fd8315ff; Zell's Duel finisher; a port director, Ray-Bomb's kind): one
     director an action on its first target - Zell's run-up (his animation set bound, the camera blob made
     current), the rising column, sparks, smoke and debris, his fist layout, the jump onto the target and the
     impact layouts, screen flashes and tiles, Zell faded and put back, the two sounds; the damage at 114
     (a big target) or 119.
     - *Inputs* (`MeteorParams`): the two sounds (start, hit). Data: the sounds, "mag111.tim".
     - *Port:* its setup also measures the column model (its top and height span).
     - *Fujin:* its tab (Director); no + menu family.
   - **Bad Breath (113)** (FFNx 9ea92c3b; Geezard's enemy attack; a port director, Ray-Bomb's kind): the
     breath from the caster's mouth - puffs towards a swinging aim point and a spray around the caster's
     facing - then one target task a party target: the rising cloud, the target redrawn swayed, the cloud
     layout, the 3D sound; the damage at the target task's tick 27.
     - *Inputs* (`BreathParams`): the sound, the targets' damage tick. Data: the sound, "mag112.tim".
     - *Tests:* the cycle test casts it from Geezard (slot 3) on Squall (`CYCLE_CASTS`; `record` drops its
       default cast for one given).
     - *Fujin:* its tab (Breath); no + menu family.
   - **Quezacotl (116)** (FFNx c98b1cdb; the GF's Thunder Storm; the timeline family; a port director,
     Ray-Bomb's kind): the master and the creature's 355-tick timeline - the model materialising, the
     camera's moves, the summon stream's loads, the lightning bolts, arcs, branches and debris, the screen
     flash, the sounds and streams; the damage at tick 345.
     - *Inputs* (`QuezacotlParams`): the voice, the four sounds (arrive, rise, charge, strike), the damage
       tick. Data: the sounds, "mag115.tim".
     - *Module:* shared (a copy runs on the module's memory): the exe's own helpers the port calls - the
       creature's materialise renderers, the target hide / show, the bolt spawners - read its words.
     - *Port:* its setup, file loader and stream callback (0x6C3580, the loader's completion callback) are
       ported; FX_LAB_MODULE makes the effect lab build it.
     - *Exe quirk:* the ribbons read a joint direction the exe never initialises (a stack local, carried
       by the port): in place in the recorder one quad differs in each of three frames (the cycle test
       leaves them out); the description and the copies match the exe.
     - *Fujin:* its tab (Creature); no + menu family.
   - **Break (117)** (FFNx 15e13b52; the spell; a port director, Ray-Bomb's kind): every 20 ticks the target
     task of the next action on its first target - the stone shell's prim-model play, the target hidden and
     drawn turning to stone (its polygons re-textured through a dither table), the debris falling and the
     sparks, the 3D sound; the status at tick 78.
     - *Inputs* (`BreakParams`): the sound, the status tick. Data: the sound, "mag116.tim".
     - *Fujin:* its tab (Target); no + menu family.
   - **Stop (119)** (FFNx ac41e82d; the spell; a port director, Ray-Bomb's kind): every 20 ticks the
     target task of the next action on its first target - the clock's keyframed prim-model play in front of
     the target, a screen fade, the clock pieces breaking into 514 flying, spinning, fading shards, the 3D
     sound; the status at tick 53.
     - *Inputs* (`StopParams`): the sound, the status tick. Data: the sound, "mag118.tim".
     - *Fujin:* its tab (Target); no + menu family.
   - **Electric Discharge (126)** (FFNx 7710dbed; Cockatrice's enemy attack; a port director, Ray-Bomb's
     kind): the main task - the screen flash, ribbons crawling over the caster's model, lightning arcs from the
     caster to the party members, their sparks and tints, the glow layouts, the 3D sound; the damage and the
     end at tick 52.
     - *Inputs* (`DischargeParams`): the sound, the damage tick. Data: the sound, "mag125.tim".
     - *Tests:* the cycle test casts it from Cockatrice (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Gastric Juice (128)** (FFNx 18aff0d9; Gayla's enemy attack; a port director, Ray-Bomb's kind): the
     target task - the juice sprayed from the caster's mouth in streams, its drips and splashes, the target
     melting (its model redrawn), the sound; the damage at tick 53.
     - *Inputs* (`JuiceParams`): the sound, the damage tick. Data: the sound, "mag127.tim".
     - *Tests:* the cycle test casts it from Gayla (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Target); no + menu family.
   - **Breath (129)** (FFNx 6a64e276; Grendel's enemy attack; a port director, Ray-Bomb's kind): the main
     task - the breath from the caster: its branching lightning mesh, arcs and sprites, the screen flash, one
     target task a target, the sound; the damage at a target task's tick 16.
     - *Inputs* (`BreathParams`): the sound, the damage tick. Data: the sound, "mag128.tim".
     - *Tests:* the cycle test casts it from Grendel (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Eerie Sound Wave (130)** (FFNx 3a251bd5; Malboro's enemy attack; a port director, Ray-Bomb's kind):
     the emitter - the sound waves from the caster's mouth towards the targets, their impact layouts on the
     targets, the sound; the damage at an impact layout's frame 8.
     - *Inputs* (`WaveParams`): the sound, the impacts' damage frame. Data: the sound, "mag129.tim".
     - *Tests:* the cycle test casts it from Malboro (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Emitter); no + menu family.
   - **Bad Breath (Malboro, 131)** (FFNx 3984bf13; Malboro's enemy attack; a port director, Ray-Bomb's kind):
     the emitter - the breath's mesh from the caster's mouth, its sprites, one target task a target tinting
     it, the sound; the damage at a target task's tick 40.
     - *Inputs* (`BreathParams`): the sound, the damage tick. Data: the sound, "mag130-299.tim".
     - *Port:* the fade colour is an accessor (a static would keep the game's address in a copy).
     - *Tests:* the cycle test casts it from Malboro (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Emitter); no + menu family.
   - **Dissolving Acid (132)** (FFNx c4aaea2c; Malboro's enemy attack; a port director, Ray-Bomb's kind): the
     target task - the acid streams from the caster's model to the target, the drops, splashes and puddle
     layouts, the sound; the damage and the end at tick 45.
     - *Inputs* (`AcidParams`): the sound, the damage tick. Data: the sound, "mag131.tim".
     - *Lab:* the recorder and the host stub the port registry's `lookup` (the drops run their nodes'
       functions: the lab patches the originals, the programs' nodes hold the ports' thunks).
     - *Tests:* the cycle test casts it from Malboro (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Target); no + menu family.
   - **Beam Laser (134)** (FFNx a7fcacdc; Elastoid's enemy attack; a port director, Ray-Bomb's kind): the beam
     from the caster to the target, its glows, sparks and hits, the sound; the damage at the beam's tick 26.
     - *Inputs* (`BeamParams`): the sound, the damage tick. Data: the sound, "mag133.tim".
     - *Tests:* the cycle test casts it from Elastoid (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Beam); no + menu family.
   - **Reflect Beam (135)** (FFNx e82b0546; Elastoid's enemy attack; a port director, Ray-Bomb's kind): the
     beam sweeping from the caster, its shots, reflections, bursts, glints and sparks, the sound; the damage
     at a reflection task's tick 25.
     - *Inputs* (`ReflectBeamParams`): the sound, the damage tick. Data: the sound, "mag134.tim".
     - *Tests:* the cycle test casts it from Elastoid (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Sweep); no + menu family.
   - **Oil Shot (136)** (FFNx 2c5102d3; Oilboyle's enemy attack; a port director, Ray-Bomb's kind): the shot
     from the caster's mouth - its oil stream, sprays, falling drops and splats, the sound; the damage at the
     shot's tick 62.
     - *Inputs* (`OilParams`): the sound, the damage tick. Data: the sound, "mag135.tim".
     - *Tests:* the cycle test casts it from Oilboyle (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Oil Blast (137)** (FFNx 89924b5e; Oilboyle's enemy attack; a port director, Ray-Bomb's kind): the blast
     - the oil block on the floor, its chunks and sprays, the sound; the damage at the blast's tick 45.
     - *Inputs* (`BlastParams`): the sound, the damage tick. Data: the sound, "mag136.tim".
     - *Tests:* the cycle test casts it from Oilboyle (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Blast); no + menu family.
   - **Saliva (138)** (FFNx 545cf131; Abyss Worm's enemy attack; a port director, Ray-Bomb's kind): the main
     task - the saliva spat from the caster's mouth: its mesh, strings, sprays and splats, the sound; the
     damage at tick 40.
     - *Inputs* (`SalivaParams`): the sound, the damage tick. Data: the sound, "mag137.tim".
     - *Tests:* the cycle test casts it from Abyss Worm (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Sonic Wave (139)** (FFNx e4437020; Oilboyle's enemy attack; a port director, Ray-Bomb's kind): the
     wave from the caster's bone point to the targets - its layout, the screen warps, one target task a
     target tinting it, the sound; the damage at a target layout's end.
     - *Inputs* (`SonicParams`): the sound. Data: the sound, "mag138.tim".
     - *Port:* its setup copies the module's data block (0x11D4E90, 0x9080 bytes: the wave mesh read from
       the copy) into the module memory; the mesh is an accessor (a static would keep the game's copy).
     - *Tests:* the cycle test casts it from Oilboyle (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Phoenix (140)** (FFNx 37c49e90; the GF's Rebirth Flame; the timeline family; a port director, Ray-Bomb's
     kind): the master and the creature's 255-tick timeline - the fire trail flipbooks and flame meshes,
     white-out tiles, the Phoenix model and its three prim-model stages, heat haze, the camera's moves, the
     summon stream's loads, sparks and embers, the sounds; the damage at tick 245, the voice release.
     - *Inputs* (`PhoenixParams`): the voice, the three sounds (trail, rise, stage), the damage tick. Data:
       the sounds, "mag139.tim".
     - *Port:* its setup, file loader (the spark / ember pools at the magic buffer's end) and stream callback
       (0x6A6360) are ported with raw exe calls; FX_LAB_MODULE makes the effect lab build it.
     - *Fujin:* its tab (Creature); no + menu family.
   - **Renzokuken, 5 hits (141)** (FFNx 718fdfc1; Squall's limit break; a port director, Ray-Bomb's kind): the
     controller - Squall's animation set and sequence bound (the hits are the sequence's), the gunblade's
     trail, the sparks, the five hits' slashes with their flashes and debris, the closing slash, the screen
     flash and his tint, the sound.
     - *Inputs* (`RenzokukenParams`): the sound. Data: the sound, "mag140-158-159-258-331-332.tim".
     - *Recorder:* `poke=ADDR:b,..` writes bytes after the setup: the cycle test pokes the stage durations
       (0x1D98214: n, then n + 1 frame counts) the battle's AnimSeq VM computes (opcode AB), which the
       recorder does not run (`CYCLE_POKES`).
     - *Fujin:* its tab (Controller); no + menu family.
   - **Fira (142)** (FFNx 5370c969; the spell; a port director, Ray-Bomb's kind): one director an action on its
     target - the fireball projectile and its trail, the flame column, the shock ring, the burst, sparks and
     embers, the screen flash, the 3D sound; the damage at the director's tick 14.
     - *Inputs* (`FiraParams`): the sound, the damage tick. Data: the sound, "mag141.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Firaga (143)** (FFNx 23b8de15; the spell; a port director, Ray-Bomb's kind): one director an action on
     its target - the area flames, the flame swirls, the fireball, the burst and sparks, the screen flash, the
     3D sound; the damage at the director's tick 48.
     - *Inputs* (`FiragaParams`): the sound, the damage tick. Data: the sound, "mag142.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Blizzard (144)** (FFNx 3efebe1a; the spell; a port director, Ray-Bomb's kind): one director an action on
     its target - the crystal rising and slamming (the battle camera shaken), the shards, falling ice, mist
     puffs and debris, the shockwave, the 3D sound; the damage at the director's tick 37.
     - *Inputs* (`BlizzardParams`): the sound, the damage tick. Data: the sound, "mag143.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Sleep (145)** (FFNx 51ed0b98; the spell; a port director, Ray-Bomb's kind): one director an action on its
     target - the main trails, the bubbles with their trails, the particles, the Zzz sprites, the 3D sound;
     the status at the director's tick 30.
     - *Inputs* (`SleepParams`): the sound, the status tick. Data: the sound, "mag144.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Tornado (146)** (FFNx 94bf4ba0; the spell; a port director, Ray-Bomb's kind): one director an action -
     the crater's pieces and the stage ground redrawn, the funnel's rings, the sparks, the morph cloud, the
     targets lifted and the debris bursts, the screen flash and shake, the sounds; the damage at tick 82.
     - *Inputs* (`TornadoParams`): the two sounds (wind, a piece landing), the damage tick. Data: the sounds,
       "mag145.tim".
     - *Port:* the capture's packets are built at the call (a static would keep the game's addresses); the
       spawn helper `Add` goes through own::Fn.
     - *Tests:* the cycle test loads a battle stage (`CYCLE_STAGES`: the ground task redraws its ground).
     - *Fujin:* its tab (Director); no + menu family.
   - **Regen (147)** (FFNx 5836825f; the spell; a port director, Ray-Bomb's kind): one director an action on
     its target - the two envelopes at its feet, the eight leaves with their trails, the sound; the status at
     tick 28.
     - *Inputs* (`RegenParams`): the sound, the status tick. Data: the sound, "mag146.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Meltdown (148)** (FFNx 75b9f424; the spell; a port director, Ray-Bomb's kind): one director an action -
     its frame towards the target, the disc, the two acid particle systems, the caster glow and the white fade,
     the melting target (its model drawn by the effect), the sound; the damage at tick 80.
     - *Inputs* (`MeltdownParams`): the sound, the damage tick. Data: the sound, "mag147.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultima (149)** (FFNx 8654cd77; the spell; a port director, Ray-Bomb's kind): one director an action -
     the orbiting sprites, the energy spins, the streaks, the shards, the ring and dome, the dust, the sparks,
     the morphing core, the casting side faded, the screen flashes and fades, the sounds; the damage at tick 166.
     - *Inputs* (`UltimaParams`): the three sounds (voice, start, blast), the damage tick. Data: the sounds,
       "mag148.tim".
     - *Port:* its part spawner `SpawnPart` goes through own::Fn (an own copy runs the port's parts).
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultrasonic Waves (152)** (FFNx 8a3a4b4f; Red Bat's attack; a port controller, Ray-Bomb's kind): the
     waves, the rings flying to the target, the three bursts at the target, the sound; the damage at tick 35.
     - *Inputs* (`UltrasonicParams`): the sound, the damage tick. Data: the sound, "mag151.tim".
     - *Tests:* the cycle test casts it from Red Bat (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Controller); no + menu family.
   - **Sticky Web (153)** (FFNx f3f19dd7; Caterchipillar's attack; a port master, Ray-Bomb's kind): the silk
     thread and the web, the two particle flights, the burst at the target, the sound; the damage at tick 55.
     - *Inputs* (`StickyWebParams`): the sound, the damage tick. Data: the sound, "mag152.tim".
     - *Port:* the spawn helper `AddTask` goes through own::Fn.
     - *Tests:* the cycle test casts it from Caterchipillar (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Master); no + menu family.
   - **Ultra Waves (154)** (FFNx 12e55771; Caterchipillar's attack; a port controller, Ray-Bomb's kind): the
     four ring emitters around the caster, the screen warp (the stage re-rendered into a captured grid), the
     sound; the damage at tick 36.
     - *Inputs* (`UltraWavesParams`): the sound, the damage tick. Data: the sound, "mag153.tim".
     - *Tests:* the cycle test casts it from Caterchipillar (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Controller); no + menu family.
   - **Sand Storm (155)** (FFNx a31bf598; Fastitocalon's attack; a port director, Ray-Bomb's kind): the sand
     funnel (its waving vertices, its path from the caster to the targets), the two dust pools, the wind
     sound; the damage at tick 50.
     - *Inputs* (`SandStormParams`): the wind sound, the damage tick. Data: the sound, "mag154.tim".
     - *Tests:* the cycle test casts it from Fastitocalon (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Renzokuken vs X-ATM092 (159)** (FFNx 5f14c771; Squall's limit break on X-ATM092; a port controller,
     Ray-Bomb's kind): Squall's and the boss's animation sets and sequences bound (the hits are the sequence's),
     the gunblade's trail, the sparks, the hits' slashes with their flashes and debris, the four ring kinds, the
     screen flash and his tint, the sound.
     - *Inputs* (`Renzokuken159Params`): the sound. Data: the sound, "mag140-158-159-258-331-332.tim".
     - *Port:* the ring spawner `AddRingAtHit` goes through own::Fn.
     - *Tests:* the cycle test casts it from Squall on X-ATM092 (slot 3, `CYCLE_CASTS`) with Renzokuken's stage
       durations poked (`CYCLE_POKES`); no damage number (the hits are the sequence's).
     - *Fujin:* its tab (Controller); no + menu family.
   - **Renzokuken (160)** (FFNx 2332af9b; Squall's limit break, the generic version; a port controller, Ray-Bomb's
     kind): Squall's animation set and sequence bound (the hits are the sequence's), the gunblade's trail, the
     sparks, the hits' slashes with their flashes and debris, the closing ring, the screen flash and his tint,
     the sound.
     - *Inputs* (`RenzokukenParams`): the sound. Data: the sound, "mag140-158-159-258-331-332.tim".
     - *Tests:* the cycle test pokes Renzokuken's stage durations (`CYCLE_POKES`); no damage number.
     - *Fujin:* its tab (Controller); no + menu family.
   - **Renzokuken vs Elvoret (161)** (FFNx 53a95473; Squall's limit break on Elvoret / Elnoyle; a port controller,
     Ray-Bomb's kind): Squall's and the boss's animation sets and sequences bound (the hits are the sequence's),
     the gunblade's trail, the sparks, the hits' slashes with their flashes and debris, the stream and the burst,
     the closing ring, the screen flash and his tint, the sound.
     - *Inputs* (`Renzokuken161Params`): the sound. Data: the sound, "mag160.tim".
     - *Tests:* the cycle test casts it from Squall on Elvoret (slot 3, `CYCLE_CASTS`) with Renzokuken's stage
       durations poked (`CYCLE_POKES`); no damage number.
     - *Fujin:* its tab (Controller); no + menu family.
   - **Fated Circle (162)** (FFNx f2ad1f61; Squall's Renzokuken finisher; a port director, Ray-Bomb's kind):
     Squall's animation set and sequence bound, the gunblade's trail, the swipe, dust and shock rings, the glow,
     shards and orbit sparks, the burst, the rain, the morph shell and the dome, the captured stage and the swirl,
     the circle with its pillars, rings and embers, the spark clouds, the screen flash, the sounds; the action
     results at tick 150.
     - *Inputs* (`FatedCircleParams`): the two sounds, the damage tick. Data: the sounds, "mag161.tim".
     - *Port:* the spawn helper `AddMain` goes through own::Fn.
     - *Fujin:* its tab (Director); no + menu family.
   - **Rough Divide (163)** (FFNx d36b7818; Squall's Renzokuken finisher; a port director, Ray-Bomb's kind):
     Squall's animation set and sequence bound (his position moved), the gunblade's trail, the glow, sparkles and
     hit sparks, the burst, shards, chips and debris, the pillar, the blade, the streaks, the flash, ring, shock,
     flare and wave, the screen flash, the sound; the action result at tick 65.
     - *Inputs* (`RoughDivideParams`): the sound, the damage tick. Data: the sound, "mag162.tim".
     - *Port:* the spawn helper `AddMain` goes through own::Fn.
     - *Fujin:* its tab (Director); no + menu family.
   - **Blasting Zone (164)** (FFNx 119aab9c; Squall's Renzokuken finisher; a port director, Ray-Bomb's kind):
     Squall's animation set and sequence bound (the setup turns him to the targets), the flares, orbit sparks,
     swirl and rings, the pulses, shards and ball, the frame model, the domes, the beam, the rocks and debris, the
     starfield, the screen flash, the morph and its sparks, the blade glow, the burst sparks, the waves, the smoke,
     the shake, the sounds (ticks 35 and 164); the action results at tick 307.
     - *Inputs* (`BlastingZoneParams`): the two sounds (blade raised, blast), the damage tick. Data: the
       sounds, "mag163.tim".
     - *Port:* the spawn helper `AddMain` goes through own::Fn.
     - *Fujin:* its tab (Director); no + menu family.
   - **Lion Heart (165)** (FFNx 84405133; Squall's Renzokuken finisher; a port director, Ray-Bomb's kind):
     Squall's animation set and sequence bound (the setup turns him to the targets), the hits on the targets with
     their results (one per hit record), the trails, rocks, flashes, rings and sparks, the final blow, the four
     sounds (ticks 10, 119, 202, ...).
     - *Inputs* (`LionHeartParams`): the four sounds. Data: the sounds, "mag164.tim".
     - *Port:* the spawn helper `AddMain` goes through own::Fn.
     - *Fujin:* its tab (Director); no + menu family.
   - **Sleeping Gas (168)** (FFNx f686ea6a; Grat's attack; a port director, Ray-Bomb's kind): the gas clouds
     waving towards the targets, the target and caster sparkles, the screen flash, the sound; the damage at
     tick 60.
     - *Inputs* (`SleepingGasParams`): the sound, the damage tick. Data: the sound, "mag167.tim".
     - *Tests:* the cycle test casts it from Grat (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Gastric Juice (Grat) (169)** (FFNx fe9aafd1; Grat's attack; a port director, Ray-Bomb's kind): the five
     juice streams with their blobs, mesh, drips and puddle, the splash, the tinted target, the sound; the
     damage at tick 35.
     - *Inputs* (`GastricJuice169Params`): the sound, the damage tick. Data: the sound, "mag168.tim".
     - *Tests:* the cycle test casts it from Grat (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Holy (175)** (FFNx 834e6a7f; the spell; a port director, Ray-Bomb's kind): one director an action - the
     screen shattered into flying triangles (the stage captured), the side faded, the sparkles, orbits and
     motes, the rings and waves, the light pillars, the beam, the disks, the flash, the screen flash, the
     sound; the damage at tick 106.
     - *Inputs* (`HolyParams`): the sound, the damage tick. Data: the sound, "mag174.tim".
     - *Port:* the spawn helper `AddTask` goes through own::Fn.
     - *Fujin:* its tab (Director); no + menu family.
   - **Sand Storm (Adamantoise) (176)** (FFNx 97c8102f; Adamantoise's attack; a port director, Ray-Bomb's kind):
     the two sand funnels walking to the targets, the sand emitters, the targets lifted and landing (their
     results), the sounds (the wind at tick 14, a target landing).
     - *Inputs* (`SandStorm176Params`): the two sounds. Data: the sounds, "mag175.tim".
     - *Port:* the spawn helper `Add` goes through own::Fn; the camera animation is `CAMERA_ANIM` (the file's
       `CAMERA` is the camera matrix).
     - *Tests:* the cycle test casts it from Adamantoise (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Bomb glow (179)** (FFNx 2b330fe5; the Bomb's attacks 82 / 83; a port director, Ray-Bomb's kind): the
     Bomb's glow (its model redrawn with a scrolling additive overlay in a cycling colour), the fuse sparks,
     the sound; the damage at tick 35.
     - *Inputs* (`BombGlowParams`): the sound, the damage tick. Data: the sound, "mag178.tim".
     - *Tests:* the cycle test casts it from the Bomb (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Suicide (180)** (FFNx acedc023; the Bomb's self-destruct; a port director, Ray-Bomb's kind): the fuse
     sparks, the Bomb's glow then gone, the explosion, the rings, the sparks, the smoke, the sound; the damage
     at tick 38.
     - *Inputs* (`SuicideParams`): the sound, the damage tick. Data: the sound, "mag179.tim".
     - *Tests:* the cycle test casts it from the Bomb (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Card (182)** (FFNx ebb0d3e5; the command; a port director, Ray-Bomb's kind): the sparkles, the two rings,
     the shards, the screen flash, the sound; carded (target record +3 bit 2 clear: DirectorB, the recorder's
     case): the target fading, the card spinning out of it, the twelve small cards with their trails; the
     action result (tick 35 / 64).
     - *Inputs* (`CardParams`): both directors' sounds and result ticks. Data: the sounds, "mag181.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Defend (183)** (FFNx db038840; the command; a port director, Ray-Bomb's kind): the two shields in front of
     the caster (the large one shrinking onto him, the small one flickering), the sound; the action result at
     tick 30.
     - *Inputs* (`DefendParams`): the sound, the result tick. Data: the sound, "mag182.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Ultra Waves (Quistis) (184)** (FFNx 9aa8e351; Quistis' Blue Magic, a copy of 154; a port controller,
     Ray-Bomb's kind): Quistis' casting animation, the four ring emitters around her, the screen warp, the
     sound (tick 6); the damage at tick 41.
     - *Inputs* (`UltraWaves184Params`): the sound, the damage tick. Data: the sound, "mag153.tim".
     - *Fujin:* its tab (Controller); no + menu family.
   - **Shiva (185)** (FFNx f99f4d86; the GF's Diamond Dust, the timeline family; a port timeline, Ray-Bomb's kind):
     the camera script, the summon stream's loads, the rings, the ground shatter, the mount, the creature with
     its glows, snow, halo and blizzard, the ice block and the dust, the screen flash, the voice and the sounds
     (ticks 1, 101, 147, 249); the action result at tick 265.
     - *Inputs* (`ShivaParams`): the voice, the four sounds, the damage tick. Data: the sounds, "mag184.tim".
     - *Module:* shared (a copy runs on the module's memory): the exe's own renderers the port calls
       (0x5C26A0, 0x5C3D10, 0x5C7AB0, ...) read the module's words.
     - *Port:* the spawn helper `LinkTask` goes through own::Fn.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Odin (187)** (FFNx f1dcacb5; the GF's Zantetsuken, the timeline family; a port timeline, Ray-Bomb's kind):
     the camera script, the summon stream's loads, the grids, debris and intro, the creature with its blade
     glow, smoke, rings, mist, sparks and slashes, the target slices, the party hidden, the screen flash, the
     voice and the sounds (ticks 1, 111, 168); the action result at tick 287.
     - *Inputs* (`OdinParams`): the voice, the three sounds, the damage tick. Data: the sounds (the texture
       is exe data, the file loader the engine's nullsub).
     - *Module:* shared (a copy runs on the module's memory): the exe's own renderers the port calls (the
       grid's writes the packet cursor itself).
     - *Port:* the spawn helper `LinkTask` goes through own::Fn.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Normal Shot (188)** (FFNx e7faa922; Irvine's Shot limit break; a port root, Ray-Bomb's kind): his
     animation set and chains, the afterimages of his gun, per shot the muzzle flashes, smoke and ground smoke,
     the impact with its particles, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (BattleActionSequence_Tick_Shot 0x50BEE0):
       the cast's sequence mode (+8) 0 the opening, 2 a shot, 1 the closing action.
     - *Inputs* (`NormalShotParams`): the gun sound. Data: the sound, "mag187.tim".
     - *Tests:* the recorder's `recall=T:MODE` calls the setup again like the Shot window: the cycle test
       fires three shots and the closing action (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Wall (189)** (FFNx a46deb2b; the magic, Selphie's Slot; a port main task, Ray-Bomb's kind): the stage
     captured, the 24 shards on an ellipse, the wall rising through its plane (the camera shake), the dust and
     debris, the sound; the action results at tick 65.
     - *Inputs* (`WallParams`): the sound, the result tick. Data: the sound, "mag188.tim".
     - *Port:* the spawn helper `AddTask` goes through own::Fn.
     - *Fujin:* its tab (Main); no + menu family.
   - **Chain Gun (190)** (FFNx 42580b37; GIM47N's attack; a port master, Ray-Bomb's kind): the muzzle flashes,
     the smoke, the twelve shots (hits on the target with their sparks, misses on the ground with their
     dust), the sound; the damage at tick 30.
     - *Inputs* (`ChainGunParams`): the sound, the damage tick. Data: the sound, "mag149.tim".
     - *Port:* the spawn helper `AddTask` goes through own::Fn.
     - *Tests:* the cycle test casts it from GIM47N (slot 3) on Squall (`CYCLE_CASTS`).
     - *Fujin:* its tab (Master); no + menu family.
   - **Doomtrain (191)** (FFNx 20a41e9e; the GF's Runaway Train, the timeline family; a port timeline, Ray-Bomb's
     kind): the camera script, the summon stream's loads, the sky, the rails and rig, the train with its
     smoke, sparks and rain, the debris, the flashes, the voice and the sounds (ticks 4, 160, 294, 336, 417);
     the action result at tick 420.
     - *Inputs* (`DoomtrainParams`): the voice, the five sounds, the damage tick. Data: the sounds (the
       texture is exe data, the file loader the engine's nullsub).
     - *Module:* shared and not relocated: the camera-script interpreter (MAG_066 0x63E9C0) in this file
       keeps its state in the module for Shiva, Odin, Cactuar and the other GFs that queue it.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Scatter Shot (192)** (FFNx 496123e2; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes, smoke, blast and ground smoke, the impacts (or the misses' rings and dust), the action results and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`ScatterShotParams`): the gun sound. Data: the sound, "mag191.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Dark Shot (193)** (FFNx d6a8ca38; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes and smoke, the dark impact with its particles, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`DarkShotParams`): the gun sound. Data: the sound, "mag192.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Flame Shot (194)** (FFNx ca558191; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes and smoke, the flaming bullet's flight and its fire burst, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`FlameShotParams`): the gun sound. Data: the sound, "mag193.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Canister Shot (195)** (FFNx b9ea2908; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes and smoke, the canister's steam, bone smoke and debris, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`CanisterShotParams`): the gun sound. Data: the sound, "mag194.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Quick Shot (196)** (FFNx f1412153; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes, smoke and ground smoke, the impact with its particles, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`QuickShotParams`): the gun sound. Data: the sound, "mag195.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Armor Shot (197)** (FFNx 06c7798b; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes and smoke, the piercing arcs and the impact's burst, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`ArmorShotParams`): the gun sound. Data: the sound, "mag196.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Hyper Shot (198)** (FFNx c291fd85; Irvine's Shot limit break; a port root, Ray-Bomb's kind, as Normal Shot 188):
     his animation set and chains, the afterimages of his gun, per shot the muzzle flashes and smoke, the hyper beam and its blast, the action result and the gun sound; the closing action.
     - *Setup:* run again for each trigger press of the Shot window (the cast's sequence mode: 0 the opening,
       2 a shot, 1 the closing action).
     - *Inputs* (`HyperShotParams`): the gun sound. Data: the sound, "mag197.tim".
     - *Tests:* three shots and the closing action recalled (`CYCLE_RECALLS`).
     - *Fujin:* its tab (Shot); no + menu family.
   - **Cactuar (199)** (FFNx 86fc2aee; the GF's 1000 Needles, the timeline family; a port timeline, Ray-Bomb's
     kind): the camera script, the summon stream's loads, the creature rising out of the ground, the ground
     prims and dust, the needle launcher, the needles and their per-target results, the screen flashes, the
     voice and the sounds (ticks 15, 53).
     - *Inputs* (`CactuarParams`): the voice, the two sounds. Data: the sounds, "mag198.tim".
     - *Port:* the spawn helpers `LinkTask` / `LinkFlash` go through own::Fn.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **No Mercy (200)** (FFNx b7940ef4; Seifer's limit break; a port director, Ray-Bomb's kind): the camera script,
     his animation set and sequences (the setup turns him to the targets), the flames, sparks and embers, the
     targets' sequences, the gunblade's trail, the caster ring, the tip flash and shards, the slashes, the
     spark burst, the frame model and the shock waves, the impact flashes and target bursts, the screen flash
     and fade, the sounds (ticks 6, 35); the action results at tick 141.
     - *Inputs* (`NoMercyParams`): the two sounds, the damage tick. Data: the sounds (the texture is exe data,
       the file loader the engine's nullsub).
     - *Port:* the spawn helper `AddMain` goes through own::Fn.
     - *Fujin:* its tab (Director); no + menu family.
   - **Burning Rave (212)** (FFNx aad96877; Zell's Duel finisher; a port root and director, Ray-Bomb's kind): his
     animation set and placement, the stage captured, the ground and burning layouts, rocks, sparks and debris,
     the targets drawn, thrown and spun, his afterimages, the camera's moves, the screen flash, the sounds
     (ticks 5, 67); the damage at tick 174.
     - *Inputs* (`BurningRaveParams`): the two sounds, the damage tick. Data: the sounds, "mag211.tim".
     - *Port:* the rock / sprite spawners take the task as an argument: those spawns go through own::Fn too.
     - *Fujin:* its tab (Director); no + menu family.
   - **My Final Heaven (215)** (FFNx a99590fb; Zell's Duel finisher; a port root and director, Ray-Bomb's kind): his
     animation set, the layouts as he walks back, runs and jumps, the rings, the debris, the targets turned,
     thrown and spun, the crater, the white flash, the camera's moves, the screen flash, the sounds (ticks 6,
     163); the damage at tick 264.
     - *Inputs* (`MyFinalHeavenParams`): the two sounds, the damage tick. Data: the sounds, "mag214.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Different Beat (216)** (FFNx 6dbad04c; Zell's Duel finisher; a port root and director, Ray-Bomb's kind): his
     animation set and moves, the stage captured, the rings, rocks, sparks and embers, the target's chain moved
     and hit, the two flash envelopes, the camera's moves, the sound; the action result.
     - *Inputs* (`DifferentBeatParams`): the sound. Data: the sound, "mag215.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Water (222)** (FFNx 106434cc; the spell; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag221_b.00 / .01) - its bones, prims, sprites and
     particles, the action results. The program calls the clone's own setup (the engine's shared state block),
     its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<222>`): the two script files (empty: the game's).
     - *Lab:* the recorder and the host build mag_brothers.cpp in for a module borrowing its handlers
       (`apply_brothers`: Water's draw 38), as they do mag_eden.cpp for `apply_eden_*`.
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Meteor (223)** (FFNx 106434cc; the spell; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag222_b.00 / .01) - its bones, prims, sprites and
     particles, the screen captures and strips, the action results. The program calls the clone's own setup
     (the engine's shared state block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<223>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **White Wind (enemy) (226)** (FFNx 0b7e7d1f; Adamantoise's attack; a port root and scene task, Ray-Bomb's
     kind): the healing wind at the caster and across the party, one sparkle layout per target with its
     result, the sound.
     - *Inputs* (`WhiteWind226Params`): the sound. Data: the sound, "mag296.tim".
     - *Tests:* the cycle test casts it from Adamantoise (slot 3) on itself (`CYCLE_CASTS`).
     - *Fujin:* its tab (Scene); no + menu family.
   - **Homing Laser (Quistis) (229)** (FFNx 83496e67; Quistis' Blue Magic; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag228_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<229>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Fire Breath (Quistis) (230)** (FFNx 83496e67; Quistis' Blue Magic; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag229_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<230>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Disease Breath (231)** (FFNx 83496e67; Blood Soul's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag230_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<231>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Breath of Death (232)** (FFNx 83496e67; Blood Soul's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag231_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<232>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Earthquake (233)** (FFNx 83496e67; Armadodo's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag232_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<233>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Fart (234)** (FFNx 83496e67; Bite Bug's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag233_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<234>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Breath (235)** (FFNx 83496e67; Blue Dragon's and the Bomb's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag234_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<235>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Ochu Dance (239)** (FFNx 83496e67; Ochu's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag238_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<239>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Ochu Earthquake (240)** (FFNx 83496e67; Ochu's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag239_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<240>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Sand Shake (256)** (FFNx e7e1fde4; Abyss Worm's attack; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag255_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<256>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Mad Cow Special (258)** (FFNx e7e1fde4; Sacred and Minotaur's combo; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag257_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<258>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Desperado (261)** (FFNx e7e1fde4; Laguna's limit break; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag260_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<261>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Blood Pain (262)** (FFNx e7e1fde4; Kiros' limit break; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag261_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<262>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Massive Anchor (263)** (FFNx e7e1fde4; Ward's limit break; a cinematic clone, Elvoret's death's kind): the GF cinematic
     engine's clone run from its two script files (mag262_b.00 / .01) - its bones, prims, sprites
     and particles, the action results. The program calls the clone's own setup (the engine's shared state
     block), its root re-pointed at the port's tick; the file loader ProgramFiles'.
     - *Inputs* (`ProgramFiles<263>`): the two script files (empty: the game's).
     - *Tests:* an edited .00 copy read by the port's file loader and the program's alike.
   - **Renzokuken (6 hits) (259)** (FFNx 1b50296e; Squall's limit break; a port controller, Ray-Bomb's kind):
     Squall's animation set and sequence bound (the hits are the sequence's), the gunblade's trail, the
     sparks, the hits' slashes with their flashes and debris, the closing flash, the screen flash and his
     tint, the sound.
     - *Inputs* (`Renzokuken259Params`): the sound. Data: the sound, "mag140-158-159-258-331-332.tim".
     - *Tests:* the cycle test pokes six stage durations (`CYCLE_POKES`); no damage number.
     - *Fujin:* its tab (Controller); no + menu family.
   - **Shockwave Pulsar (Quistis) (260)** (FFNx f93a385d; Quistis' Blue Magic; a port root and master, Ray-Bomb's
     kind): her animation set and chain, the effect camera, the targets lifted and risen, the rings, sparks and
     shards, the screen flashes and fade, the sounds (ticks 0, 80, 170); the action results at tick 252.
     - *Inputs* (`Pulsar260Params`): the three sounds, the damage tick. Data: the sounds, "mag069-259.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **LV Up (271)** (FFNx 2bc3601e; the command; a port root, Ray-Bomb's kind): the level-up layout on the target (its
     morphing model, the target measured), the sound; the action result when it ends.
     - *Inputs* (`LvUpParams`): the sound. Data: the sound, "mag270.tim".
     - *Fujin:* its tab (Root); no + menu family.
   - **LV Down (272)** (FFNx 2bc3601e; the command; a port root, Ray-Bomb's kind): the level-down layout on the target (its
     morphing model, the target measured), the sound; the action result when it ends.
     - *Inputs* (`LvDownParams`): the sound. Data: the sound, "mag271.tim".
     - *Fujin:* its tab (Root); no + menu family.
   - **Mad Rush (273)** (FFNx 4beaed47; the command; a port root, Ray-Bomb's kind): one layout per target (its morphing
     model at its bone), the dust rising, the sound; each target's action result when its layout ends.
     - *Inputs* (`MadRushParams`): the sound. Data: the sound, "mag272.tim".
     - *Fujin:* its tab (Root); no + menu family.
   - **Duel (274)** (FFNx 94cba3d7; Zell's limit break, its six regular moves; a port root, Ray-Bomb's kind): the
     root and the move task, his animation set and chains, the afterimages, the move's layouts, sparks, hit
     flashes and rocks, the Duel pause, the sounds, the action results; the end.
     - *Setup:* run again for every Duel action (BattleActionSequence_Tick_Duel 0x50BDC0): the cast's
       sequence mode (+8) 0 the cast, 2..7 a move (posted to the root node), 8 the end.
     - *Inputs* (`DuelParams`): the six moves' sounds. Data: the sounds, "mag273.tim".
     - *Tests:* the cycle test casts with Zell's model (`CYCLE_MODELS`: Punch Rush reads his bones) and
       recalls the six moves and the end (`CYCLE_RECALLS`).
     - *Fujin:* its tabs (Punch Rush, Booya, Heel Drop, Mach Kick, Dolphin Blow, Meteor Strike); no + menu family.
   - **Electrocute (275)** (FFNx fa882258; Quistis' Blue Magic, Electric Discharge adapted; a port root, Ray-Bomb's
     kind): lightning crawlers over her model, free arcs from her centre, arcs from her bones to the targets with
     their sparks (a hit target tinted), the glow layouts, the screen flash, the sound; the action result.
     - *Inputs* (`ElectrocuteParams`): the sound. Data: the sound, "mag125.tim".
     - *Fujin:* its tab (Main); no + menu family.
   - **X-ATM092 death (276)** (FFNx 580808fe; its AI's death section; a port root, Ray-Bomb's kind): the machine
     shaken by sparks and smoke, arcs between its parts, five bursts of its bones into flying debris, the white
     screen, the sounds; no damage.
     - *Inputs* (`XAtmDeathParams`): the start sound, the voice slot's sound. Data: the sounds, "mag275.tim".
     - *Tests:* cast by X-ATM092 (c0m092) on the party (`CYCLE_CASTS`).
     - *Fujin:* its tab (Director); no + menu family.
   - **Funguar laser (277)** (FFNx 13575b41; Funguar's enemy attack, a Beam Laser variant; a port root, Ray-Bomb's
     kind): from a vertex of the caster's model to each target, the muzzle and aim layouts, the beam, the hit
     layouts, glows and sparks, the impact layout, the sound; the action results.
     - *Inputs* (`FunguarLaserParams`): the beam's sound. Data: the sound, "mag276-301.tim".
     - *Tests:* cast by Funguar (c0m058) on the party (`CYCLE_CASTS`).
     - *Fujin:* its tab (Beam); no + menu family.
   - **Carbuncle (278)** (FFNx 4acc68b7; the GF's Ruby Light, the timeline family; a port timeline, Ray-Bomb's kind):
     the creature, the ruby dome and its floor mirror, the two keyframed stages, the sparkles and shards, one ruby
     per target (orbit stones, rings, the reflect wall), the camera orbit, the party hidden and the enemies
     lifted, the voice and the sounds (ticks 1, 0x56, 0x91, 0xD7); each target's action result at its ruby's
     tick 0x32.
     - *Inputs* (`CarbuncleParams`): the voice, the four sounds, the damage tick. Data: the sounds, "mag277.tim".
     - *Module:* shared (a copy runs on the module's memory): the exe helpers the port calls by their original
       addresses (the prim callback 0x681FD0, DamageTarget 0x683920, ...) read the module's words.
     - *Fujin:* its tab (Creature); no + menu family.
   - **Full-cure (280)** (FFNx 5ad8b9c2; the magic, Selphie's Slot; a port root, Ray-Bomb's kind): the screen flash
     ramp, every 20 ticks the next target's layout at its effect point with the sound, the sparkles; each
     target's action result.
     - *Inputs* (`FullCureParams`): the sound. Data: the sound, "mag279.tim".
     - *Fujin:* its tab (Control); no + menu family.
   - **Shotgun (281)** (FFNx 0b7bc4e4; the Esthar Soldiers' enemy attack; a port root, Ray-Bomb's kind): the muzzle
     layout at the caster's gun and its sparks, the hits on random bones of the target with their layouts and
     sparks, the sound; the action result.
     - *Inputs* (`ShotgunParams`): the shot's sound. Data: the sound, "mag280.tim".
     - *Tests:* cast by an Esthar Soldier (c0m078) on the party (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Rapture (288)** (FFNx 3044eac1; the magic, Selphie's Slot; a port root, Ray-Bomb's kind): every 10 ticks the
     next target - its feathers, wing layouts and sparkles, the target rising away (or bouncing), the sound; the
     coloured screen flash; each target's action result.
     - *Inputs* (`RaptureParams`): the sound. Data: the sound, "mag287.tim".
     - *Fujin:* its tab (Target); no + menu family.
   - **Brrawghh (289)** (FFNx 6c3b7070; Gerogero's and Gunblade's enemy attack; a port root, Ray-Bomb's kind): the
     spit tubes from the caster's mouth to the target, the spit, drip and splat sprites, the splash layouts, the
     layout at the target, the sound; the action result.
     - *Inputs* (`BrrawghhParams`): the sound. Data: the sound, "mag288.tim".
     - *Tests:* cast by Gerogero (c0m034) on the party (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Pandemona (291)** (FFNx b68a15d2; the GF's Tornado Zone, the timeline family; a port timeline, Ray-Bomb's
     kind): the tornado layers, prim models and particles, the creature, the targets sucked up, spun, carried
     round and dropped, the camera, the streamed loads, the voice and the sounds; each target's action result
     when it lands.
     - *Inputs* (`PandemonaParams`): the voice, the five sounds. Data: the sounds (its textures are exe data).
     - *Module:* shared (a copy runs on the module's memory): the exe helpers the port calls by their original
       addresses read the module's words.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **White Wind (Quistis) (297)** (FFNx 4b1a2edd; Quistis' Blue Magic, a copy of the enemy's 226 that binds her
     cast animation; a port root, Ray-Bomb's kind): the healing wind at the caster and across the party, one
     sparkle layout per target with its action result, the sound.
     - *Inputs* (`WhiteWind297Params`): the sound. Data: the sound, "mag296.tim".
     - *Tests:* cast on two targets (`CYCLE_MONSTERS`: one records too little for the cycle test).
     - *Fujin:* its tab (Scene); no + menu family.
   - **Micro Missiles (Quistis) (299)** (FFNx 92980f0e; Quistis' Blue Magic; a port root, Ray-Bomb's kind): her cast
     animation, six missiles fanned from her to random bones of the target (two miss) with their trails, hits,
     flashes and sparks, the sound; the action result.
     - *Inputs* (`MicroMissilesParams`): the launch sound. Data: the sound, "mag283-298.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Bad Breath (Quistis) (300)** (FFNx 72ffd29d; Quistis' Blue Magic; a port root, Ray-Bomb's kind): her cast
     animation, the breath meshes from her mouth (following her animation) swept over the enemies, the yellow
     screen fade, the smoke, one hit task a target, the sound; the action results.
     - *Inputs* (`BadBreath300Params`): the breath's sound. Data: the sound, "mag130-299.tim".
     - *Fujin:* its tab (Breath); no + menu family.
   - **Boomerang Sword (304)** (FFNx 4c826715; the Esthar Soldiers' enemy attack; a port root, Ray-Bomb's kind): the
     sword thrown from the caster's hand along the targets and back, spinning, with its trail, a hit layout and
     sparks at each target it passes, the sound; each target's action result.
     - *Inputs* (`BoomerangSwordParams`): the throw's sound. Data: the sound, "mag303.tim".
     - *Tests:* cast by an Esthar Soldier (c0m079) on the party (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Gatling Gun (Quistis) (305)** (FFNx 87552010; Quistis' Blue Magic, Chain Gun adapted; a port root, Ray-Bomb's
     kind): her cast animation, the muzzle flashes, the grey smoke, five misses on the line to the target and
     seven hits on it (with their dust and sparks), the screen flash, the sound; the damage at tick 0x1E.
     - *Inputs* (`GatlingGunParams`): the sound, the damage tick. Data: the sound, "mag149.tim".
     - *Fujin:* its tab (Master); no + menu family.
   - **Degenerator (Quistis) (306)** (FFNx 431a7a57; Quistis' Blue Magic; a port root, Ray-Bomb's kind): a black
     vortex swallows the target - the core, pulses, flicker, screen and target rings, the fades, the target
     pulled in and swallowed, the debris, the texture restore, the sound; the action result.
     - *Inputs* (`DegeneratorParams`): the sound. Data: the sound, "mag173.tim".
     - *Fujin:* its tab (Controller); no + menu family.
   - **Ray-Bomb (Quistis) (307)** (FFNx 1930289e; Quistis' Blue Magic, Ray-Bomb adapted; a port root, Ray-Bomb's
     kind): her cast animation, the muzzle at her hand charging, the dust and the flash, the beam to the targets
     with its sparks, the shockwave rings, puffs and debris, the party thrown up, the texture restore, the
     sounds; the action results.
     - *Inputs* (`RayBomb307Params`): the muzzle and blast sounds. Data: the sounds, "mag009.tim".
     - *Fujin:* its tab (Director); no + menu family.
   - **Hero (309)** (FFNx 18d8e283; the battle items Hero-trial / Hero; a port root, Ray-Bomb's kind): the orbit
     layouts spiralling in, the main layout and the shards at the target, the sound; the action result.
     - *Inputs* (`HeroParams`): the sound. Data: the sound, "mag308.tim".
     - *Fujin:* its tab (Play); no + menu family.
   - **Holy War (310)** (FFNx 67967bb8; the battle items Holy War-trial / Holy War, Hero's twin for every target; a
     port root, Ray-Bomb's kind): one target every 5 ticks - the orbit layouts spiralling in, the main layout
     and the shards at it, the sound; its action result.
     - *Inputs* (`HolyWarParams`): the sound. Data: the sound, "mag308.tim".
     - *Fujin:* its tab (Play); no + menu family.
   - **Gravija (311)** (FFNx cf11742f; Diablos' enemy attack; a port root, Ray-Bomb's kind): the grey screen flash, the
     layout at the targets' average point, the screen warp around every target, the particles, the sound; the
     action results.
     - *Inputs* (`GravijaParams`): the sound. Data: the sound, "mag213-310.tim".
     - *Tests:* cast by Diablos (c0m066) on the party (`CYCLE_CASTS`).
     - *Fujin:* its tab (Main); no + menu family.
   - **Fake President death (315)** (FFNx 883d74d1; its AI's death section; a port root, Ray-Bomb's kind): the Fake
     President melting into a puddle (drops, bubbles, rings, sparks, splashes) and Gerogero (the next entity
     slot) rising out of it, the tints, the voice and the sounds; the action result.
     - *Inputs* (`FakePresidentDeathParams`): the voice, the start and hit sounds. Data: the sounds, "mag314.tim".
     - *Tests:* cast by the Fake President (c0m075) with Gerogero (c0m034) in the next slot (`CYCLE_CASTS`,
       `CYCLE_SLOTS`: its rise reads that entity).
     - *Fujin:* its tab (Master); no + menu family.
   - **Acid (Quistis) (317)** (FFNx 316f2d95; Quistis' Blue Magic, Gastric Juice adapted; a port root, Ray-Bomb's
     kind): her cast animation, the acid streams and spray from her to the target, the drips and splashes, the
     target melting, the sound; the action result.
     - *Inputs* (`AcidParams`): the sound. Data: the sound, "mag127.tim".
     - *Fujin:* its tab (Target); no + menu family.
   - **Diablos (325)** (FFNx eec33c9f; the GF's Dark Messenger, the timeline family; a port timeline, Ray-Bomb's kind):
     the two battle models, the prim-model players and particles (bolts, puffs, rising and burst layouts), the
     targets squashed, the camera, the streamed loads, the screen flash, the voice and the sounds (ticks 0, 0x5B,
     0xEE, 0x14D, 0x192, 0x1C8); the action results at tick 499.
     - *Inputs* (`DiablosParams`): the voice, the six sounds, the damage tick. Data: the sounds, "mag324.tim".
     - *Module:* shared (a copy runs on the module's memory): the exe helpers the port calls by their original
       addresses read the module's words.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Odin reverse (326)** (FFNx 89201bd1; Seifer cuts Odin in two, the timeline family, a re-linked copy of Odin's;
     a port timeline, Ray-Bomb's kind): the camera script, the summon stream's loads, the grids, debris and intro,
     the creature with its blade, smoke, rings, mist and sparks, Odin cut in two with the blood bursts, the ghost
     and its sword, the walls, the fading models and tint, the screen flash, the voice and the sounds (ticks 1,
     111, 171, 252); the action result at tick 408.
     - *Inputs* (`OdinReverseParams`): the voice, the four sounds, the damage tick. Data: the sounds (its
       texture is exe data).
     - *Module:* shared (a copy runs on the module's memory), like Odin's.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Gilgamesh (327)** (FFNx 73f10360; the GF's Zantetsuken, the timeline family, one module for 327-330; a port
     timeline, Ray-Bomb's kind): the camera script, the summon stream's loads, the fade tile, rings, flares,
     risers, the swords and Gilgamesh, sparks, puffs, spinners, dots and rising rings, the horse, the final pose,
     the trail, the sword attack (the targets sliced), the screen flash, the voice and the sounds (ticks 1, 121,
     181); the action results.
     - *Inputs* (`GilgameshParams`): the three sounds. Data: the sounds, "mag326-329.tim". (The voice and the
       attack sound are the variant's table entries.)
     - *Module:* shared (a copy runs on the module's memory): the exe helpers the port calls by their original
       addresses read the module's words.
     - *Fujin:* its tab (Timeline); no + menu family.
   - **Renzokuken (7 hits) (332)** (FFNx 84f3a5e5; Squall's limit break; a port controller, Ray-Bomb's kind):
     Squall's animation set and sequence bound (the hits are the sequence's), the gunblade's trail, the
     sparks, the hits' slashes with their flashes and debris, the two closing rings, the screen flash and his
     tint, the sound.
     - *Inputs* (`Renzokuken332Params`): the sound. Data: the sound, "mag140-158-159-258-331-332.tim".
     - *Tests:* the cycle test pokes seven stage durations (`CYCLE_POKES`); no damage number.
     - *Fujin:* its tab (Controller); no + menu family.
   - **Renzokuken (8 hits) (333)** (FFNx 602b0593; Squall's limit break; a port controller, Ray-Bomb's kind):
     Squall's animation set and sequence bound (the hits are the sequence's), the gunblade's trail, the
     sparks, the hits' slashes with their flashes and debris, the two closing rings, the screen flash and his
     tint, the sound.
     - *Inputs* (`Renzokuken333Params`): the sound. Data: the sound, "mag140-158-159-258-331-332.tim".
     - *Tests:* the cycle test pokes eight stage durations (`CYCLE_POKES`); no damage number.
     - *Fujin:* its tab (Controller); no + menu family.
   - **Moomba (338)** (FFNx 162c7380; the GF's Friendship, the timeline family; a port timeline, Ray-Bomb's kind): the
     screen flash, Moomba, the ring prim model, prim-model tasks and sparks at the target's and Moomba's
     vertices, the bursts with debris, the sprite sparks, the stream, the voice and the sound; the action result.
     - *Inputs* (`MoombaParams`): the voice, the sound. Data: the sounds (its textures are exe data).
     - *Module:* shared (a copy runs on the module's memory): the exe helpers the port calls by their original
       addresses read the module's words.
     - *Fujin:* its tab (Creature); no + menu family.
