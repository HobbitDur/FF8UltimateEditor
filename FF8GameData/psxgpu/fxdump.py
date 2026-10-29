"""A battle-effect recording of the FFNx effect harness (fxaudit_held.exe ... between=FILE vram=1),
read as frames a viewer can draw.

The harness maps FF8_EN.exe, fakes a battle and runs one effect's ORIGINAL code tick by tick (15 per
second); its "between" dump lists, per real tick:

    R t n [ordered]       the original pass of tick t, then its n OT insertions ("ordered": listed in
                          draw order - Tools/fxrecorder walks the PC's render list):
    P f n sub obj lay mdl gfc fn bucket len words...   one GPU packet (words in hex; up to 16); from
                          Tools/fxrecorder, f = the effect part that drew it (a port's FX_PART, 0
                          for none: FFNx fx_params.h)
    C t ex ey ez ax ay az the battle camera after the tick (eye, look-at)
    V t x y w h hexwords  (vram=1) a VRAM upload the tick queued: a w x h rectangle at (x, y)
    B t x y w h u v       (vram=1) a VRAM-to-VRAM copy the tick queued
    Q t part seq frame    (Tools/fxrecorder) a sprite the tick drew: the effect part, its sprite
                          sequence's address (hex) and frame (FF8GameData/psxgpu/spritesequence.py)

Other blocks (H, Z, O: 30 fps held frames; S: spawned tasks) are skipped. The packets are drawn in
reverse insertion order within an OT bucket and buckets from the highest address down, the
order a reversed ordering table is walked; the harness does not record the depth keys of
depth-sorted inserts, so prims sharing a bucket keep that order.
"""
from dataclasses import dataclass, field

from FF8GameData.psxgpu.gpu import Gpu, Vram


@dataclass
class EffectTick:
    index: int
    packets: list = field(default_factory=list)     # [(bucket, insertion order, [words])]
    parts: list = field(default_factory=list)       # the effect part of each packet (0: none)
    camera: tuple = None                            # (eye xyz, look-at xyz)
    uploads: list = field(default_factory=list)     # [("V", x, y, w, h, words) | ("B", x, y, w, h, u, v)]
    ordered: bool = False   # the packets are in draw order already ("R t n ordered": the recorder's walk)
    sprites: list = field(default_factory=list)     # [(part, sequence address, frame)] drawn (Q lines)

    def part_packets(self, parts=None):
        """The packets of these effect parts (all of them for None)."""
        if parts is None:
            return self.packets
        return [packet for packet, part in zip(self.packets, self.parts) if part in parts]

    @property
    def part_ids(self):
        return set(self.parts)


@dataclass
class EffectRecording:
    effect_id: int = None
    ticks: list = field(default_factory=list)
    pre_uploads: list = field(default_factory=list)  # queued before tick 0 (setup, file loads)
    summary: str = ""
    _vram_cache: tuple = field(default=None, repr=False, compare=False)   # (uploads key, Vram) of the last frame

    def fit_view(self, margin=0.08, parts=None):
        """(x, y, width, height) of the screen-plane window holding what the effect draws over all its
        ticks (2nd to 98th percentile of the polygon / sprite points, plus a margin), at least the
        320 x 224 units and at most the game window x 2 (GAME_WINDOW: the effect may be framed by
        a camera that does not show it all). parts: only the packets of these effect parts."""
        import numpy as np
        from FF8GameData.psxgpu.gpu import GAME_WINDOW, SCREEN_H, SCREEN_W, _raw_xy
        points = []
        for tick in self.ticks:
            for _bucket, _order, words in tick.part_packets(parts):
                code = words[0] >> 24 if words else 0
                if 0x20 <= code < 0x40:
                    count, index = (4 if code & 8 else 3), 1
                    for point in range(count):
                        if point and code & 0x10:
                            index += 1
                        if index < len(words):
                            points.append(_raw_xy(words[index]))
                        index += 1 + bool(code & 4)
                elif 0x60 <= code < 0x80 and len(words) > 1:
                    points.append(_raw_xy(words[1]))
        if not points:
            return 0, 0, SCREEN_W, SCREEN_H
        xs, ys = np.array(points).T
        low_x, high_x = np.percentile(xs, (2, 98))
        low_y, high_y = np.percentile(ys, (2, 98))
        width, height = (high_x - low_x) * (1 + 2 * margin), (high_y - low_y) * (1 + 2 * margin)
        width, height = min(max(width, SCREEN_W), 2 * GAME_WINDOW[2]), min(max(height, SCREEN_H), 2 * GAME_WINDOW[3])
        centre_x, centre_y = (low_x + high_x) / 2, (low_y + high_y) / 2
        return int(centre_x - width / 2), int(centre_y - height / 2), int(width), int(height)

    def frame(self, tick_index, vram=None, view=None, scale=1.0, renderer=None, parts=None):
        """The RGB image of tick `tick_index` and the Gpu that drew it (its missing_pages / counts).
        view: (x, y, width, height) of the screen plane to draw, None = the game's window
        (GAME_WINDOW); scale: image pixels per packet unit; renderer: a glrender.PsxGlRenderer to
        draw with OpenGL (the same picture, fast enough to play), None = the software Gpu; parts:
        draw only the packets of these effect parts (the uploads stay whole)."""
        from FF8GameData.psxgpu.gpu import GAME_WINDOW
        key = None
        if vram is None:
            key = (id(self), self._uploads_through(tick_index))
            vram = self._vram_cache[1] if self._vram_cache and self._vram_cache[0] == key else None
            if vram is None:
                vram = self.vram_at(tick_index)
                self._vram_cache = (key, vram)
        x, y, width, height = view or GAME_WINDOW
        size = max(1, round(width * scale)), max(1, round(height * scale))
        if renderer is not None:
            from FF8GameData.psxgpu.glrender import PrimitiveCollector
            gpu = PrimitiveCollector(vram, *size, origin=(x, y), scale=scale)
        else:
            gpu = Gpu(vram, *size, origin=(x, y), scale=scale)
        tick = self.ticks[tick_index]
        packets = tick.part_packets(parts)
        packets = packets if tick.ordered else sorted(packets, key=lambda p: (-p[0], -p[1]))
        for _bucket, _order, words in packets:
            gpu.draw_packet(words)
        if renderer is not None:
            return renderer.draw(gpu, vram_key=key), gpu
        return gpu.image(), gpu

    def _uploads_through(self, tick_index):
        """How many uploads change VRAM up to tick `tick_index`: the VRAM of two ticks with the same
        count is the same."""
        return len(self.pre_uploads) + sum(len(tick.uploads) for tick in self.ticks[:tick_index + 1])

    def vram_at(self, tick_index):
        """VRAM as the uploads queued up to tick `tick_index` (included) leave it."""
        vram = Vram()
        for upload in self.pre_uploads:
            _apply(vram, upload)
        for tick in self.ticks[:tick_index + 1]:
            for upload in tick.uploads:
                _apply(vram, upload)
        return vram

    @property
    def has_vram(self):
        return bool(self.pre_uploads or any(tick.uploads for tick in self.ticks))


def _apply(vram, upload):
    if upload[0] == "V":
        _kind, x, y, w, h, words = upload
        vram.upload(x, y, w, h, words)
    else:
        _kind, x, y, w, h, u, v = upload
        vram.copy(x, y, u, v, w, h)


def _hex_words(text):
    return [int(text[i:i + 4], 16) for i in range(0, len(text), 4)]


def parse_recording(lines, effect_id=None) -> EffectRecording:
    """An EffectRecording from the lines of a harness dump."""
    recording = EffectRecording(effect_id)
    by_index, current = {}, None
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind == "R":
            index = int(parts[1])
            current = by_index.setdefault(index, EffectTick(index))
            current.packets = []
            current.parts = []
            current.ordered = len(parts) > 3 and parts[3] == "ordered"
        elif kind in ("H", "Z", "O", "HC"):
            current = None                          # held frames: not the game's own ticks
        elif kind == "P" and current is not None and len(parts) >= 11:
            words = [int(word, 16) for word in parts[11:]]
            current.packets.append((int(parts[9], 16), len(current.packets), words))
            current.parts.append(int(parts[1]) if parts[1].isdigit() else 0)
        elif kind == "C" and len(parts) >= 8:
            index = int(parts[1])
            values = tuple(int(value) for value in parts[2:8])
            by_index.setdefault(index, EffectTick(index)).camera = (values[:3], values[3:])
        elif kind == "Q" and len(parts) >= 5:
            by_index.setdefault(int(parts[1]), EffectTick(int(parts[1]))).sprites.append(
                (int(parts[2]), int(parts[3], 16), int(parts[4])))
        elif kind == "V" and len(parts) >= 7:
            index, x, y, w, h = (int(value) for value in parts[1:6])
            upload = ("V", x, y, w, h, _hex_words(parts[6]))
            if len(upload[5]) == w * h:
                _upload_target(recording, by_index, index).append(upload)
        elif kind == "B" and len(parts) >= 8:
            index, x, y, w, h, u, v = (int(value) for value in parts[1:8])
            _upload_target(recording, by_index, index).append(("B", x, y, w, h, u, v))
    recording.ticks = [by_index[index] for index in sorted(by_index)]
    return recording


def _upload_target(recording, by_index, index):
    # an upload dumped before tick t's run was queued by the setup or a file load: it is in VRAM
    # when tick t draws, so it goes with tick t (tick 0's go to pre_uploads)
    if index == 0 and 0 not in by_index:
        return recording.pre_uploads
    return by_index.setdefault(index, EffectTick(index)).uploads


def load_recording(path, effect_id=None) -> EffectRecording:
    """A harness dump (.txt, or gzip-compressed .gz)."""
    import gzip
    opener = gzip.open if str(path).lower().endswith(".gz") else open
    with opener(path, "rt", encoding="ascii", errors="replace") as file:
        return parse_recording(file, effect_id)
