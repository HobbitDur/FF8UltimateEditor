"""
Tests for Hyne (.ff8 Steam save-file editor).

Unlike Quezacotl (init.out), no real .ff8 save file ships with the repo — saves are
player-specific and live outside it — so these tests build a synthetic, CRC-correct
8192-byte savemap image (all zero game state) and wrap it in the real LZSS envelope,
exercising the exact same load/save path a real save file goes through: LZSS decompress,
CRC self-check, entry parsing (reused from Quezacotl), edit, CRC recompute, LZSS recompress,
backup-before-write.
"""
import pathlib
import struct

import pytest

from FF8GameData.gamedata import GameData
from Hyne.hynemanager import (
    HyneManager, IMAGE_SIZE, HEADER_SIZE, GAMESTATE_BASE,
    CRC_OFFSET_1, CRC_OFFSET_2, CRC_SPAN_START, CRC_SPAN_LEN,
    crc16_ff8, lzss_decompress, lzss_compress_all_literal, lzss_compress,
    metadata_signature, update_metadata_for_save,
)
from Quezacotl.quezacotlmanager import (
    NB_GF, NB_CHARACTERS, NB_ITEMS, CHARACTER_DATA_OFFSET, CHARACTER_ENTRY_SIZE,
    GF_COMPATIBILITY_MIN,
)


@pytest.fixture(scope="module")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent.parent
    return GameData(str(project_root / "FF8GameData"))


@pytest.fixture
def manager(game_data):
    return HyneManager(game_data)


def _valid_image():
    """A CRC-correct 8192-byte savemap image.

    Filled with a deterministic non-zero byte pattern rather than all zeros: this buggy CRC
    (see crc16_ff8's docstring) has a degenerate property where table[0] == 0, so once the
    running CRC happens to hit 0 mid-stream, any further run of zero bytes leaves it at 0
    forever — an all-zero buffer is a worst-case input for testing checksum *sensitivity*
    (it would make single-byte corruption near the start invisible to the checksum). Real
    save data is never this degenerate, but the test fixture must not be either.
    """
    image = bytearray((i * 167 + 41) & 0xFF for i in range(IMAGE_SIZE))
    crc = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
    struct.pack_into("<H", image, CRC_OFFSET_1, crc)
    struct.pack_into("<H", image, CRC_OFFSET_2, crc)
    return bytes(image)


def _write_ff8(path, image: bytes):
    compressed = lzss_compress_all_literal(image)
    with open(path, "wb") as f:
        f.write(struct.pack("<I", len(compressed)))
        f.write(compressed)


@pytest.fixture
def save_path(tmp_path):
    """A valid, freshly-written .ff8 file (all-literal LZSS, correct CRC)."""
    path = tmp_path / "slot1_save01.ff8"
    _write_ff8(path, _valid_image())
    return path


class TestLzss:
    def test_all_literal_roundtrip(self):
        data = bytes(range(256)) * 40  # 10240 bytes, non-trivial content
        compressed = lzss_compress_all_literal(data)
        assert lzss_decompress(compressed) == data

    def test_flag_byte_marks_every_token_literal(self):
        # 3 bytes -> one flag byte (bits 0-2 set) + 3 literal bytes
        compressed = lzss_compress_all_literal(b"\xAA\xBB\xCC")
        assert compressed[0] == 0b0000_0111
        assert compressed[1:] == b"\xAA\xBB\xCC"

    def test_real_compress_roundtrip(self):
        """lzss_compress (the back-reference encoder) must decompress to exactly its input -
        this is the ONE thing that must never regress, since save_file() trusts it blindly for
        anything that ends up on disk."""
        data = _valid_image()
        compressed = lzss_compress(data)
        assert lzss_decompress(compressed) == data

    def test_real_compress_stays_under_one_block(self):
        """Regression guard for the bug that broke a real save file: Save_EmuMC_CreateFile@
        0x4c4fa0 allots exactly one 8192-byte memory-card block per save; a compressed size at
        or over that silently claims a second block and the game deletes the file as "unused
        block". The all-literal encoder inflates an 8192-byte image to ~9216 bytes - ALWAYS over
        the limit; the real encoder must always land comfortably under it, even for save data
        that isn't especially repetitive."""
        compressed = lzss_compress(_valid_image())
        assert len(compressed) + 4 < IMAGE_SIZE
        # the bug this guards against, for contrast:
        assert len(lzss_compress_all_literal(_valid_image())) + 4 >= IMAGE_SIZE

    def test_distance_4096_is_never_emitted(self):
        """A back-reference distance of exactly 4096 aliases to 0 via the format's mod-4096
        ring-buffer arithmetic (raw12 = (i - dist + 0xFEE) & 0xFFF) and would corrupt the
        decompressed output. The encoder's search window must stop at 4095."""
        # A run long enough that the ideal (but unusable) match would sit exactly 4096 back.
        data = bytes([7]) + bytes(4095) + bytes([7]) + bytes(50)
        compressed = lzss_compress(data)
        assert lzss_decompress(compressed) == data


class TestCrc:
    def test_table_255_is_never_written_bug_is_preserved(self):
        """Regression guard for the ported off-by-one bug: the original EXE's table-build
        loop is a do-while checked AFTER incrementing, so it only ever fills indices 0..254 —
        table[255] stays 0 from the initial memset. A textbook CRC-16/CCITT-FALSE table would
        NOT have this gap, and using one silently breaks every checksum this tool writes."""
        from Hyne.hynemanager import _CRC_TABLE
        assert _CRC_TABLE[255] == 0
        assert _CRC_TABLE[254] != 0  # sanity: the gap is specific to index 255, not a broader bug

    def test_deterministic_and_sensitive_to_input(self):
        span = bytes((i * 167 + 41) & 0xFF for i in range(CRC_SPAN_LEN))
        corrupted = bytearray(span)
        corrupted[0] ^= 0xFF
        assert crc16_ff8(span) == crc16_ff8(span)
        assert crc16_ff8(span) != crc16_ff8(bytes(corrupted))

    def test_detects_corruption(self):
        image = bytearray(_valid_image())
        image[CRC_SPAN_START] ^= 0xFF  # corrupt one byte inside the checksummed span
        stored = struct.unpack_from("<H", image, CRC_OFFSET_1)[0]
        recomputed = crc16_ff8(bytes(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN]))
        assert stored != recomputed


class TestLoad:
    def test_rejects_bad_crc(self, manager, tmp_path):
        image = bytearray(_valid_image())
        image[CRC_SPAN_START] ^= 0xFF  # corrupt checksummed data without fixing the stored CRC
        path = tmp_path / "corrupt.ff8"
        _write_ff8(path, bytes(image))
        with pytest.raises(ValueError, match="checksum"):
            manager.load_file(str(path))

    def test_rejects_wrong_decompressed_size(self, manager, tmp_path):
        payload = lzss_compress_all_literal(bytes(100))  # decompresses to far less than 8192
        path = tmp_path / "tooshort.ff8"
        with open(path, "wb") as f:
            f.write(struct.pack("<I", len(payload)))
            f.write(payload)
        with pytest.raises(ValueError, match="8192"):
            manager.load_file(str(path))

    def test_parses_all_entry_tables(self, manager, save_path):
        manager.load_file(str(save_path))
        assert len(manager.gf_entries) == NB_GF
        assert len(manager.character_entries) == NB_CHARACTERS
        assert len(manager.item_entries) == NB_ITEMS
        assert manager.config is not None
        assert manager.misc is not None

    def test_gf_names_from_gforce_json(self, manager, save_path):
        manager.load_file(str(save_path))
        assert manager.gf_entries[0].gf_name == "Quezacotl"

    def test_character_offset_matches_documented_worked_example(self, manager, save_path):
        """Zell (char index 1) magic slot 0 must sit at absolute image offset 1720 — the exact
        offset independently derived via IDA in this format's original RE session."""
        manager.load_file(str(save_path))
        zell = manager.character_entries[1]
        expected_offset = GAMESTATE_BASE + CHARACTER_DATA_OFFSET + 1 * CHARACTER_ENTRY_SIZE + 16
        assert expected_offset == 1720
        zell.magics[0].magic_id = 80
        assert manager.buffer[expected_offset] == 80


class TestSaveRoundtrip:
    def test_save_without_modification_is_crc_stable(self, manager, save_path, tmp_path):
        manager.load_file(str(save_path))
        out = tmp_path / "out.ff8"
        manager.save_file(str(out), backup=False)

        raw = out.read_bytes()
        comp_size = struct.unpack_from("<I", raw, 0)[0]
        image = lzss_decompress(raw[4:4 + comp_size])
        assert len(image) == IMAGE_SIZE
        stored = struct.unpack_from("<H", image, CRC_OFFSET_1)[0]
        assert stored == struct.unpack_from("<H", image, CRC_OFFSET_2)[0]
        assert stored == crc16_ff8(image[CRC_SPAN_START:CRC_SPAN_START + CRC_SPAN_LEN])

    def test_save_defaults_to_loaded_path(self, manager, save_path):
        manager.load_file(str(save_path))
        manager.item_entries[0].item_id = 5
        manager.save_file(backup=False)

        reloaded = HyneManager(manager.game_data)
        reloaded.load_file(str(save_path))
        assert reloaded.item_entries[0].item_id == 5

    def test_save_creates_backup_by_default(self, manager, save_path):
        original_bytes = save_path.read_bytes()
        manager.load_file(str(save_path))
        manager.save_file()  # backup=True by default

        backup_path = save_path.with_suffix(save_path.suffix + ".bak")
        assert backup_path.exists()
        assert backup_path.read_bytes() == original_bytes

    def test_edit_reload_roundtrip(self, manager, save_path):
        manager.load_file(str(save_path))
        zell = manager.character_entries[1]
        zell.magics[0].magic_id = 80
        zell.magics[0].quantity = 9
        manager.config.volume = 42
        manager.misc.gil = 123456
        manager.save_file(backup=False)

        reloaded = HyneManager(manager.game_data)
        reloaded.load_file(str(save_path))
        assert reloaded.character_entries[1].magics[0].magic_id == 80
        assert reloaded.character_entries[1].magics[0].quantity == 9
        assert reloaded.config.volume == 42
        assert reloaded.misc.gil == 123456

    def test_only_intended_bytes_plus_crc_change(self, manager, save_path):
        """Mirrors the original RE proof-of-concept: a single-field edit should only ever
        touch that field's byte(s) plus the two CRC copies — everything else must be
        byte-for-byte preserved."""
        manager.load_file(str(save_path))
        raw_before = save_path.read_bytes()
        comp_size_before = struct.unpack_from("<I", raw_before, 0)[0]
        before = lzss_decompress(raw_before[4:4 + comp_size_before])
        zell = manager.character_entries[1]
        target_offset = GAMESTATE_BASE + CHARACTER_DATA_OFFSET + 1 * CHARACTER_ENTRY_SIZE + 16
        zell.magics[0].magic_id = 80
        manager.save_file(backup=False)

        raw = save_path.read_bytes()
        comp_size = struct.unpack_from("<I", raw, 0)[0]
        after = lzss_decompress(raw[4:4 + comp_size])

        diffs = {i for i in range(IMAGE_SIZE) if before[i] != after[i]}
        expected = {target_offset, CRC_OFFSET_1, CRC_OFFSET_1 + 1, CRC_OFFSET_2, CRC_OFFSET_2 + 1}
        assert diffs == expected


class TestGfCharacterItemEntry:
    def test_gf_ability_bitfield_roundtrip(self, manager, save_path):
        manager.load_file(str(save_path))
        gf = manager.gf_entries[0]
        ability_11_before = gf.has_ability(11)  # a different ability in the same byte
        gf.set_ability(10, True)
        manager.save_file(backup=False)

        reloaded = HyneManager(manager.game_data)
        reloaded.load_file(str(save_path))
        assert reloaded.gf_entries[0].has_ability(10) is True
        assert reloaded.gf_entries[0].has_ability(11) is ability_11_before

    def test_character_gf_compatibility_roundtrip(self, manager, save_path):
        manager.load_file(str(save_path))
        squall = manager.character_entries[0]
        assert squall.name == "Squall"
        squall.set_gf_compatibility(0, GF_COMPATIBILITY_MIN + 500)
        manager.save_file(backup=False)

        reloaded = HyneManager(manager.game_data)
        reloaded.load_file(str(save_path))
        assert reloaded.character_entries[0].get_gf_compatibility(0) == GF_COMPATIBILITY_MIN + 500

    def test_item_roundtrip_and_name(self, manager, save_path):
        manager.load_file(str(save_path))
        manager.item_entries[0].item_id = 1  # Potion
        manager.item_entries[0].quantity = 50
        assert manager.item_entries[0].name == "Potion"
        manager.save_file(backup=False)

        reloaded = HyneManager(manager.game_data)
        reloaded.load_file(str(save_path))
        assert reloaded.item_entries[0].item_id == 1
        assert reloaded.item_entries[0].quantity == 50


class TestMetadata:
    """Regression coverage for the game's OUT-OF-BAND save validation: something outside
    FF8_EN.exe (Steam Cloud sync and/or the DotEmu EmuMC layer, confirmed via dotemuCreateFileA/
    dotemuDeleteFileA imports from an external AF3DN module this project's IDA database doesn't
    cover) silently reverts a .ff8 file whose content doesn't match metadata.xml's recorded
    per-slot MD5 signature — discovered after two internally-verified (correct LZSS, correct CRC,
    under the 8192-byte block limit) saves were reverted anyway. metadata_signature() reproduces
    Hyne.exe's own Metadata::md5sum (src/Metadata.cpp, myst6re/hyne on GitHub) exactly, verified
    against a real save's real metadata.xml entry outside this repo (not reproducible here since
    saves are player-specific)."""

    def test_metadata_signature_is_md5_of_file_bytes_plus_userid(self):
        # Hand-computed reference vector matching Metadata::md5sum's documented formula
        # (md5(lzsData + userID) where lzsData is Hyne's name for the whole on-disk file).
        import hashlib
        file_bytes = b"\x05\x00\x00\x00\xFF\xAA\xBB\xCC\xDD"
        user_id = "12345678"
        expected = hashlib.md5(file_bytes + user_id.encode("latin1")).hexdigest()
        assert metadata_signature(file_bytes, user_id) == expected
        assert len(expected) == 32  # 32 lowercase hex chars, matching every real signature seen

    def test_update_metadata_for_save_rewrites_only_the_matching_entry(self, tmp_path):
        user_dir = tmp_path / "user_12345678"
        user_dir.mkdir()
        metadata_path = user_dir / "metadata.xml"
        metadata_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gamestatus>\n'
            '  <savefile num="1" type="ff8" slot="1">\n'
            '    <timestamp></timestamp>\n'
            '    <signature>00000000000000000000000000000000</signature>\n'
            '  </savefile>\n'
            '  <savefile num="2" type="ff8" slot="1">\n'
            '    <timestamp>1717870448000</timestamp>\n'
            '    <signature>11111111111111111111111111111111</signature>\n'
            '  </savefile>\n'
            '</gamestatus>\n',
            encoding="utf-8",
        )
        save_path = user_dir / "slot1_save01.ff8"
        file_bytes = b"\x05\x00\x00\x00\xFF\xAA\xBB\xCC\xDD"

        update_metadata_for_save(str(save_path), file_bytes)

        new_xml = metadata_path.read_text(encoding="utf-8")
        expected_sig = metadata_signature(file_bytes, "12345678")
        assert expected_sig in new_xml
        assert "<timestamp></timestamp>" not in new_xml  # num=1's entry got a real timestamp
        # num=2's entry (a different slot number) must be untouched
        assert "11111111111111111111111111111111" in new_xml
        assert "1717870448000" in new_xml
        assert pathlib.Path(str(metadata_path) + ".bak").exists()

    def test_update_metadata_for_save_is_noop_without_metadata_xml(self, tmp_path):
        # No metadata.xml alongside the save -> must not raise, must not create one either
        # (matches Hyne's own behavior: a missing metadata.xml is a soft-fail, not a hard error).
        user_dir = tmp_path / "user_12345678"
        user_dir.mkdir()
        save_path = user_dir / "slot1_save01.ff8"
        update_metadata_for_save(str(save_path), b"\x00\x00\x00\x00")
        assert not (user_dir / "metadata.xml").exists()

    def test_save_file_updates_metadata_signature_to_match_new_content(self, manager, save_path, tmp_path):
        """End-to-end: save_file() must leave metadata.xml's signature matching the freshly
        written file's own bytes, exactly like the real Hyne.exe does after every save — this is
        the actual fix for the "unused block" bug, not just a nice-to-have."""
        user_dir = tmp_path / "user_87654321"
        user_dir.mkdir()
        real_save_path = user_dir / "slot1_save01.ff8"
        real_save_path.write_bytes(save_path.read_bytes())
        (user_dir / "metadata.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gamestatus>\n'
            '  <savefile num="1" type="ff8" slot="1">\n'
            '    <timestamp></timestamp>\n'
            '    <signature>00000000000000000000000000000000</signature>\n'
            '  </savefile>\n'
            '</gamestatus>\n',
            encoding="utf-8",
        )

        manager.load_file(str(real_save_path))
        manager.item_entries[0].item_id = 1
        manager.save_file(str(real_save_path), backup=False)

        new_file_bytes = real_save_path.read_bytes()
        new_xml = (user_dir / "metadata.xml").read_text(encoding="utf-8")
        assert metadata_signature(new_file_bytes, "87654321") in new_xml
