# CID draw points: files, positions and story phases

CID currently targets **the original English PC / Steam 2013 EXE**. Its offsets
and world-phase lookup are for that build.

## Which file should I save?

| Edit | Input | Output |
| --- | --- | --- |
| Magic ID, refill, high yield, for both field and world points | FF8 EXE | `.hext` patch; the EXE is not overwritten |
| Ordered draw-group searches for each world phase | FF8 EXE | Same `.hext` patch |
| World block X/Y and terrain triangle index | `wmsetus.obj` (or the matching language's `wmsetxx.obj`) | Updated `.obj` |
| Draw-ID ranges defining group contents | `wmsetxx.obj` | Same updated `.obj` |
| Spell names displayed by CID | Optional complementary `kernel.bin` | None; read-only |
| Triangle positions displayed by CID | Optional complementary `wmx.obj` | None; read-only |

The shared header **Save** button writes whichever backing data has edits:
magic and phase searches to Hext, positions and group ranges to wmset. There are
no separate CID save/export buttons for these outputs. With no edits it offers to save
the loaded outputs again. Cancelling a save keeps that output marked modified.
Changing both kinds of data requires **both** outputs in the game: apply the Hext
through the mod's patch loader, and replace/repack the matching world archive's
`wmsetxx.obj`. Saving positions alone does not change the spell or refill flags.
`kernel.bin` is the name reference; rename spells with a kernel editor, then reload
the complementary file in CID. With no kernel loaded CID displays numeric magic
IDs, with no built-in spell-name fallback. The six-bit EXE field allows IDs 0-63.

## Why does a point look misplaced or missing?

A world trigger is `(block ID, triangle index)`, not an arbitrary X/Y coordinate.
The two block bytes decode as `column = x & 127`, `row = 2*y + (x >> 7)` on a
128 x 96 grid. The third byte is the terrain polygon index; it is not a magic ID.

With only wmset loaded, the marker is at the **approximate block centre**, and
the selected block is outlined. Points sharing a block overlap; the number beside
the marker counts the records there, even when their triangle indices differ.
For example, **5 means five records**, not Draw ID 5. Click to select/cycle overlapping records,
or select one in the table. Use the mouse wheel to zoom in or out.
The bundled background is illustrative, so a block-centre marker near the coast
can appear in the water. These approximate positions do not change the saved bytes.

Load complementary `wmx.obj` to position markers at their terrain-triangle
centroids and outline the selected triangle. The trigger covers the triangle,
not just its centroid. CID also builds a flat terrain overview from this file,
so the background and markers use the same projection. This is the **base
world**: story replacement segments may differ.
When loading wmset, CID automatically opens a sibling `wmx.obj` as a read-only
complementary file if no terrain is already loaded or selected. A manually loaded
terrain file is preserved. Otherwise use the read-only import to choose it.

The checkboxes beside Game version select **phases 0-4** in any combination.
For example, check phases 1 and 2 to show their combined records; a record in both
phases is drawn once. Hover over a checkbox for its record count. **No phase**
also includes records searched by none of the phases, including the original
unused ID 256. Check only No phase to inspect those records, or combine it with
normal phases. Clearing every checkbox hides all markers. The view uses the
stored position even when an unused slot contains zero coordinates. Changing
these checkboxes does not edit the file or create an undo step.

The original Hell-island record **ID 215** refers to block `(9, 49)`, triangle
32, whose ground type in the base wmx is **34 (sea)**. This is already in the
source files; CID preserves it rather than moving it to a nearby land triangle.
Being included in a phase's search range does not prove physical accessibility.

Click and drag any marker to move it in one gesture; it need not be selected
first. A click without a drag selects it; later clicks cycle overlapping records.
Dragging empty map never moves a point. A drag requires the normal system drag threshold. With
wmx loaded the drop chooses the triangle under the pointer and updates all three
position bytes. Without wmx, dragging changes only the block bytes and preserves
the triangle index; that index must exist in the destination block to work in-game.
The table still allows direct byte edits. Nothing moves until wmset is loaded.

**Ctrl+Z** undoes the last CID edit; **Ctrl+Shift+Z** or **Ctrl+Y** redoes it.
Each completed drag is one undo step, restoring its block and triangle together.
History also includes table edits, magic/refill/high-yield settings, group ranges,
phase search rules, and each CSV import as one step. Undo selects the affected
draw or tab and refreshes the map and editor values. Save indicators track the
last successful save independently for Hext and wmset; cancelling one output
keeps it unsaved. Saving preserves history; opening/reloading/closing a primary
EXE or wmset starts a new history to avoid restoring another file's data.
Read-only kernel/terrain loads and phase-view changes preserve history.

## Editing groups and phase availability

The **Groups and phases** tab edits two parts of the draw-point rules:

- **Group contents**: set the first and last Draw ID included in each group, or
  clear **Has members** to empty that group. Select a group to inspect its member
  IDs, spell names (when kernel.bin is loaded), default locations and phase list.
- **Phase searches**: choose up to four group searches per world phase, in order.
  Choose **None** to remove a search; later groups shift left. An empty row makes
  that phase scan no draw groups.

The original format has **five groups (0-4)**. A group is one contiguous range,
and ranges may overlap. There is no independent membership bit per draw point.
Changing a range preserves draw IDs, magic bytes and saved draw-status IDs.
Adding a sixth group would require changing the executable's format handling:
it reads the records-base pointer at header offset 40, directly after five ranges.
CID therefore exposes the five existing groups rather than inserting another
range into the records-base pointer.

The game searches groups in the specified order, and records in ascending ID
order within each group. The first record matching the player's block and
triangle wins. The tab reports distinct draw IDs sharing a trigger in the same
phase, identifying the ID that matches first. Reordering searches can change
which spell is obtained at that trigger.

Group-range edits mark **wmset** modified. Phase-search edits mark **Hext**
modified. Both immediately refresh the draw table's phase column, map filter
membership and the member preview. Opening files in either order works: the
phase searches come from the **loaded EXE**, including its existing custom rules.
Until an EXE is loaded, phase editing is disabled and the preview identifies its
use of the original OG rules. The Hext output includes all 20 loaded phase-table
bytes, preserving negative terminators and ignored trailing bytes in unchanged
rows; surrounding EXE data is not exported by this table. CSV continues to carry
only individual draw data and positions, not group ranges or phase rules.

## Story dependence is real; disc labels are only a guide

The **Phase info** icon in the top row, after the phase checkboxes, explains the story
transitions and lists the exact original JSM assignment sites. It is available
without loading game files. These explanations describe the original English
scripts; a mod that changes field scripts can change the transitions.

| Phase | When the original scripts assign it | Disc context |
| --- | --- | --- |
| 0 | Initial variant; no normal field script in the audit explicitly assigns 0 | Disc 1 and early Disc 2 |
| 1 | Missile Base finale, during Selphie's team's escape; both ending branches assign 1 | Disc 2 |
| 2 | After Balamb Garden's emergency steering movie, avoiding Balamb town; story progress is set to 570 | Disc 2, continuing into early Disc 3 |
| 3 | After the Esthar city-reveal sequence on the approach bridge beyond the Great Salt Lake; story progress is set to 1750 | Disc 3 |
| 4 | During the successful rescue of Rinoa in space, after the Lunar Cry; reasserted in the later Esthar air-station scene at story progress 3150 | Late Disc 3 and Disc 4 |

The six normal field-script writes to variable 266 were checked directly:

| Phase | Original field script | Absolute JSM byte offset of `POPM_B 266` |
| --- | --- | --- |
| 1 | `gmpark2`: `lastevent2_1::touchOn` | `0x1CD4` |
| 1 | `gmpark2`: `lastevent2_2::touchOn` | `0x2410` |
| 2 | `bgsido_8`: `dic::defalut` (original spelling) | `0x2284` |
| 3 | `ewbrdg1`: `Director::default` | `0x1AD0` |
| 4 | `ssspace2`: `director0::default` | `0xDBC` |
| 4 | `eaplane1`: `Director::default` | `0x648` |

Each assignment is immediately preceded by `PSHN_L <phase>`. These are offsets
inside the original English JSM files, not Hext addresses. The original `.sym`
files supply the entity/method names. The audit excludes `test*` fields and the
unused `bgmast_6` debug menu. The real-file regression test verifies every listed
assignment, its symbol, and that the list covers all non-debug writers to the
phase byte across the extracted field scripts. Reading scripts for this audit
does not modify them.

`WorldMap_DrawPointsParsing_wmset35` at VA `0x54F920` selects up to four ranges
from the wmset header using `WM_WorldPhase & 31`. This is a **story phase**, not
a world region or a direct disc-number check. The original English EXE's lookup
at VA `0xC76770` is:

| World phase | Range groups scanned |
| --- | --- |
| 0 | 0, 1 |
| 1 | 0, 2 |
| 2 | 0, 2, 3 |
| 3 | 0, 2, 3, 4 |
| 4 | 0, 2, 3, 4 |

CID reads each range's offsets from the loaded wmset and reads the phase table
from EXE file offset `0x876770` (20 bytes for five rows). The editor changes these
rules, without modifying the scripts that advance the saved phase. The saved
selector is field-script variable **266**, `WorldmapVariantIndex`, copied into
the runtime phase during world-map initialization. Phase numbers are **not disc
numbers**; there are five supported phases and four discs. Physical accessibility
(vehicles, barriers and terrain) is separate from being scanned by this lookup.

In the original `wmsetus.obj`, Draw ID 246 is scanned only in phase 0; ID 247
is scanned in phases 1-4. They have the same block and triangle, but their EXE
bytes give Blizzard and Cure respectively. IDs 248-249 begin in phase 2;
250-255 begin in phase 3. This resolves the guide discrepancy: Alcauld Plains
stays Blizzard into early Disc 2 and changes to Cure at the phase-1 assignment
in the Missile Base finale, rather than switching merely because Disc 2 starts.

## Inventory audit against the original game files

The EXE has 256 draw-data bytes (128 field slots and 128 world slots). The
original wmset has 128 world records: **127 are scanned** by the phase ranges;
the final slot, Draw ID 256, is outside every range. The two Alcauld variants
mean there are **126 distinct world triggers**, not 127 separate locations.

The islands contain **28 Heaven records (185-212)** and **33 Hell records
(213-245)**. Their shared blocks caused many markers to be drawn on top of each
other. Papastew's world table lists 28 Heaven and 32 Hell entries; its extra
field-map table also must not be counted as additional world positions. The game
has four Hell Flare records (215, 229, 236, 243), while that guide lists three.
CID already included the slots; the audit fixes their labels and makes overlaps
visible instead of inventing new records.

Corrected location references include:

- 129: Gaulg Mountains; 130: Raha Cape.
- **136: Yaulny Canyon, Fire at the railway bridge**, previously labelled unused.
- 166: Monterosa Plateau, Double, previously labelled unused.
- 213-214: Hell, previously labelled Heaven.
- 246: Alcauld Plains, previously labelled Hell.
- 248-250 and 254-256: shifted location labels corrected, including unused 256.

Changing a location label does not change game data. Every original world record's
triangle index resolves in the base `wmx.obj`. No-edit wmset saves are byte-exact;
position edits preserve the phase header, padding and every other section. Group
edits change only the selected range's eight header bytes.

References: [Papastew draw-point guide](https://www.papastew.co.uk/ff8draw),
[world-map wmset format](https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/worldmap/worldmap-wmsetxx-file-format/),
[wmx terrain format](https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/worldmap/worldmap-wmx-file-format/).
The runtime conclusions above were checked against the local English 2013
executable in IDA, rather than inferred from the guide image.
