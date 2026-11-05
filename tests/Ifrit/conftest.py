import pathlib
import sys

# Make the project root importable (Ifrit, FF8GameData) whatever the pytest invocation
project_root = pathlib.Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


import pytest


@pytest.fixture(autouse=True)
def _propagate_rotation_default():
    """"Apply to all following frames" is remembered (ifrit/3d/propagate_rotation): one test unticking it
    would leave it off for every later test of its worker - each starts from the coded default (ON)."""
    from PyQt6.QtCore import QSettings
    QSettings("FF8UltimateEditor", "FF8UltimateEditor").remove("ifrit/3d/propagate_rotation")
    yield
