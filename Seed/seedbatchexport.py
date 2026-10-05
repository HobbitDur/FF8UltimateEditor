import pathlib
from typing import Callable, List, Optional, Tuple

from Ifrit.Ifrit3D.gltfexporter import GltfExporter
from Seed.seedmanager import SeedManager


def export_fields_to_gltf(chara_one_paths: List[pathlib.Path], out_dir, main_chr_folder=None,
                          live_manager: Optional[SeedManager] = None,
                          progress: Callable[[int, str], bool] = None) -> Tuple[List[pathlib.Path], List[str]]:
    """Export every model of every given chara.one to <out_dir>/<field>/<index>_<name>.glb.

    live_manager: the tool's manager - for its open chara.one, the models it already built are
    exported as they are now (unsaved edits included) instead of being re-read from the file.
    progress(field_index, field_name) is called before each field; returning False cancels.
    Returns (written files, failure messages)."""
    out_dir = pathlib.Path(out_dir)
    written, failures = [], []
    live_path = live_manager.chara_one_path.resolve() \
        if live_manager is not None and live_manager.chara_one_path is not None else None
    for field_index, path in enumerate(chara_one_paths):
        path = pathlib.Path(path)
        field = path.parent.name
        if progress is not None and progress(field_index, field) is False:
            break
        manager = SeedManager()
        manager.main_chr_folder = pathlib.Path(main_chr_folder) if main_chr_folder else None
        try:
            manager.load_chara_one(path)
        except Exception as error:
            failures.append(f"{field}: {error}")
            continue
        if live_path is not None and path.resolve() == live_path:
            manager.models = dict(live_manager.models)
        field_dir = out_dir / field
        for index, entry in enumerate(manager.chara_one.entries):
            try:
                manager.load_entry(index)
                if not manager.enemy.geometry_data.object_data:
                    continue
                field_dir.mkdir(parents=True, exist_ok=True)
                file_path = field_dir / f"{index:02d}_{entry.name}.glb"
                GltfExporter(manager).export(str(file_path))
                written.append(file_path)
            except Exception as error:
                failures.append(f"{field} model {index} ({entry.name}): {error}")
    return written, failures
