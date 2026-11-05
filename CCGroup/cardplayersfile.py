"""
The card players file (*.cardplayers.json): every NPC card player of the opened field folders in one
readable file - to keep (it diffs well in git), to share, or to apply onto another field folder
(another mod's, or a fresh copy) so the same card setup is made there.

    {"format": "FF8UltimateEditor CCGroup card players", "version": 1,
     "players": [{"map": "mapdata/bg/bghall_1", "entity": "seito6", "script": "talk", "index": 0,
                  "deck_id": 31, "game_rules": {"var": 292, "push": "PSHM_B"}, ..., "level_mask": 7,
                  "clock": [0, 0], "variant_literals": [],
                  "texts": [{"role": "Question", "text": "..."}, ...],
                  "changed": true,
                  "added": {"region": 0, "on_no": "nothing"}}]}

A player is found again by its map folder, entity, script and its position among that script's
CARDGAME calls ("index"). Each of the 7 values is a literal (a number), a savemap variable
({"var", "push"}) or anything else ({"opcode", "value"}: kept as the target has it). With the vanilla
reference open, "changed" says whether the player differs from vanilla, and "added" marks a card game
the vanilla NPC does not have: applying the file gives that NPC the card game first.
"""
import json
import os

from CCGroup import jsmnpc
from CCGroup.jsmcardgame import (JsmCardGameFile, NB_CARDGAME_PARAMS, OPCODE_PSHM_B, OPCODE_PSHM_W, OPCODE_PSHM_L,
                                 OPCODE_PSHSM_B, OPCODE_PSHSM_W, OPCODE_PSHSM_L, PARAM_DECK_ID, PARAM_GAME_RULES)

FORMAT_NAME = "FF8UltimateEditor CCGroup card players"
FORMAT_VERSION = 1
FILE_FILTER = "Card players (*.cardplayers.json);;JSON (*.json)"
PARAM_KEYS = ["deck_id", "game_rules", "trade_rules", "rare_chance", "ai_search", "ai_strategy", "level_mask"]
PUSH_NAMES = {OPCODE_PSHM_B: "PSHM_B", OPCODE_PSHM_W: "PSHM_W", OPCODE_PSHM_L: "PSHM_L",
              OPCODE_PSHSM_B: "PSHSM_B", OPCODE_PSHSM_W: "PSHSM_W", OPCODE_PSHSM_L: "PSHSM_L"}
PUSH_OPCODES = {name: opcode for opcode, name in PUSH_NAMES.items()}
COMPARED_KEYS = PARAM_KEYS + ["clock", "variant_literals", "texts"]


def map_key(jsm_file):
    """'mapdata/bg/bghall_1': the map folder, relative to the field folder, the same in every one."""
    return os.path.dirname(jsm_file.rel_path).replace(os.sep, "/")


def player_index(jsm_file, player):
    """Position of the player among the CARDGAME calls of its entity's script."""
    same = [other for other in jsm_file.players
            if (other.entity_name, other.script_name) == (player.entity_name, player.script_name)]
    return same.index(player)


def _param_value(param):
    if param.is_literal():
        return param.value
    if param.is_variable():
        return {"var": param.value, "push": PUSH_NAMES[param.opcode]}
    return {"opcode": param.opcode, "value": param.value}


def player_record(jsm_file, player, msd_file):
    """The file's entry of one card player (its current, possibly unsaved, values)."""
    record = {"map": map_key(jsm_file), "entity": player.entity_name, "script": player.script_name,
              "index": player_index(jsm_file, player)}
    for key, param in zip(PARAM_KEYS, player.params):
        record[key] = _param_value(param)
    record["clock"] = list(player.clock())
    record["variant_literals"] = [literal.value for literal in player.variant.literals()] if player.variant else []
    texts = []
    if msd_file is not None:
        for use in jsmnpc.player_messages(jsm_file, player):
            if 0 <= use.message_id < len(msd_file):
                texts.append({"role": use.role, "text": msd_file.text(use.message_id)})
    record["texts"] = texts
    return record


def _added_card_game(jsm_file, player):
    """How the card game was given to the NPC (jsmnpc.add_card_game's region and 'on no' choice),
    read back from the code it appended."""
    rules = player.params[PARAM_GAME_RULES]
    if rules.opcode == OPCODE_PSHM_B and jsmnpc.VAR_REGION_RULES <= rules.value < jsmnpc.VAR_REGION_RULES + 8:
        region = rules.value - jsmnpc.VAR_REGION_RULES
    else:  # rules copied from the map's cardgamemaster: the region it calls
        calls = jsmnpc.card_master_calls(jsm_file)
        region = jsmnpc.REGIONS.index(calls["region"]) if calls and calls["region"] in jsmnpc.REGIONS else 0
    cardgame_index = (player.cardgame_file_offset - jsm_file.offset_script) // 4
    _start, end = jsmnpc.script_bounds(jsm_file, cardgame_index)
    last_opcode = jsm_file.instructions()[end - 1][0]
    on_no = jsmnpc.ON_NO_ORIGINAL if last_opcode == jsmnpc.OPCODE_JMP else jsmnpc.ON_NO_NOTHING
    return {"region": region, "on_no": on_no}


class _Vanilla:
    """The vanilla reference's version of the maps, read on demand to compare with."""

    def __init__(self, manager):
        self.manager = manager
        self.files = {}

    def file(self, jsm_file):
        if not jsm_file.vanilla_path:
            return None, None
        if jsm_file.vanilla_path not in self.files:
            vanilla = JsmCardGameFile(jsm_file.vanilla_path, os.path.splitext(jsm_file.vanilla_path)[0] + ".sym")
            vanilla.rel_path = jsm_file.rel_path
            msd_file = None
            msd_path = os.path.join(os.path.dirname(jsm_file.vanilla_path), jsm_file.map_name + ".msd")
            if self.manager.game_data is not None and os.path.isfile(msd_path):
                from FF8GameData.field.msdfile import MsdFile
                with open(msd_path, "rb") as msd_data:
                    msd_file = MsdFile(msd_data.read(), self.manager.game_data)
            self.files[jsm_file.vanilla_path] = (vanilla, msd_file)
        return self.files[jsm_file.vanilla_path]


def export_players(manager, compare_with_vanilla: bool):
    """The file content for every card player of the manager's maps. compare_with_vanilla (the
    vanilla reference is open under the edited folder): flag each player changed / added."""
    vanilla = _Vanilla(manager) if compare_with_vanilla else None
    players = []
    for jsm_file in manager.jsm_files:
        msd_file = manager.msd(jsm_file)
        vanilla_records = {}
        vanilla_entities = set()
        if vanilla is not None:
            vanilla_file, vanilla_msd = vanilla.file(jsm_file)
            if vanilla_file is not None:
                for vanilla_player in vanilla_file.players:
                    record = player_record(vanilla_file, vanilla_player, vanilla_msd)
                    vanilla_records[(record["entity"], record["script"], record["index"])] = record
                    vanilla_entities.add(vanilla_player.entity_name)
        for player in jsm_file.players:
            record = player_record(jsm_file, player, msd_file)
            if vanilla is not None:
                original = vanilla_records.get((record["entity"], record["script"], record["index"]))
                record["changed"] = original is None or any(record[key] != original[key] for key in COMPARED_KEYS)
                if player.entity_name not in vanilla_entities:
                    record["added"] = _added_card_game(jsm_file, player)
            players.append(record)
    return {"format": FORMAT_NAME, "version": FORMAT_VERSION, "players": players}


def write_file(path, content):
    text = json.dumps(content, indent=1, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as out:
        out.write(text)


def read_file(path):
    """The file content, checked to be a card players file (ValueError otherwise)."""
    with open(path, encoding="utf-8") as source:
        try:
            content = json.load(source)
        except json.JSONDecodeError as error:
            raise ValueError(f"Not a JSON file: {error}") from None
    if not isinstance(content, dict) or content.get("format") != FORMAT_NAME:
        raise ValueError("Not a CCGroup card players file (exported with Export card players).")
    if content.get("version", 0) > FORMAT_VERSION:
        raise ValueError(f"Made by a newer version of the editor (file version {content['version']}): update it.")
    return content


class ApplyReport:
    def __init__(self):
        self.changed = []    # "<map> <entity>" of the players whose values the file changed
        self.added = []      # card games given to an NPC
        self.unchanged = 0   # players already as the file has them
        self.not_found = []  # "<map> <entity>: why"
        self.problems = []   # parts of a player that could not be applied


def _find_player(jsm_file, record):
    same = [player for player in jsm_file.players
            if (player.entity_name, player.script_name) == (record["entity"], record["script"])]
    index = record.get("index", 0)
    return same[index] if index < len(same) else None


def _apply_param(param, value):
    if isinstance(value, int):
        if not param.is_editable():
            return f"{param.name} is not a literal nor a variable here: kept"
        param.set_literal(value)
    elif isinstance(value, dict) and "var" in value:
        if not param.is_editable():
            return f"{param.name} is not a literal nor a variable here: kept"
        param.set_variable(value["var"], PUSH_OPCODES.get(value.get("push"), OPCODE_PSHM_B))
    elif isinstance(value, dict) and (param.opcode, param.value) != (value.get("opcode"), value.get("value")):
        return f"{param.name} is computed at runtime in the file: kept as it is here"
    return ""


def _apply_texts(jsm_file, player, msd_file, texts, problems, label):
    """Set the script's texts in order; False when nothing could be compared."""
    if not texts:
        return False
    if msd_file is None:
        problems.append(f"{label}: no {jsm_file.map_name}.msd, texts not applied")
        return False
    uses = [use for use in jsmnpc.player_messages(jsm_file, player) if 0 <= use.message_id < len(msd_file)]
    if [use.role for use in uses] != [text["role"] for text in texts]:
        problems.append(f"{label}: its script shows other texts than in the file ({len(uses)} vs {len(texts)}),"
                        f" texts not applied")
        return False
    changed = False
    for use, text in zip(uses, texts):
        if msd_file.text(use.message_id) == text["text"]:
            continue
        if msd_file.encode(msd_file.text(use.message_id)) != msd_file.messages[use.message_id]:
            problems.append(f"{label}: message {use.message_id} holds codes this tool cannot re-encode, kept")
            continue
        msd_file.set_text(use.message_id, text["text"])
        changed = True
    return changed


def apply_players(manager, content):
    """Apply a card players file onto the manager's maps (as unsaved edits). Returns an ApplyReport."""
    report = ApplyReport()
    maps = {map_key(jsm_file): jsm_file for jsm_file in manager.all_files or manager.jsm_files}
    for record in content.get("players", []):
        label = f"{record.get('map', '?').split('/')[-1]} {record.get('entity', '?')}"
        jsm_file = maps.get(record.get("map"))
        if jsm_file is None:
            report.not_found.append(f"{label}: no such map in the opened folders")
            continue
        player = _find_player(jsm_file, record)
        if player is None and "added" in record:
            player = _add_card_game(manager, jsm_file, record, report, label)
            if player is None:
                continue
        elif player is None:
            report.not_found.append(f"{label}: no card game in {record.get('script')} here")
            continue
        before = player_record(jsm_file, player, manager.msd(jsm_file))
        for key, param in zip(PARAM_KEYS, player.params):
            if key in record:
                problem = _apply_param(param, record[key])
                if problem:
                    report.problems.append(f"{label}: {problem}")
        if "clock" in record:
            player.set_clock(*record["clock"])
        literals = player.variant.literals() if player.variant else []
        wanted = record.get("variant_literals", [])
        if len(literals) == len(wanted):
            for literal, value in zip(literals, wanted):
                literal.value = value
        else:
            report.problems.append(f"{label}: its variant has other conditions than in the file, kept")
        _apply_texts(jsm_file, player, manager.msd(jsm_file), record.get("texts", []), report.problems, label)
        if label in report.added:
            continue
        if player_record(jsm_file, player, manager.msd(jsm_file)) != before:
            report.changed.append(label)
        else:
            report.unchanged += 1
    return report


def _add_card_game(manager, jsm_file, record, report, label):
    """Give the NPC the card game the file says was added (then filled like any player)."""
    npc = next((npc for npc in manager.npcs(jsm_file) if npc.entity_name == record["entity"]), None)
    if npc is None:
        report.not_found.append(f"{label}: no such NPC in this map")
        return None
    texts = {text["role"]: text["text"] for text in record.get("texts", [])}
    added = record["added"]
    deck_id = record.get("deck_id") if isinstance(record.get("deck_id"), int) else None
    try:
        player = manager.add_card_game(jsm_file, npc, texts.get(jsmnpc.ROLE_QUESTION, jsmnpc.DEFAULT_QUESTION),
                                       texts.get(jsmnpc.ROLE_NOT_ENOUGH, jsmnpc.DEFAULT_NOT_ENOUGH_CARDS),
                                       added.get("region", 0), added.get("on_no", jsmnpc.ON_NO_NOTHING), deck_id)
    except (ValueError, OSError) as error:
        report.not_found.append(f"{label}: the card game could not be added ({error})")
        return None
    report.added.append(label)
    return player


assert len(PARAM_KEYS) == NB_CARDGAME_PARAMS and PARAM_KEYS[PARAM_DECK_ID] == "deck_id"
