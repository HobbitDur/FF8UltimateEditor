"""Effect-centric resource discovery with explicit provenance.

A filename family is a discovery hint, never proof that the effect loads that file.
Native dispatch, cinematic interpreter profiles and data location are independent facts.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER


@dataclass(frozen=True)
class EffectResource:
    key: str
    name: str
    source: str
    evidence: str
    kind: str = "file"
    note: str = ""
    address: int = 0
    size: int = 0


def filename_effect(name):
    match = re.fullmatch(r"mag(\d{3})(?:[_.-].*)?", Path(name).name, re.IGNORECASE)
    return int(match[1]) + 1 if match else None


class EffectCatalog:
    def __init__(self, resource_folder=None):
        folder = Path(resource_folder or RESOURCES_JSON_FOLDER)
        self.names = {e["id"]: e["name"] for e in json.loads(
            (folder / "attack_animation.json").read_text(encoding="utf-8"))["attack_animation"]}
        self.dump = json.loads((folder / "magic_effect.json").read_text(encoding="utf-8"))
        self.research = json.loads((folder / "effect_native_research.json").read_text(encoding="utf-8"))["effects"]
        self.camera = json.loads((folder / "effect_camera.json").read_text(encoding="utf-8"))
        self.profiles = json.loads((folder / "mag_cinematic_profiles.json").read_text(encoding="utf-8"))["effects"]
        self.native = json.loads((folder / "effect_resources.json").read_text(encoding="utf-8"))
        self.facts = json.loads((folder / "effect_runtime.json").read_text(encoding="utf-8"))["effects"]
        self.files = json.loads((folder / "mag_file_catalog.json").read_text(encoding="utf-8"))["files"]

    def effect_ids(self):
        return sorted({int(k) for k in self.dump} | {i for i in self.names if i > 0})

    def name(self, effect):
        return self.names.get(effect, "Free slot" if self.info(effect).get("free") else "Unidentified effect")

    def info(self, effect):
        return self.dump.get(str(effect), {})

    def functions(self, effect):
        return self.info(effect).get("functions", []) + self.research.get(str(effect), [])

    def runtime(self, effect):
        if str(effect) in self.profiles:
            return "MAG cinematic interpreter"
        return self.facts.get(str(effect), {}).get("runtime", "Native effect code")

    def notes(self, effect):
        return self.facts.get(str(effect), {}).get("note", "")

    def camera_entry(self, effect):
        return next((t for t in self.camera["tracks"] if t["effect_id"] == effect), None)

    def aliases(self, effect):
        address = self.info(effect).get("logic_addr")
        return [int(k) for k, v in self.dump.items() if int(k) != effect and address
                and v.get("logic_addr") == address and not v.get("free")]

    def resources(self, effect, extra_names=()):
        result = {}
        # String extraction is partial and can contain unrelated constants (e.g. "V").
        # Keep only resource-like filenames; an empty loader is not an unused slot.
        for name in self.info(effect).get("files_loaded", []):
            if re.fullmatch(r"[\w.-]+\.[\w]+", name):
                result[name.lower()] = EffectResource(name.lower(), name, "File", "Loader reference")
        for entry in self.facts.get(str(effect), {}).get("files", []):
            name = entry["name"]
            result[name.lower()] = EffectResource(name.lower(), name, "File", "Verified runtime resource",
                                                  entry.get("kind", "file"), entry.get("note", ""))
        for name in sorted(set(self.files) | set(extra_names), key=str.lower):
            if filename_effect(name) == effect and name.lower() not in result:
                result[name.lower()] = EffectResource(name.lower(), name, "File", "Filename family only",
                                                      note="Association is a discovery hint; loading by this effect is not proven.")
        for entry in self.native["resources"]:
            if effect in entry["effect_ids"]:
                result[entry["id"]] = EffectResource(entry["id"], entry.get("label", entry["id"]), "Executable",
                    "IDA resource binding / validated bytes", entry["kind"],
                    entry.get("note", "English 2013 Steam data; exported as Hext. Separate copies remain independent."),
                    int(entry["address"], 16), entry["size"])
        return list(result.values())
