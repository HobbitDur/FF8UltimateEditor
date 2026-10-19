"""Prepared actor topology for the camera preview's batched renderer.

Indices, UVs and materials are constant during playback. Only the shared vertex
array changes. Quad halves share the original face normal for PSX-style culling.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class PreviewBatch:
    indices: np.ndarray
    normal_indices: np.ndarray
    uvs: np.ndarray
    pixmap: object
    black_is_transparent: bool
    depth_bias: int
    color: tuple = (.4, .55, .75)


@dataclass
class PreviewMesh:
    vertices: np.ndarray
    batches: list


def prepare_batches(geometry, texture_data, black_is_transparent=True, offset=0):
    tri = geometry.get_triangles_with_uv()
    quad = geometry.get_quads_with_uv()
    pixmaps = [td.texture_image for td in texture_data if td.texture_image is not None]
    raw_ids = sorted({entry[2] for entry in tri + quad})
    textures = {raw: pixmaps[min(rank, len(pixmaps) - 1)] for rank, raw in enumerate(raw_ids)} if pixmaps else {}
    groups = {}

    def add(indices, uvs, raw, bias, corners, color=(.4, .55, .75)):
        key = (raw, bias, color)
        values = groups.setdefault(key, ([], [], []))
        values[0].append(tuple(indices[i] + offset for i in corners))
        values[1].append(tuple(i + offset for i in indices[:3]))
        values[2].append(tuple(uvs[i] for i in corners))

    for entry in tri:
        add(*entry, (0, 1, 2))
    for entry in quad:
        for corners in ((0, 1, 3), (0, 2, 3)):
            add(*entry, corners)
    for size, entries in ((3, geometry.get_colored_triangles_with_color()),
                          (4, geometry.get_colored_quads_with_color())):
        for indices, color, bias in entries:
            for corners in (((0, 1, 2),) if size == 3 else ((0, 1, 3), (0, 2, 3))):
                add(indices, ((0., 0.),) * size, None, bias, corners, tuple(color))
    return [PreviewBatch(np.asarray(indices, dtype=np.int32), np.asarray(normals, dtype=np.int32),
                         np.asarray(uvs, dtype=np.float32), textures.get(raw), black_is_transparent,
                         bias, color)
            for (raw, bias, color), (indices, normals, uvs) in groups.items()]
