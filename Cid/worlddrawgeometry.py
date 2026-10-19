"""Read-only terrain support for draw triggers (wmx.obj, base world segments).

The third byte of a wmset draw record is a polygon index, not a magic ID.
The trigger covers that triangle; its centroid is a useful map marker.
Story replacement segments are deliberately not guessed here.
"""
import struct
import math
from pathlib import Path


class WorldDrawGeometry:
    SEGMENT_SIZE = 0x9000
    BLOCK_SIZE = 2048

    def __init__(self, file_path):
        self.data = Path(file_path).read_bytes()
        if len(self.data) < 768 * self.SEGMENT_SIZE or len(self.data) % self.SEGMENT_SIZE:
            raise ValueError("wmx.obj must contain at least 768 complete world segments")
        self._blocks = {}

    def triangles(self, block_x, block_y, cache=True):
        key = (block_x, block_y)
        if key in self._blocks:
            return self._blocks[key]
        if not (0 <= block_x < 128 and 0 <= block_y < 96):
            return []
        base, coords, faces = self.read_block(block_x, block_y)
        triangles = []
        for i in range(faces):
            indices = self.data[base + 4 + i * 16:base + 7 + i * 16]
            if any(index >= len(coords) for index in indices):
                raise ValueError("Invalid wmx triangle vertex")
            triangles.append(tuple((block_x + coords[index][0] / self.BLOCK_SIZE,
                                    block_y - coords[index][2] / self.BLOCK_SIZE)
                                   for index in indices))
        if cache:
            self._blocks[key] = triangles
        return triangles

    def read_block(self, block_x, block_y):
        """Validated raw vertices and face-table address, without caching the world."""
        if not (0 <= block_x < 128 and 0 <= block_y < 96):
            raise ValueError('World block is outside the base map')
        segment = (block_y // 4 * 32 + block_x // 4) * self.SEGMENT_SIZE
        entry = block_y % 4 * 4 + block_x % 4
        offset = struct.unpack_from('<I', self.data, segment + 4 + 4 * entry)[0] & ~3
        if not 68 <= offset < self.SEGMENT_SIZE - 4:
            raise ValueError("Invalid wmx block offset")
        base = segment + offset
        faces, vertices, normals = struct.unpack_from('BBB', self.data, base)
        vertex_base = base + 4 + faces * 16
        if vertex_base + (vertices + normals) * 8 > segment + self.SEGMENT_SIZE:
            raise ValueError("Truncated wmx block")
        coords = [struct.unpack_from('<hhh', self.data, vertex_base + i * 8)
                  for i in range(vertices)]
        return base, coords, faces

    def terrain_at(self, x, y, triangle_index=None):
        """Ground, interpolated elevation and slope in game units at a map position.

        Raw wmx Y points down; sea is zero. Supplying a triangle index inspects
        that draw trigger even if a bridge or another surface overlaps it.
        """
        picked = self.pick(x, y) if triangle_index is None else None
        if triangle_index is None:
            if picked is None:
                return None
            triangle_index = picked[2]
        if not (0 <= x < 128 and 0 <= y < 96):
            return None
        bx, by = int(x), int(y)
        base, coords, faces = self.read_block(bx, by)
        if not 0 <= triangle_index < faces:
            return None
        face = self.data[base + 4 + triangle_index * 16:base + 20 + triangle_index * 16]
        if any(i >= len(coords) for i in face[:3]):
            raise ValueError('Invalid wmx triangle vertex')
        vertices = [(coords[i][0], -coords[i][2], -coords[i][1]) for i in face[:3]]
        a, b, c = vertices
        dx1, dy1, dh1 = (b[i] - a[i] for i in range(3))
        dx2, dy2, dh2 = (c[i] - a[i] for i in range(3))
        determinant = dx1 * dy2 - dx2 * dy1
        if abs(determinant) < 1e-10:
            return None
        hx = (dh1 * dy2 - dh2 * dy1) / determinant
        hy = (dx1 * dh2 - dx2 * dh1) / determinant
        height = a[2] + hx * ((x - bx) * self.BLOCK_SIZE - a[0]) + hy * ((y - by) * self.BLOCK_SIZE - a[1])
        return dict(block_x=bx, block_y=by, triangle=triangle_index, ground=face[13],
                    height=height, slope=math.degrees(math.atan(math.hypot(hx, hy))))

    def overview_png(self):
        """Flat base-terrain map in the same coordinate system as the trigger records.

        Generate from the loaded file so modded geometry is reflected rather than
        relying on the bundled reference terrain. Do not retain the entire world
        mesh just to build this small preview.
        """
        from io import BytesIO
        from PIL import Image, ImageDraw

        image = Image.new('RGB', (1024, 768), (28, 55, 120))
        painter = ImageDraw.Draw(image)
        region_colors = {0: (200, 217, 220), 1: (117, 174, 100), 2: (108, 154, 104),
                         3: (121, 163, 105), 4: (97, 149, 86), 5: (185, 154, 108),
                         6: (172, 177, 99), 7: (157, 153, 103)}
        for by in range(96):
            for bx in range(128):
                segment = (by // 4 * 32 + bx // 4) * self.SEGMENT_SIZE
                group = struct.unpack_from('<I', self.data, segment)[0]
                entry = by % 4 * 4 + bx % 4
                base = segment + (struct.unpack_from('<I', self.data, segment + 4 + 4 * entry)[0] & ~3)
                for index, triangle in enumerate(self.triangles(bx, by, cache=False)):
                    ground = self.data[base + 4 + index * 16 + 13]
                    if ground == 34:  # open sea
                        continue
                    color = region_colors.get(group, (112, 150, 111))
                    if ground == 10:
                        color = (214, 204, 151)
                    painter.polygon([(round(x * 8), round(y * 8)) for x, y in triangle], fill=color)
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    def triangle(self, draw):
        triangles = self.triangles(*draw.get_block_xy())
        return triangles[draw.sub_id] if 0 <= draw.sub_id < len(triangles) else None

    def mesh_png(self):
        """Transparent triangle edges in the same world projection as the overview.

        Build once on demand. A high-resolution overlay keeps pan/zoom responsive
        without drawing hundreds of thousands of individual polygons every frame.
        """
        from io import BytesIO
        from PIL import Image, ImageDraw

        scale = 32
        image = Image.new('RGBA', (128 * scale, 96 * scale))
        painter = ImageDraw.Draw(image)
        for by in range(96):
            for bx in range(128):
                for triangle in self.triangles(bx, by, cache=False):
                    points = [(round(x * scale), round(y * scale)) for x, y in triangle]
                    painter.line(points + [points[0]], fill=(235, 245, 255, 115), width=1)
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    def pick(self, x, y):
        """Return the polygon under a map position, or None outside valid terrain."""
        if not (0 <= x < 128 and 0 <= y < 96):
            return None
        bx, by = int(x), int(y)
        for index, triangle in enumerate(self.triangles(bx, by)):
            a, b, c = triangle
            def cross(p, q):
                return (p[0] - x) * (q[1] - y) - (p[1] - y) * (q[0] - x)
            signs = (cross(a, b), cross(b, c), cross(c, a))
            area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(area) > 1e-10 and (min(signs) >= -1e-10 or max(signs) <= 1e-10):
                return bx | ((by & 1) << 7), by >> 1, index
        return None
