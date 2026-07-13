"""
FF8 Lab — live test pipeline orchestrator.

Ties together: md AI source → ifrit-ai compile → Junction VIII mod folder
(hot-swap) → game launch. Designed for the loop:

    edit md → `ff8lab deploy c0m028` → re-enter battle in game → observe.

Paths are machine-specific and read from pipeline/config.local.json
(see config.local.json.example).

Usage (from the FF8UltimateEditor root, with the venv python):
    python pipeline/ff8lab.py seed c0m028      # export vanilla AI to md workdir (start editing from there)
    python pipeline/ff8lab.py deploy c0m028    # compile md + copy .dat into the J8 mod folder
    python pipeline/ff8lab.py launch           # start the modded game via Junction VIII if not running
    python pipeline/ff8lab.py status           # game running? files deployed?
    python pipeline/ff8lab.py restore c0m028   # put the vanilla .dat back in the mod folder
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = pathlib.Path(__file__).resolve().parent / "config.local.json"

sys.path.insert(0, str(REPO_ROOT))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[error] Missing {CONFIG_PATH}. Copy config.local.json.example and adjust paths.", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def game_running() -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq FF8_EN.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True,
    ).stdout
    return "FF8_EN.exe" in out


def _paths(cfg: dict, monster: str):
    """Resolve (base_dat, md_source, deployed_dat) for a monster like 'c0m028'."""
    base_dat = pathlib.Path(cfg["vanilla_battle_dir"]) / f"{monster}.dat"
    md_source = pathlib.Path(cfg["md_workdir"]) / f"{monster}.md"
    deployed = pathlib.Path(cfg["j8_mod_battle_dir"]) / f"{monster}.dat"
    return base_dat, md_source, deployed


def cmd_seed(cfg: dict, monster: str) -> int:
    from Cli.ifrit_ai import _load_enemy, _ai_data_to_md
    base_dat, md_source, _ = _paths(cfg, monster)
    if not base_dat.exists():
        print(f"[error] Vanilla dat not found: {base_dat}", file=sys.stderr)
        return 1
    if md_source.exists():
        print(f"[error] {md_source} already exists, not overwriting (delete it to re-seed).", file=sys.stderr)
        return 1
    md_source.parent.mkdir(parents=True, exist_ok=True)
    game_data, enemy, compiler, decompiler = _load_enemy(str(base_dat))
    md_source.write_text(_ai_data_to_md(game_data, enemy.battle_script_data['ai_data'], decompiler), encoding="utf-8")
    print(f"[ok] Seeded {md_source} from vanilla {monster}.dat — edit it, then run: deploy {monster}")
    return 0


def cmd_deploy(cfg: dict, monster: str) -> int:
    from FF8GameData.dat.daterrors import AICodeError
    from Cli.ifrit_ai import _load_enemy, _md_to_ai_data
    base_dat, md_source, deployed = _paths(cfg, monster)
    if not md_source.exists():
        print(f"[error] No md source: {md_source} (run 'seed {monster}' first)", file=sys.stderr)
        return 1
    game_data, enemy, compiler, decompiler = _load_enemy(str(base_dat))
    try:
        _md_to_ai_data(str(md_source), enemy, compiler, decompiler)
        if AICodeError.has_errors():
            print(AICodeError.format_errors_for_display(), file=sys.stderr)
            AICodeError.clear_errors()
            return 1
    except AICodeError:
        print(AICodeError.format_errors_for_display(), file=sys.stderr)
        AICodeError.clear_errors()
        return 1
    # Optional stat overrides: <monster>.stats.json next to the md,
    # e.g. {"hp": [4, 11, 0, 255], "str": [10, 10, 10, 10]}
    stats_file = md_source.with_name(f"{monster}.stats.json")
    if stats_file.exists():
        overrides = json.loads(stats_file.read_text(encoding="utf-8"))
        for key, value in overrides.items():
            if key not in enemy.info_stat_data:
                print(f"[error] Unknown stat '{key}' (valid: {', '.join(enemy.info_stat_data)})", file=sys.stderr)
                return 1
            enemy.info_stat_data[key] = value
            print(f"[info] stat override: {key} = {value}")
    deployed.parent.mkdir(parents=True, exist_ok=True)
    enemy.write_data_to_file(game_data, str(deployed))
    print(f"[ok] {md_source.name} compiled and deployed to {deployed}")
    if game_running():
        print("[info] Game is running — .dat hot-swaps: just re-enter a battle with this monster.")
    else:
        print("[info] Game not running — use 'launch' to start it.")
    return 0


def cmd_restore(cfg: dict, monster: str) -> int:
    base_dat, _, deployed = _paths(cfg, monster)
    shutil.copyfile(base_dat, deployed)
    print(f"[ok] Vanilla {monster}.dat restored to {deployed}")
    return 0


def cmd_launch(cfg: dict) -> int:
    if game_running():
        print("[info] FF8_EN.exe already running.")
        return 0
    j8 = cfg["j8_exe"]
    subprocess.Popen([j8, "/MINI", "/LAUNCH"], cwd=str(pathlib.Path(j8).parent))
    print("[ok] Junction VIII launching the game (/MINI /LAUNCH)...")
    return 0


def cmd_status(cfg: dict) -> int:
    print(f"Game running   : {game_running()}")
    mod_dir = pathlib.Path(cfg["j8_mod_battle_dir"])
    dats = sorted(mod_dir.glob("c[0-9]m[0-9][0-9][0-9].dat"))
    print(f"Mod battle dir : {mod_dir} ({len(dats)} monster .dat deployed)")
    for d in dats:
        print(f"  - {d.name}")
    md_dir = pathlib.Path(cfg["md_workdir"])
    mds = sorted(md_dir.glob("*.md")) if md_dir.exists() else []
    print(f"md workdir     : {md_dir} ({len(mds)} md files)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ff8lab", description="FF8 live AI test pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "deploy", "restore"):
        p = sub.add_parser(name)
        p.add_argument("monster", help="Monster file name, e.g. c0m028")
    sub.add_parser("launch")
    sub.add_parser("status")
    args = parser.parse_args()

    cfg = load_config()
    if args.command == "seed":
        return cmd_seed(cfg, args.monster)
    if args.command == "deploy":
        return cmd_deploy(cfg, args.monster)
    if args.command == "restore":
        return cmd_restore(cfg, args.monster)
    if args.command == "launch":
        return cmd_launch(cfg)
    if args.command == "status":
        return cmd_status(cfg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
