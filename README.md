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

### TonberryShop — shop editor (`mngrp.bin`)
Edits the items/prices/stock sold in each shop (Balamb, Dollet, Timber, Deling City…).

<img src="Resources/screenshots/tonberryshop.png" width="800">

### CCGroup — Triple Triad card editor
Edits Triple Triad card values (ranks/elements) and which cards NPCs play with.

<img src="Resources/screenshots/ccgroup.png" width="800">

### DrawEditor — draw point editor
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

  ![image](https://github.com/HobbitDur/ifrit-enhanced/assets/19329243/0f1d58c2-4ed4-49c7-b5cb-d9cb8e5120ae)

- **Siren** — `price.bin` editor (shop/item prices). Now also built in (see the Siren tool above);
  the standalone launcher is kept for reference.

  ![alt tag](https://cloud.githubusercontent.com/assets/5892410/19022992/084a8e60-88e4-11e6-9307-461bc264e039.png)

- **Doomtrain** — `kernel.bin` editor (general game/battle data).

  <img src="https://cloud.githubusercontent.com/assets/5892410/17307688/b5270ade-5836-11e6-8e03-e2f91e47c0f8.png" width="30%"></img> <img src="https://cloud.githubusercontent.com/assets/5892410/17307689/b52c1218-5836-11e6-9094-2756dbacd76b.png" width="30%"></img> <img src="https://cloud.githubusercontent.com/assets/5892410/17307690/b535fb5c-5836-11e6-8d6a-a3cf0c11a1a0.png" width="30%"></img>

- **Junkshop** — `mweapon.bin` editor (weapon data).

  <img src="https://cloud.githubusercontent.com/assets/5892410/18587447/6644466a-7c22-11e6-9ca9-61b83ed162e5.png"></img>

- **Quezacotl** — `init.out` editor (new-game starting data).

  ![image](https://github.com/user-attachments/assets/50aea64e-1a87-43c2-9356-48d677c37174)

- **Jumbo Cactuar** — `Scene.out` editor (field encounters).
- **Deling** — archive editor (browse/extract/repack the game's `.fs`/`.fi`/`.fl` archives).
- **Hyne** — save file editor.
- **VincentTim** — command-line texture converter for FF7/FF8 `.tim`/`.tex` files (see its own
  [README](ExternalTools/VincentTim/README.md)).

## CLI

`cli.py` exposes GUI features as scriptable commands, useful for batch processing or CI pipelines
without opening any window:

```
python cli.py shumi-translator export-csv --input kernel.bin --output kernel.csv
python cli.py shumi-translator import-csv --input kernel.bin --csv kernel.csv
python cli.py shumi-translator compress --input kernel.bin --output kernel_compressed.bin
```

Run `python cli.py --help` to list all available tools and commands.

# Donate
You can help me releasing those tools on my [Patreon](https://www.patreon.com/c/hobbitmods)
