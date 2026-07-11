"""Project-wide pytest configuration.

Some tests need original FF8 game files (.jsm, .dat, kernel.bin, ...) that cannot be
committed to the repo for copyright reasons. Those tests are marked with @pytest.mark.ff8data
and are skipped automatically when the files are not present next to this conftest.

Run only those tests locally with:      pytest -m ff8data
The CI excludes them completely with:   pytest -m "not ff8data"
"""
import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "ff8data(*files): test needs original FF8 game files that are not committed "
        "for copyright reasons, skipped when the files are missing from the project root",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("ff8data")
        if marker:
            missing = [file_name for file_name in marker.args if not (PROJECT_ROOT / file_name).exists()]
            if missing:
                item.add_marker(pytest.mark.skip(
                    reason=f"FF8 game files not available (copyright, not in repo): {', '.join(missing)}"))
