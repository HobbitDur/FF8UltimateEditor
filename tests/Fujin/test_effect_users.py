"""Fujin's "Used by": the spells, items, GFs, enemy attacks and limit breaks of a kernel.bin that
play each effect (their Attack animation field), shown in the Overview, the effect list's tooltip
and its search."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication

KERNEL = "extracted_files/main/kernel.bin"
CURE, LIFE, DISEASE_BREATH, RUBY_LIGHT = 1, 35, 231, 278


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data(KERNEL)
def test_kernel_entries_name_the_effects_they_play():
    from FF8GameData.gamedata import GameData
    from Fujin.effectusers import read_effect_users
    users = read_effect_users(GameData("FF8GameData"), KERNEL)
    labels = lambda effect: [(user.kind, user.entry_id, user.name) for user in users.get(effect, [])]
    assert ("Magic", 21, "Cure") in labels(CURE) and ("Battle item", 31, "Phoenix Pinion") in labels(CURE)
    assert labels(LIFE) == [("Magic", 24, "Life")]
    assert labels(DISEASE_BREATH) == [("Enemy attack", 65, "Disease Breath")]
    assert labels(RUBY_LIGHT) == [("GF", 6, "Ruby Light")]
    magic = [user.entry_id for effect_users in users.values() for user in effect_users if user.kind == "Magic"]
    assert not set(range(64, 96)) & set(magic)          # the ids kept for the GF summons are skipped


@pytest.mark.ff8data(KERNEL)
def test_overview_tooltip_and_search_show_the_users(qapp):
    from Fujin.fujinwidget import FujinWidget
    fujin = FujinWidget()
    fujin.select_effect(CURE)
    assert "Open kernel.bin" in fujin.overview.toPlainText()
    assert any("kernel.bin" in label for label, _callback in fujin.complementary_entries())
    assert fujin.kernel_binding in fujin.file_bindings() and fujin.kernel_binding.read_only

    fujin.file_registry.open_file("kernel.bin", KERNEL)      # shared: opened in SolomonRing works too
    text = fujin.overview.toPlainText()
    assert "Used by" in text and "Phoenix Pinion" in text and "Open kernel.bin" not in text
    item = fujin.effect_list.currentItem()
    assert "Used by: Cure (Magic 21)" in item.toolTip() and item.toolTip().startswith("001")

    fujin.effect_search.search_field.setText("phoenix pinion")    # found by a user, not its name
    visible = [fujin.effect_list.item(row).data(256) for row in range(fujin.effect_list.count())
               if not fujin.effect_list.item(row).isHidden()]
    assert CURE in visible and LIFE not in visible
    fujin.effect_search.clear_search()

    fujin.file_registry.close_file("kernel.bin")
    assert not fujin.users(CURE) and "Open kernel.bin" in fujin.overview.toPlainText()
