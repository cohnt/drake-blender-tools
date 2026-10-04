# SPDX-License-Identifier: MIT
"""Regression tests for Blender meshfile imports."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import pytest

try:
    import bpy
except ModuleNotFoundError:
    bpy = None

if bpy is not None:
    import numpy as np
    from meshcat_html_importer.blender.mesh_builder import create_mesh_file_object
    from meshcat_html_importer.blender.scene_builder import (
        _apply_world_transform,
        _create_object_from_node,
    )
    from meshcat_html_importer.scene.geometry import MeshFileGeometry
    from meshcat_html_importer.scene.materials import parse_material
    from meshcat_html_importer.scene.scene_graph import SceneNode
    from meshcat_html_importer.scene.transforms import Transform


pytestmark = pytest.mark.skipif(bpy is None, reason="bpy is not installed")


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def reset_blender_state():
    """Reset Blender to an empty factory scene before and after each test."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    yield
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _make_translated_gltf_geometry() -> MeshFileGeometry:
    """Create a tiny glTF mesh with a static node translation."""
    positions = struct.pack(
        "<9f",
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
    )
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "mesh.bin", "byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 1.0],
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
        # glTF is Y-up. Blender's importer maps glTF Y to Blender Z.
        "nodes": [{"mesh": 0, "translation": [0.0, -0.5, 0.0]}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    return MeshFileGeometry(
        format="gltf",
        data=json.dumps(gltf).encode("utf-8"),
        resources={"mesh.bin": positions},
    )


def _make_textured_obj_geometry() -> MeshFileGeometry:
    """Create a tiny textured OBJ mesh."""
    obj_data = "\n".join(
        [
            "mtllib test.mtl",
            "o Triangle",
            "v 0.0 0.0 0.0",
            "v 1.0 0.0 0.0",
            "v 0.0 1.0 0.0",
            "vt 0.0 0.0",
            "vt 1.0 0.0",
            "vt 0.0 1.0",
            "usemtl material_0",
            "f 1/1 2/2 3/3",
            "",
        ]
    ).encode("utf-8")
    mtl_data = "\n".join(
        [
            "newmtl material_0",
            "Ka 1.000000 1.000000 1.000000",
            "Kd 1.000000 1.000000 1.000000",
            "Ks 0.000000 0.000000 0.000000",
            "d 1.000000",
            "illum 1",
            "map_Kd test.png",
            "",
        ]
    ).encode("utf-8")
    return MeshFileGeometry(
        format="obj",
        data=obj_data,
        resources={
            "test.mtl": mtl_data,
            "test.png": TINY_PNG,
        },
    )


# A small non-planar mesh shared by the Collada and OBJ fixtures.
TETRA_POSITIONS = [
    (0.0, 0.0, 0.0),
    (0.1, 0.0, 0.0),
    (0.0, 0.2, 0.0),
    (0.0, 0.0, 0.3),
]
TETRA_TRIANGLES = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]


def _make_collada_geometry(
    asset: str = "<up_axis>Y_UP</up_axis>", normals: bool = True
) -> MeshFileGeometry:
    """Create a tiny Collada tetrahedron, with per-corner normals by default.

    The node translation is part of the file, so it must be baked into the
    vertices, as Meshcat does.
    """
    positions = " ".join(f"{c}" for p in TETRA_POSITIONS for c in p)
    p = " ".join(f"{v} {f}" for f, tri in enumerate(TETRA_TRIANGLES) for v in tri)
    dae = f"""<?xml version="1.0" encoding="UTF-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>{asset}</asset>
  <library_geometries>
    <geometry id="tetra">
      <mesh>
        <source id="pos">
          <float_array id="pos-array" count="12">{positions}</float_array>
          <technique_common>
            <accessor source="#pos-array" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="nrm">
          <float_array id="nrm-array" count="12">
            0 0 -1  0 -1 0  -1 0 0  0.57735 0.57735 0.57735
          </float_array>
          <technique_common>
            <accessor source="#nrm-array" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>
        <triangles count="4">
          <input offset="0" semantic="VERTEX" source="#verts"/>
          {'<input offset="1" semantic="NORMAL" source="#nrm"/>' if normals else ""}
          <p>{p}</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="scene">
      <node>
        <translate>0.5 0 0</translate>
        <instance_geometry url="#tetra"/>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>
"""
    if not normals:
        dae = dae.replace(f"<p>{p}</p>", f"<p>{' '.join(p.split()[::2])}</p>")
    return MeshFileGeometry(format="dae", data=dae.encode("utf-8"))


def _make_tetra_obj_geometry() -> MeshFileGeometry:
    """The Collada tetrahedron as an OBJ, with its node translation applied."""
    lines = [f"v {x + 0.5} {y} {z}" for x, y, z in TETRA_POSITIONS]
    lines += ["f " + " ".join(str(v + 1) for v in tri) for tri in TETRA_TRIANGLES]
    return MeshFileGeometry(format="obj", data=("\n".join(lines) + "\n").encode())


def _drake_phong_material(color: int):
    """The MeshPhongMaterial Drake sends with a Mesh shape."""
    return parse_material(
        {
            "uuid": "mat",
            "type": "MeshPhongMaterial",
            "color": color,
            "vertexColors": False,
            "opacity": 1.0,
            "reflectivity": 0.5,
            "side": 2,
            "transparent": False,
        }
    )


def _world_vertices(obj) -> np.ndarray:
    """World-space vertices of an unparented object, linked to a scene or not."""
    return np.array([tuple(obj.matrix_basis @ v.co) for v in obj.data.vertices])


class TestBlenderMeshfileImport:
    """Blender-backed regression tests for meshfile imports."""

    def test_gltf_import_preserves_static_node_translation(self):
        """glTF node translations should survive post-import world transforms."""
        node = SceneNode(
            path="/floor",
            name="floor",
            geometry=_make_translated_gltf_geometry(),
        )

        obj, import_matrix = create_mesh_file_object(node, name="floor")

        assert obj is not None
        assert import_matrix is not None
        assert import_matrix[2][3] == pytest.approx(-0.5)

        _apply_world_transform(obj, node, import_matrix=import_matrix)

        assert obj.matrix_world.translation.z == pytest.approx(-0.5)

    def test_obj_import_packs_texture_before_tempdir_cleanup(self):
        """OBJ textures should remain valid after the import tempdir is deleted."""
        node = SceneNode(
            path="/tray",
            name="tray",
            geometry=_make_textured_obj_geometry(),
        )

        obj, import_matrix = create_mesh_file_object(node, name="tray")

        assert obj is not None
        assert import_matrix is None
        assert len(bpy.data.images) == 1

        image = bpy.data.images[0]
        image_path = Path(bpy.path.abspath(image.filepath, library=image.library))

        assert image.packed_file is not None
        assert tuple(image.size) == (1, 1)
        assert not image_path.exists()

        material = obj.data.materials[0]
        assert material is not None
        assert material.node_tree is not None
        assert any(
            getattr(node, "image", None) == image for node in material.node_tree.nodes
        )

    def test_dae_import_builds_mesh_with_file_normals(self):
        """Collada meshes become Blender meshes, keeping the file's normals."""
        node = SceneNode(
            path="/robot/link", name="link", geometry=_make_collada_geometry()
        )

        obj, import_matrix = create_mesh_file_object(node, name="link")

        assert obj is not None
        assert import_matrix is None
        assert len(obj.data.vertices) == 4
        assert len(obj.data.polygons) == 4
        assert obj.data.has_custom_normals

        corner_normals = [tuple(n.vector) for n in obj.data.corner_normals]
        assert corner_normals[0] == pytest.approx((0.0, 0.0, -1.0), abs=1e-4)
        assert corner_normals[9] == pytest.approx((0.57735, 0.57735, 0.57735), abs=1e-4)

    def test_dae_keeps_per_corner_normals_uvs_and_both_sides(self):
        """Every corner keeps its own normal and UV, in triangle order.

        The two triangles use the same vertices with opposite winding, as in a
        double-sided export. Meshcat draws both, so both are kept.
        """
        normals = np.array(
            [[0, 0, 1], [0, 0.6, 0.8], [0.6, 0, 0.8],
             [0, 0, -1], [0, -0.6, -0.8], [-0.6, 0, -0.8]]
        )  # fmt: skip
        uvs = np.array([[0, 0], [1, 0], [0, 1], [0.5, 0.5], [0.25, 0.75], [1, 1]])
        flat = " ".join(f"{v}" for v in normals.ravel())
        flat_uvs = " ".join(f"{v}" for v in uvs.ravel())
        dae = f"""<?xml version="1.0" encoding="UTF-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><up_axis>Y_UP</up_axis></asset>
  <library_geometries>
    <geometry id="sheet">
      <mesh>
        <source id="pos">
          <float_array id="pos-array">0 0 0  1 0 0  0 1 0</float_array>
          <technique_common>
            <accessor source="#pos-array" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="nrm">
          <float_array id="nrm-array">{flat}</float_array>
          <technique_common>
            <accessor source="#nrm-array" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="uv">
          <float_array id="uv-array">{flat_uvs}</float_array>
          <technique_common>
            <accessor source="#uv-array" stride="2">
              <param name="S" type="float"/><param name="T" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>
        <triangles count="2">
          <input offset="0" semantic="VERTEX" source="#verts"/>
          <input offset="1" semantic="NORMAL" source="#nrm"/>
          <input offset="2" semantic="TEXCOORD" source="#uv" set="0"/>
          <p>0 0 0  1 1 1  2 2 2  0 3 3  2 4 4  1 5 5</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="scene">
      <node><instance_geometry url="#sheet"/></node>
    </visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>
"""
        node = SceneNode(
            path="/sheet",
            name="sheet",
            geometry=MeshFileGeometry(format="dae", data=dae.encode("utf-8")),
        )

        obj, _ = create_mesh_file_object(node, name="sheet")

        mesh = obj.data
        assert len(mesh.polygons) == 2
        corner_positions = [
            tuple(mesh.vertices[lp.vertex_index].co) for lp in mesh.loops
        ]
        np.testing.assert_allclose(
            corner_positions,
            [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 0), (0, 1, 0), (1, 0, 0)],
        )
        np.testing.assert_allclose(
            [tuple(n.vector) for n in mesh.corner_normals], normals, atol=1e-3
        )
        np.testing.assert_allclose(
            [tuple(d.uv) for d in mesh.uv_layers["UVMap"].data], uvs, atol=1e-6
        )

    def test_dae_without_normals_is_flat_shaded(self):
        """Meshcat computes flat normals for a dae without NORMAL; so does Blender."""
        node = SceneNode(
            path="/flat", name="flat", geometry=_make_collada_geometry(normals=False)
        )

        obj, _ = create_mesh_file_object(node, name="flat")

        assert len(obj.data.polygons) == 4
        assert not obj.data.has_custom_normals
        assert not any(polygon.use_smooth for polygon in obj.data.polygons)

    def test_dae_object_matches_obj_object(self):
        """A dae and an OBJ of the same vertices land in the same place.

        Both are placed by the same Meshcat transform. The dae keeps the Drake
        Rgba as its colour, as Meshcat shows it.
        """
        transform = Transform(
            translation=(1.0, -2.0, 0.5),
            rotation=(0.0, 0.0, 0.38268343, 0.92387953),  # 45 deg about z
            scale=(1.0, 1.0, 1.0),
        )
        dae_node = SceneNode(
            path="/example/dae_mesh",
            name="dae_mesh",
            transform=transform,
            geometry=_make_collada_geometry(),
            material=_drake_phong_material(0xCC1919),
        )
        obj_node = SceneNode(
            path="/example/obj_reference",
            name="obj_reference",
            transform=transform,
            geometry=_make_tetra_obj_geometry(),
            material=_drake_phong_material(0x19991A),
        )

        dae_obj, _ = _create_object_from_node(dae_node)
        obj_obj, _ = _create_object_from_node(obj_node)

        dae_verts = _world_vertices(dae_obj)
        obj_verts = _world_vertices(obj_obj)
        assert len(dae_verts) == len(obj_verts) == 4
        # Same vertex set, regardless of order.
        dists = np.linalg.norm(dae_verts[:, None, :] - obj_verts[None, :, :], axis=2)
        assert dists.min(axis=1).max() < 1e-6
        assert dists.min(axis=0).max() < 1e-6
        # Both are placed by the Meshcat transform: rotate 45 deg about z, then
        # translate.
        c = s = np.sqrt(0.5)
        expected = (np.array(TETRA_POSITIONS) + [0.5, 0, 0]) @ np.array(
            [[c, s, 0], [-s, c, 0], [0, 0, 1]]
        ) + [1.0, -2.0, 0.5]
        dists = np.linalg.norm(dae_verts[:, None, :] - expected[None, :, :], axis=2)
        assert dists.min(axis=1).max() < 1e-6

        material = dae_obj.active_material
        assert material is not None
        bsdf = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        assert tuple(bsdf.inputs["Base Color"].default_value)[:3] == pytest.approx(
            (0.8, 0.098, 0.098), abs=1e-3
        )

    def test_dae_unit_and_up_axis_ignored_like_meshcat(self, capsys):
        """<unit> and Z_UP do not change the imported geometry."""
        reference_node = SceneNode(
            path="/a", name="a", geometry=_make_collada_geometry()
        )
        variant_node = SceneNode(
            path="/b",
            name="b",
            geometry=_make_collada_geometry(
                '<unit meter="0.001" name="millimeter"/><up_axis>Z_UP</up_axis>'
            ),
        )

        reference, _ = create_mesh_file_object(reference_node, name="a")
        variant, _ = create_mesh_file_object(variant_node, name="b")

        np.testing.assert_allclose(
            [tuple(v.co) for v in variant.data.vertices],
            [tuple(v.co) for v in reference.data.vertices],
        )
        # Ignoring them is intended, so it is a note, not a warning.
        out = capsys.readouterr().out
        assert "Note: Collada mesh for /b" in out
        assert "Warning" not in out

    def test_unsupported_format_warns(self, capsys):
        """Formats the importer cannot read are reported, not silently dropped."""
        node = SceneNode(
            path="/robot/part",
            name="part",
            geometry=MeshFileGeometry(format="stl", data=b"solid part\nendsolid\n"),
        )

        obj, import_matrix = create_mesh_file_object(node, name="part")

        assert obj is None
        assert import_matrix is None
        out = capsys.readouterr().out
        assert "Unsupported embedded mesh format 'stl'" in out
        assert "/robot/part" in out

    def test_dae_without_geometry_warns(self, capsys):
        """A Collada file with nothing Meshcat draws is reported."""
        node = SceneNode(
            path="/robot/empty",
            name="empty",
            geometry=MeshFileGeometry(format="dae", data=b"<COLLADA></COLLADA>"),
        )

        obj, _ = create_mesh_file_object(node, name="empty")

        assert obj is None
        assert "/robot/empty" in capsys.readouterr().out
