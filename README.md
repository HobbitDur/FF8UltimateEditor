# FF8 Ultimate Editor

A collection of tools for modding **Final Fantasy VIII** (PC/Remaster), all bundled behind one
launcher: `FF8UltimateEditor.exe` (or `python main.py`). Pick a tool from the "Hobbit tools" dropdown
at the top of the window, or launch one of the external programs from the toolbar next to it.

A command-line interface (`cli.py`) is also available for scripting text import/export without
opening the GUI (see [CLI](#cli) below).

Make your choice!

## Tools made by HobbitDur

These are built into the app and selected from the "Hobbit tools" dropdown.

### Ifrit — monster / battle model editor (`c0m*.dat`)
All-in-one editor for monster and summon battle files, organized as tabs sharing one file toolbar:
- **AI** — decompiles and edits monster AI scripts (conditions/commands) as readable pseudo-code.
- **Seq** — edits animation sequences (the byte-code that drives monster/summon animations).
- **3D** — views the monster's 3D model and animations (mesh/wireframe, playback speed, bone list), with glTF export.
- **Texture** / **Dynamic Texture** — edits the monster's textures and palette-animation (VRAM) effects.
- **Xlsx** — exports/imports monster stats to/from an Excel spreadsheet for easy bulk editing.

<img src="Resources/screenshots/ifrit_3d.png" width="800"><br>
<img src="Resources/screenshots/ifrit_texture.png" width="800"><br>
<img src="Resources/screenshots/ifrit_ai.png" width="800">

### ShumiTranslator — text editor (all in-game text)
Edits every text string in the game (dialogue, menus, items, names…), with CSV export/import for
bulk translation work.

<img src="Resources/screenshots/shumitranslator.png" width="800">

### TonberryShop — shop editor (`shop.bin`)
Edits which items each shop sells (Balamb, Dollet, Timber, Deling City…), and the per-slot "rare"
flag. (Item prices live in `price.bin` — see the Siren tool.)

<img src="Resources/screenshots/tonberryshop.png" width="800">

### CCGroup — Triple Triad card editor
Edits Triple Triad card values (ranks/elements) and which cards NPCs play with.

<img src="Resources/screenshots/ccgroup.png" width="800">

### Cid — draw point editor
Edits every draw point in the game (field and world map), including which spell/quantity/refill
rate it gives, and its position on the world map.

<img src="Resources/screenshots/draweditor.png" width="800">

### SolomonRing — Guardian Force editor (`kernel.bin`)
Edits GF data: general stats, learnable abilities, and character/GF junction compatibility.

<img src="Resources/screenshots/solomonring.png" width="800">

### PuPuCargo — item menu editor (`mitem.bin`)
Edits how items behave in menus (what they refine into, what they do when used, their parameters).

<img src="Resources/screenshots/pupucargo.png" width="800">

### Seed — field character model viewer
Views field character models and their animations (NPCs from `chara.one` and main characters from
`main_chr.fs`).

<img src="Resources/screenshots/seed.png" width="800">

### Pandemona — refine ability editor
Edits GF refine abilities: which items/cards convert into which magic, and in what quantity.

<img src="Resources/screenshots/pandemona.png" width="800">

### Alexander — battle stage viewer
Views and edits battle stage geometry/textures (`a0stgXXX.x` files from `battle.fs`).

<img src="Resources/screenshots/alexander.png" width="800">

### Julia — sound editor
Edits the battle sound archive (`audio.fmt` / `audio.dat`).

<img src="Resources/screenshots/julia.png" width="800">

### Siren — item price editor (`price.bin`)
Edits each item's buy price and sell price multiplier (the sell price the shop pays back is
`round((buy price / 10 / 2) * sell multiplier)`). Ported from the original Siren tool.

## Other tools made by other modders (launched from the toolbar)

These are external, standalone programs. The launcher can check for and download updates for them
automatically (see the update button in the toolbar).

- **IfritGui** — the original Ifrit tool for editing monster stats.

  <img src="Resources/screenshots/ifritgui.png" width="800">

- **Siren** — `price.bin` editor (shop/item prices). Now also built in (see the Siren tool above);
  the standalone launcher is kept for reference.

  <img src="Resources/screenshots/siren_external.png" width="800">

- **Doomtrain** — `kernel.bin` editor (general game/battle data).

  <img src="Resources/screenshots/doomtrain_1.png" width="30%"></img> <img src="Resources/screenshots/doomtrain_2.png" width="30%"></img> <img src="Resources/screenshots/doomtrain_3.png" width="30%"></img>

- **Junkshop** — `mweapon.bin` editor (weapon data).

  <img src="Resources/screenshots/junkshop.png"></img>

- **Quezacotl** — `init.out` editor (new-game starting data).

  <img src="Resources/screenshots/quezacotl.png" width="800">

- **Jumbo Cactuar** — `Scene.out` editor (field encounters).
- **Deling** — archive editor (browse/extract/repack the game's `.fs`/`.fi`/`.fl` archives).
- **Hyne** — save file editor.
- **VincentTim** — command-line texture converter for FF7/FF8 `.tim`/`.tex` files (see its own
  [README](ExternalTools/VincentTim/README.md)).

## CLI

`cli.py` exposes GUI features as scriptable commands, useful for batch processing, translation
work, or CI pipelines without opening any window. Every tool runs headless (no Qt window) and
edits the same files as its GUI counterpart.

```
python cli.py <tool> <command> [options]
```

- `python cli.py --help` lists every tool.
- `python cli.py <tool> --help` lists a tool's commands and their options.

Run it from the repo root (with the project's virtualenv active). The tools that need the game's
reference data load it automatically from `FF8GameData/`.

### Conventions

- **CSV** exports use `|` as the delimiter; imports auto-detect `|`, `;` or `,`, so a file edited
  in Excel still re-imports cleanly. The `shumi-translator` and `cid` CSV formats match what the
  GUIs produce, so files are interchangeable between CLI and GUI.
- **`--output`/`-o` is optional** on most in-place editors: omit it to overwrite the input file,
  or give a path to write a copy. Import commands only touch the fields you changed, and a no-edit
  round-trip reproduces the original file byte-for-byte (except `kernel.bin`, whose text offsets
  are recomputed, and `init.out`, which is grown to its full size so every item slot is editable —
  both matching the GUI's own save behaviour).

### Available tools

| Tool | Edits | Commands |
| --- | --- | --- |
| `shumi-translator` | all in-game text (`kernel.bin`, `mngrp.bin`, `namedic.bin`, field/world/battle, exe) | `export-csv`, `import-csv`, `export-all`, `export-all-{field,battle,kernel,namedic,mngrp,exe,world}`, `compress`, `uncompress` |
| `ifrit` | monster/summon `c0m*.dat` (stats, model, animation seq) | `export-xlsx`, `import-xlsx`, `export-gltf`, `import-gltf`, `export-seq-xml`, `import-seq-xml` |
| `ifrit-ai` | monster AI scripts in `c0m*.dat` | `export-md`, `compile-md` |
| `solomon-ring` | `kernel.bin` (all data sections, field-level) | `list-sections`, `list-fields`, `get`, `set`, `export-csv`, `import-csv` |
| `tonberry-shop` | shop inventories (`shop.bin`) | `export-csv`, `import-csv` |
| `siren` | item prices (`price.bin`) | `export-csv`, `import-csv`, `set-price` |
| `junkshop` | weapon-upgrade recipes (`mwepon.bin`) | `export-csv`, `import-csv` |
| `pupu-cargo` | item menu behaviour (`mitem.bin`) | `export-csv`, `import-csv` |
| `pandemona` | GF refine formulas (`mngrp.bin`) | `export-csv`, `import-csv` |
| `quezacotl` | new-game starting data (`init.out`) | `export-json`, `import-json` |
| `ccgroup` | Triple Triad NPC card players (field `.jsm`) | `list`, `export-csv`, `import-csv`, `set-param` |
| `cid` | draw points (exe `.hext` + world positions in `wmset`) | `export-csv`, `import-csv` |
| `julia` | battle sounds (`audio.fmt` / `audio.dat`) | `list`, `export-wav`, `export-all`, `replace` |
| `alexander` | battle stages (`a0stgXXX.x`) | `export-glb`, `import-glb` |
| `seed` | field model containers (`chara.one`) | `list-models` |
| `jp-font-builder` | JP font atlas for the ILP-JP mod | `build`, `decode` |

### Examples

Text (translation workflow):

```
python cli.py shumi-translator export-csv --input kernel.bin --output kernel.csv
python cli.py shumi-translator import-csv --input kernel.bin --csv kernel.csv
python cli.py shumi-translator compress   --input kernel.bin --output kernel_compressed.bin
python cli.py shumi-translator export-all  --input-dir game_lang --output-dir csv_out
```

Binary editors (CSV round-trip, `--output` optional):

```
python cli.py tonberry-shop export-csv --input shop.bin   --output shops.csv
python cli.py tonberry-shop import-csv --input shop.bin   --csv shops.csv --output shops_new.bin
python cli.py siren         set-price  --input price.bin  --item-id 24 --buy-price 3000
python cli.py junkshop      export-csv --input mwepon.bin --output weapons.csv
python cli.py pupu-cargo    export-csv --input mitem.bin  --output items.csv
python cli.py pandemona     export-csv --input mngrp.bin  --output refine.csv
```

kernel.bin field editing (addressed by section → entry → field):

```
python cli.py solomon-ring list-sections
python cli.py solomon-ring list-fields --section 2
python cli.py solomon-ring get --input kernel.bin --section 2 --entry 1
python cli.py solomon-ring set --input kernel.bin --section 2 --entry 1 --field spell_power --value 99
python cli.py solomon-ring export-csv --input kernel.bin --section 2 --output magic.csv
```

New-game data as JSON:

```
python cli.py quezacotl export-json --input init.out --output init.json
python cli.py quezacotl import-json --input init.out --json init.json
```

NPC card players (a literal value, or `var:N` to read a savemap variable):

```
python cli.py ccgroup list       --folder extracted_files/field/mapdata
python cli.py ccgroup export-csv  --folder extracted_files/field/mapdata --output players.csv
python cli.py ccgroup import-csv  --folder extracted_files/field/mapdata --csv players.csv
python cli.py ccgroup set-param   --jsm bghall_1.jsm --player 0 --param rare-chance --value 99
```

Draw points (exe byte + world map position):

```
python cli.py cid export-csv --exe FF8_EN.exe --wmset wmset.obj --output draws.csv
python cli.py cid import-csv --csv draws.csv --exe FF8_EN.exe --wmset wmset.obj \
    --output-hext draw.hext --output-wmset wmset_new.obj
```

3D models and sound:

```
python cli.py ifrit     export-gltf --input c0m071.dat --output c0m071.glb
python cli.py ifrit     export-xlsx --input extracted_files/battle --output monsters.xlsx
python cli.py alexander export-glb  --input a0stg001.x --output stage.glb
python cli.py julia      export-wav  --fmt audio.fmt --index 1 --output sound.wav
python cli.py julia      replace     --fmt audio.fmt --index 1 --wav new.wav
```

# Donate
You can help me releasing those tools on my [Patreon](https://www.patreon.com/c/hobbitmods)
