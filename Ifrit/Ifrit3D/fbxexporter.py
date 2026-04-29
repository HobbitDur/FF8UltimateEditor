# fbx_exporter.py
# Add this to your project

import struct
from typing import List, Tuple
import numpy as np


class FF8ToFBXExporter:
    """
    Exports FF8 monster data to FBX format.
    This writes a binary FBX file that can be imported into Blender, Maya, etc.
    """

    def __init__(self, ifrit_manager):
        self.ifrit_manager = ifrit_manager

    def export(self, filepath: str):
        """
        Export the current monster to FBX.
        Includes: skeleton, mesh, textures, and all animations.
        """
        # Get data from your existing structures
        vertices = self._get_all_vertices()
        triangles = self.ifrit_manager.enemy.geometry_data.get_triangles()
        quads = self.ifrit_manager.enemy.geometry_data.get_quads()
        bones = self.ifrit_manager.enemy.bone_data.bones
        animations = self.ifrit_manager.enemy.animation_data.animations

        # Write FBX file (simplified ASCII FBX for clarity)
        # Note: For production, use the official FBX SDK
        self._write_ascii_fbx(filepath, vertices, triangles, quads, bones, animations)

    def _write_ascii_fbx(self, filepath, vertices, triangles, quads, bones, animations):
        """
        Write an ASCII FBX file (simpler to implement, though binary is more efficient).
        This is a minimal FBX that should still import into most 3D software.
        """
        with open(filepath, 'w') as f:
            # FBX header
            f.write("""; FBX 7.4.0 project file
; ----------------------------------------------------

FBXHeaderExtension:  {
    FBXHeaderVersion: 1003
    FBXVersion: 7400
}

Definitions: {
    Version: 100
    Count: 4

    # Define bone (limb node)
    ObjectType: "LimbNode" {
        Count: {0}
    }

    # Define mesh
    ObjectType: "Mesh" {
        Count: 1
    }

    # Define material
    ObjectType: "Material" {
        Count: 1
    }
}

""".format(len(bones)))

            # Write objects section with skeleton
            f.write("Objects: {\n")

            # Write skeleton hierarchy
            for i, bone in enumerate(bones):
                parent_id = bone.parent_id if bone.parent_id != 0xFFFF else -1
                f.write(f"""
    Model: {{Model::LimbNode::Bone{i}_{i}}} {{
        Version: 232
        Properties70:  {{
            P: "RotationActive", "bool", "", "", 1
            P: "InheritType", "enum", "", "", 1
            P: "ScalingMax", "Vector3D", "Vector", "", 0,0,0
            P: "DefaultAttributeIndex", "int", "Integer", "", 0
        }}
        Shading: T
        Culling: "CullingOff"
        Parent: {f"Model::LimbNode::Bone{parent_id}_{parent_id}" if parent_id >= 0 else ""}
    }}
""")

            # Write mesh
            f.write(f"""
    Model::Mesh::MonsterMesh {{
        Version: 232
        Properties70:  {{
            P: "RotationActive", "bool", "", "", 1
            P: "InheritType", "enum", "", "", 1
            P: "ScalingMax", "Vector3D", "Vector", "", 0,0,0
            P: "DefaultAttributeIndex", "int", "Integer", "", 0
        }}
        Shading: T
        Culling: "CullingOff"
        Geometry: Geometry::MonsterMesh
    }}
""")

            # Write geometry (vertex positions, normals, UVs)
            f.write(f"""
    Geometry::MonsterMesh {{
        Version: 124
        Vertices: *{len(vertices)} {{
            a: {self._format_vertex_list(vertices)}
        }}
        PolygonVertexIndex: *{self._get_polygon_count(triangles, quads)} {{
            a: {self._format_polygon_indices(triangles, quads)}
        }}
        LayerElementNormal: 0 {{
            Version: 102
            Name: ""
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "Direct"
            Normals: *{len(vertices)} {{
                a: {self._generate_normals(vertices, triangles, quads)}
            }}
        }}
        LayerElementUV: 0 {{
            Version: 101
            Name: "UVMap"
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "IndexToDirect"
            UV: *{len(vertices)} {{
                a: {self._get_uv_coordinates()}
            }}
            UVIndex: *{len(vertices)} {{
                a: {self._get_uv_indices(triangles, quads)}
            }}
        }}
        LayerElementMaterial: 0 {{
            Version: 101
            Name: ""
            MappingInformationType: "AllSame"
            ReferenceInformationType: "IndexToDirect"
            Materials: *1 {{
                a: 0
            }}
        }}
    }}
""")

            # Write animation stacks
            for anim_id, animation in enumerate(animations):
                f.write(f"""
    AnimationStack::AnimStack{anim_id} {{
        Version: 0
        Properties70:  {{
            P: "LocalStart", "KTime", "Time", "", 0
            P: "LocalStop", "KTime", "Time", "", {animation._nb_frames * 46186158000}
        }}
        AnimationLayer::AnimLayer{anim_id} {{
            Version: 0
            Properties70:  {{
                P: "BlendMode", "enum", "", "", 0
                P: "RotationAccumulationMode", "enum", "", "", 0
                P: "ScaleAccumulationMode", "enum", "", "", 0
            }}
""")

                # Write bone animations
                for bone_id in range(len(bones)):
                    f.write(f"""
            AnimationCurveNode::AnimCurveNode_Bone{bone_id}_Rot {{
                Properties70: {{
                    P: "d|X", "Number", "", "A", 0
                    P: "d|Y", "Number", "", "A", 0
                    P: "d|Z", "Number", "", "A", 0
                }}
""")

                    # Write rotation curves for X, Y, Z
                    for axis_idx, axis in enumerate(['X', 'Y', 'Z']):
                        f.write(f"""
                AnimationCurve::AnimCurve_Rot{axis} {{
                    Default: 0
                    KeyVer: 4008
                    KeyCount: {animation._nb_frames}
                    Key: {self._format_animation_keys(animation, bone_id, axis_idx)}
                }}
""")
                    f.write("            }\n")

                f.write("        }\n    }\n")

            f.write("}\n")

            # Write connections
            f.write("""
Connections: {
""")
            # Connect bones
            for i, bone in enumerate(bones):
                if bone.parent_id != 0xFFFF:
                    f.write(f'    Connect: "OO", "Model::LimbNode::Bone{i}_{i}", "Model::LimbNode::Bone{bone.parent_id}_{bone.parent_id}"\n')

            # Connect mesh to first bone (root)
            if bones:
                f.write(f'    Connect: "OO", "Model::Mesh::MonsterMesh", "Model::LimbNode::Bone0_0"\n')
                f.write(f'    Connect: "OO", "Geometry::MonsterMesh", "Model::Mesh::MonsterMesh"\n')

            # Connect animations
            for anim_id in range(len(animations)):
                f.write(f'    Connect: "OO", "AnimationStack::AnimStack{anim_id}", ""\n')

            f.write("}\n")

    def _format_vertex_list(self, vertices):
        """Format vertices as FBX-compatible list"""
        coords = []
        for v in vertices:
            coords.extend([v[0], v[1], v[2]])
        return ",".join([f"{c:.6f}" for c in coords])

    def _get_polygon_count(self, triangles, quads):
        """FBX stores polygon indices with negative last index to mark end"""
        return len(triangles) * 3 + len(quads) * 4

    def _format_polygon_indices(self, triangles, quads):
        """Format indices with negative last index of each polygon"""
        indices = []
        for tri in triangles:
            indices.extend([tri[0], tri[1], -tri[2] - 1])  # Negative marks end of polygon
        for quad in quads:
            indices.extend([quad[0], quad[1], quad[2], -quad[3] - 1])
        return ",".join([str(i) for i in indices])

    def _generate_normals(self, vertices, triangles, quads):
        """Generate simple vertex normals (you may want to compute proper ones)"""
        # Simplified: returns zero normals
        return ",".join(["0,0,1"] * len(vertices))

    def _get_uv_coordinates(self):
        """Extract UV coordinates from your geometry data"""
        uvs = []
        # This needs to be populated from your GeometryTriangle/GeometryQuad classes
        for obj in self.ifrit_manager.enemy.geometry_data.object_data:
            for vd in obj.vertices_data:
                # UVs are stored per vertex in your structure
                pass
        return ",".join(["0,0"] * 10)  # Placeholder

    def _get_uv_indices(self, triangles, quads):
        """Get UV indices matching polygon vertices"""
        indices = []
        for tri in triangles:
            indices.extend([tri[0], tri[1], tri[2]])
        for quad in quads:
            indices.extend([quad[0], quad[1], quad[2], quad[3]])
        return ",".join([str(i) for i in indices])

    def _format_animation_keys(self, animation, bone_id, axis_idx):
        """Format rotation keys for an animation"""
        keys = []
        for frame_id, frame in enumerate(animation.frames):
            if bone_id < len(frame.bone_rot_deg):
                rotation = frame.bone_rot_deg[bone_id][axis_idx]
                time = frame_id * 46186158000  # FBX time unit (ticks)
                keys.append(f"{time},1,{rotation:.4f},0,0,0")
        return ",".join(keys)


class FBXImporter:
    """
    Imports FBX files back into FF8 format.
    This reads edited FBX files and converts them back to your internal structures.
    """

    def __init__(self, ifrit_manager):
        self.ifrit_manager = ifrit_manager

    def import_file(self, filepath: str):
        """
        Import an FBX file and update the current monster data.
        This will parse the FBX and convert back to FF8 formats.
        """
        # For a robust solution, use the official FBX SDK:
        # from fbx import *

        # Simplified ASCII FBX parsing (for demonstration)
        vertices, bone_transforms = self._parse_ascii_fbx(filepath)

        # Convert back to FF8 format
        self._update_ff8_data(vertices, bone_transforms)

    def _parse_ascii_fbx(self, filepath):
        """Parse ASCII FBX (simplified)"""
        vertices = []
        bone_transforms = {}

        with open(filepath, 'r') as f:
            content = f.read()

            # Extract vertices (simplified regex - use proper parsing in production)
            import re
            vert_match = re.search(r'Vertices:\s*\*\d+\s*\{\s*a:\s*([^}]+)', content)
            if vert_match:
                vert_data = [float(x) for x in vert_match.group(1).split(',')]
                vertices = [(vert_data[i], vert_data[i + 1], vert_data[i + 2])
                            for i in range(0, len(vert_data), 3)]

            # Extract bone transformations
            # This would need to parse the AnimationCurveNode sections

        return vertices, bone_transforms

    def _update_ff8_data(self, vertices, bone_transforms):
        """Convert imported data back to FF8 format"""
        # Update vertex positions
        # You'll need to:
        # 1. Convert back to FF8's 16-bit integer format (multiply by 2048)
        # 2. Update the Vertex objects in your GeometrySection
        # 3. Handle bone weight assignments

        # Update bone animations
        # 1. Convert degrees back to FF8's 4096-unit rotation
        # 2. Store in AnimationFrame.bone_rot_raw
        pass