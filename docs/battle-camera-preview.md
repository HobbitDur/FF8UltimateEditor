# Battle camera preview

Ifrit's Camera tab and SolomonRing's character camera preview share a battle-context
player. Choose a set/animation and click Preview, then scrub the frame slider or Play.
The player keeps the final camera pose visible after playback ends.
An empty camera keeps the configured starting view and still displays the encounter.

- **Game camera** uses the DAT shot, its projection/lens and roll, inside a 4:3 viewport.
- **Free camera** lets you orbit, pan and zoom to inspect the surrounding scene.
- **Open scene.out** reads the encounter list without modifying it. Choose an encounter
  by its zero-based ID, stage and enemy list, then select the enemy slot. For a monster
  DAT, only encounters containing that monster are offered; duplicate instances have
  separate slot choices. A character DAT can preview any nonempty encounter.
- In encounter mode, enemy XYZ coordinates come directly from the selected record.
  The loaded monster occupies its chosen slot; a loaded character occupies party slot 0
  at the origin. The opposing party member in a monster preview also uses slot 0 at the
  origin. **Party placement and normal facing are assumptions**, not data in scene.out.
- Enemy DATs and `a0stgNNN.x` are searched beside scene.out first, then beside the loaded
  model. Available enemies and the static stage are displayed without textures; missing
  assets are reported. The stage sky dome is hidden. Auxiliary imports never save files.
  The loaded model keeps its normal textures and weapon. Scene files opened in another
  tool are shared through the file bank. Closing scene.out restores manual placement.
- Expand **Battle setup** to choose whether the loaded model is the caster or target,
  set their battle slot IDs and place the opponent in world units (Y points down) in
  manual mode. Encounter mode derives those slots and disables manual coordinates.
- The opponent starts as a marker. **Load opponent** imports another monster/character
  DAT read-only and displays its posed mesh without textures. Clear returns to the marker.
- **Starting view** supplies the preceding camera for shots that start with a previous-view
  reference. Model animation and the selected skeletal clip can be changed independently.

The raw coordinate modes survive playback: caster/target attachment points use the
skeleton header's F0..FE bone selectors; F3/F4 refer to the preceding view; F2/F5..F8 use
the caster/target midpoint bases. Layout 1 resolves a block's keyframes once on entry;
layout 0 resolves them live. Block timing, final holds, easing and cubic curves reuse
the camera math already used by Watts. The renderer applies the projection H value
(higher means a tighter lens), the battle screen centre (160,108), roll and model root.
Close-up clipping uses the actual camera distance rather than the unrelated orbit zoom.

This fixes the former origin-camera problem: valid F3/F4 keyframes with zero offsets
were stripped of their reference modes and placed the eye and target at the model centre.
Squall's first six opening shots include these holds.

## Scope

This is a preview of the selected DAT camera animation with manual or encounter placement,
not a replay of a complete game action. It does not run a magic effect's procedural
camera code, camera-setting VM, actor choreography VM, battle AI or camera shake. The
chosen skeletal clip is previewed directly. Encounter mode supplies the enemy slots
and optional static stage; party formation, surprise/back-attack rotation, intro-camera
scripts and stage animations are not replayed. The encounter camera bytes do not replace
the DAT animation being previewed. Manual mode places two actors. A literal reference
to another unavailable slot is reported.
The effect-owned F9 frame is unavailable and is explicitly reported when a target-frame
fallback is used. Floating-point transforms, easing and splines approximate fixed-point
engine rounding. Use the game to verify final effect/animation handoffs.

## Reuse and validation

The Sequence tab already reads scene.out to place a monster in a real encounter; its
shared encounter parser is reused here. Alexander supplies the static stage parser.
Laguna already has Game/Free camera views for GF cinematics. Its engine look-at basis
is reused here, along with Watts' existing easing/spline functions and Ifrit3D's posed
body/weapon renderer. Watts keeps its existing pre-baked composite placement.

The targeted tests cover previous-view holds, snapshot/live modes, target/midpoint
placement, lens/roll, final holds, Squall's six opening shots, opponent import without
editing DAT bytes, and the shared Qt controls. Character camera round-trips,
SolomonRing character/weapon previews and Watts playback are checked separately.
Encounter checks cover source model switching, duplicate monster slots, XYZ preservation,
automatic asset lookup, stage mesh indices, invalid imports and shared-file closing.
