# Battle camera preview

Ifrit's Camera tab and SolomonRing's character camera preview share a battle-context
player. Choose a set/animation and click Preview, then scrub the frame slider or Play.
The player keeps the final camera pose visible after playback ends.
An empty camera keeps the configured starting view and still displays the encounter.

- **Game camera** uses the DAT shot, its projection/lens and roll, inside a 4:3 viewport.
- **Free camera** lets you orbit, pan and zoom to inspect the surrounding scene.
- Expand **Battle setup** with its arrow to reveal **Open scene.out**, the encounter
  list and placement controls. Folding the section hides its contents without disabling
  them. The preview gets at least half the Camera tab by default; the splitter is movable.
- **Open scene.out** reads the encounter list without modifying it. Choose an encounter
  by its zero-based ID, stage and monster names, then select the enemy slot. Names come
  from the edited/current DAT or nearby monster DATs, with the catalog as a fallback.
  Mod-added monsters therefore keep their own names. For a monster
  DAT, only encounters containing that monster are offered; duplicate instances have
  separate slot choices. A character DAT can preview any nonempty encounter.
- In encounter mode, enemy XYZ coordinates come directly from the selected record.
  The loaded monster occupies its chosen slot. **Party size** and **Player slot** choose
  the player's position from the engine's normal battle formation, defaulting to three
  members and slot 0. The same controls place the player facing a loaded monster.
- Enemy DATs are searched beside scene.out first, then beside the loaded
  model. Available enemies are displayed with their extracted textures; missing
  assets are reported. Only actors are drawn: no battle stage, ground grid or axis gizmo.
  Auxiliary imports never save files.
  The loaded model keeps its normal textures and weapon. Scene files opened in another
  tool are shared through the file bank. Closing scene.out restores manual placement.
- Expand **Battle setup** to choose whether the loaded model is the caster or target,
  set their battle slot IDs and place the opponent in world units (Y points down) in
  manual mode. Encounter mode disables manual coordinates and points the slots at the loaded
  model and its opponent; they stay editable to pick any placed slot (another enemy, a party
  member). Changing the loaded model keeps the selected encounter while it still matches.
- A host tool can supply the other actors: imported models by file name (encounter enemies,
  the default player), a body and weapon per party slot, and the opponent's weapon. Every
  party slot of the formation is then placed, and party members are drawn with their weapon
  (a reduced weapon such as Zell's gloves is posed by the body's bones).
- **Load opponent** imports another monster/character DAT read-only and displays its
  textured posed mesh. In a monster encounter preview the player defaults to
  Squall (`d0c000.dat`) from the battle folder when no custom opponent is loaded.
- **Starting view** supplies the preceding camera for shots that start with a previous-view
  reference. Model animation and the selected skeletal clip can be changed independently.

The raw coordinate modes survive playback: caster/target attachment points use the
skeleton header's F0..FE bone selectors; F3/F4 refer to the preceding view; F2/F5..F8 use
the caster/target midpoint bases. Layout 1 resolves a block's keyframes once on entry;
layout 0 resolves them live. Block timing, final holds, easing and cubic curves reuse
the camera math already used by Watts. The renderer applies the projection H value
(higher means a tighter lens), the battle screen centre (160,108), roll and model root.
Close-up clipping uses the actual camera distance rather than the unrelated orbit zoom.

Playback uses elapsed wall time at 15 game ticks per second. Delayed redraws skip to
the due tick instead of stretching the camera duration; pause/resume and manual seeking
reset the clock anchor. Native shots still have their original 15 Hz sampling.
Auxiliary actors use cached topology, UVs, posed frames and shared textures. Culling
and fallback shading are vectorized; materials are submitted through vertex arrays,
without a Python normal/vertex loop per triangle. Textures are extracted on first
model import and uploaded once per preview context, not during each animation tick.

The normal party formation comes from `computeSomeStatusData` (EN `0x47DBA0`),
using the table at `0xB81030` (world XYZ, Y down):

| Party size | Positions in party-slot order |
| --- | --- |
| 1 | `(0,0,1800)` |
| 2 | `(-1000,0,1800)`, `(1000,0,1800)` |
| 3 | `(-1200,0,2100)`, `(0,0,1500)`, `(1200,0,2100)` |

`resetBasedRotation` (`0x502070`) gives party actors Y rotation 0 and monsters
2048 (half a turn). These replace the previous origin placeholder and reversed facing.

This fixes the former origin-camera problem: valid F3/F4 keyframes with zero offsets
were stripped of their reference modes and placed the eye and target at the model centre.
Squall's first six opening shots include these holds.

## Fujin: effect cameras

Fujin's **Camera effect editor** tab reuses the same player for the 221 spell/attack camera
tracks stored in the exe, and only feeds the shared setup. Import characters (`d?c###.dat`),
their weapons (`d?w###.dat`) and monsters (`c0m###.dat`) with **Import models…** or the header's
**Import read-only**; they are read-only and remembered for Auto-upload. Each **Party** slot
takes a character and one of its weapons. **Open scene.out** (the shared file, also in the
setup's encounter picker) places a real encounter: pick it in **Battle setup**, and **Caster** /
**Target** then list its battle slots, party members and enemies alike. Without scene.out the
setup's manual placement puts the caster and an imported monster face to face.

An effect track starts with a camera script that chooses the animation to play. Fujin runs it
(`FF8GameData/dat/camerascript.py`, the shared VM's arithmetic and jumps plus the camera
op codes). The attacker and target slots (C3 18/19) are the setup's caster/target slots; the
**Script inputs** set the rest: opening shot (camera variable 0: 0-5 for a character, 8 for a
monster's Magic, -1 for none), target status (C3 16), target camera category (C3 15, from the
target monster's byte 246), affected targets, action count and the random value (C3 11;
C3 1C-22 use it modulo 2-8). The line under the inputs names the chosen animation index
(set = index >> 4, slot = index & 7) and the values the script read. **▶ Play effect camera**
runs it again; a slot's **▶ Preview** plays that slot as is. Keyframe edits replay at once
from the same tick.

## Scope

This is a preview of the selected DAT camera animation with manual or encounter placement,
not a replay of a complete game action. It does not run a magic effect's procedural
camera code, camera-setting VM, actor choreography VM, battle AI or camera shake. The
chosen skeletal clip is previewed directly. Encounter mode supplies the enemy slots
and the selected normal party formation; surprise/back-attack rotation, intro-camera
scripts and stage animations are not replayed. The encounter camera bytes do not replace
the DAT animation being previewed. Manual mode places two actors. A literal reference
to another unavailable slot is reported.
The effect-owned F9 frame is unavailable and is explicitly reported when a target-frame
fallback is used. Floating-point transforms, easing and splines approximate fixed-point
engine rounding. Use the game to verify final effect/animation handoffs.

## Reuse and validation

The Sequence tab already reads scene.out to place a monster in a real encounter; its
shared encounter parser is reused here.
Laguna already has Game/Free camera views for GF cinematics. Its engine look-at basis
is reused here, along with Watts' existing easing/spline functions and Ifrit3D's posed
body/weapon renderer. Watts keeps its existing pre-baked composite placement.

The targeted tests cover previous-view holds, snapshot/live modes, target/midpoint
placement, lens/roll, final holds, Squall's six opening shots, opponent import without
editing DAT bytes, and the shared Qt controls. Character camera round-trips,
SolomonRing character/weapon previews and Watts playback are checked separately.
Encounter checks cover source model switching, duplicate monster slots, XYZ preservation,
automatic asset lookup, actor mesh indices, named/modded monsters, normal party
formations, absence of stage geometry, invalid imports and shared-file closing.
Clock regressions cover delayed callbacks, pause/resume, seeking and final holds.
Prepared-mesh checks cover quad winding/culling, UVs and per-model texture mapping.
