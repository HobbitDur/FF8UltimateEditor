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

The two labelled save buttons write their respective output. The shared header
Save writes whichever backing data has edits. With no edits it offers to save
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
the marker counts the records there. Click to select/cycle overlapping records,
or select one in the table. Use the mouse wheel to zoom in or out.

Load complementary `wmx.obj` to position markers at their terrain-triangle
centroids and outline the selected triangle. The trigger covers the triangle,
not just its centroid. CID also builds a flat terrain overview from this file,
so the background and markers use the same projection. This is the **base
world**: story replacement segments may differ.

Only dragging a selected marker moves it. Clicking empty map or a marker never
changes coordinates. A drag requires the normal system drag threshold. With
wmx loaded the drop chooses the triangle under the pointer and updates all three
position bytes. Without wmx, dragging changes only the block bytes and preserves
the triangle index; that index must exist in the destination block to work in-game.
The table still allows direct byte edits. Nothing moves until wmset is loaded.

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
250-255 begin in phase 3. The attached guide and Papastew disagree on the disc
cutover for Alcauld Plains, so CID deliberately reports the verified phase values.

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
