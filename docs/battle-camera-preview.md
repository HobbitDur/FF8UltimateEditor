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
  model. Available enemies are displayed without textures; missing
  assets are reported. Only actors are drawn: no battle stage, ground grid or axis gizmo.
  Auxiliary imports never save files.
  The loaded model keeps its normal textures and weapon. Scene files opened in another
  tool are shared through the file bank. Closing scene.out restores manual placement.
- Expand **Battle setup** to choose whether the loaded model is the caster or target,
  set their battle slot IDs and place the opponent in world units (Y points down) in
  manual mode. Encounter mode derives those slots and disables manual coordinates.
- **Load opponent** imports another monster/character DAT read-only and displays its
  posed mesh without textures. In a monster encounter preview the player defaults to
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
