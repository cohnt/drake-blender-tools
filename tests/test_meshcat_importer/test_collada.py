# SPDX-License-Identifier: MIT
"""Tests for the Collada reader, which follows how Meshcat shows .dae meshes."""

import numpy as np
import pytest
from collada.common import DaeError
from meshcat_html_importer.scene.collada import parse_collada

# Accessor parameters for a source of 3D vectors.
XYZ = (
    '<param name="X" type="float"/><param name="Y" type="float"/>'
    '<param name="Z" type="float"/>'
)

# Hubo-style geometry: one <triangles>, with VERTEX, COLOR and NORMAL
# interleaved at offsets 0, 1 and 2.
TRIANGLE_GEOMETRY = f"""
<geometry id="tri-lib" name="tri">
  <mesh>
    <source id="tri-positions">
      <float_array id="tri-positions-array" count="12">
        0 0 0  1 0 0  0 1 0  0 0 1
      </float_array>
      <technique_common>
        <accessor count="4" source="#tri-positions-array" stride="3">
          {XYZ}
        </accessor>
      </technique_common>
    </source>
    <source id="tri-colors">
      <float_array id="tri-colors-array" count="4">1 1 0 1</float_array>
      <technique_common>
        <accessor count="1" source="#tri-colors-array" stride="4">
          <param name="R" type="float"/><param name="G" type="float"/>
          <param name="B" type="float"/><param name="A" type="float"/>
        </accessor>
      </technique_common>
    </source>
    <source id="tri-normals">
      <float_array id="tri-normals-array" count="6">0 0 1  1 0 0</float_array>
      <technique_common>
        <accessor count="2" source="#tri-normals-array" stride="3">
          {XYZ}
        </accessor>
      </technique_common>
    </source>
    <vertices id="tri-vertices">
      <input semantic="POSITION" source="#tri-positions"/>
    </vertices>
    <triangles count="2">
      <input offset="0" semantic="VERTEX" source="#tri-vertices"/>
      <input offset="1" semantic="COLOR" source="#tri-colors"/>
      <input offset="2" semantic="NORMAL" source="#tri-normals"/>
      <p>0 0 0  1 0 0  2 0 0  0 0 1  2 0 1  3 0 1</p>
    </triangles>
  </mesh>
</geometry>
"""

# One quad and one pentagon in a polylist, with UVs on the primitive.
POLYLIST_GEOMETRY = f"""
<geometry id="poly-lib">
  <mesh>
    <source id="poly-positions">
      <float_array id="poly-positions-array" count="27">
        0 0 0  1 0 0  1 1 0  0 1 0
        2 0 0  3 0 0  3 1 0  2.5 2 0  2 1 0
      </float_array>
      <technique_common>
        <accessor count="9" source="#poly-positions-array" stride="3">
          {XYZ}
        </accessor>
      </technique_common>
    </source>
    <source id="poly-uvs">
      <float_array id="poly-uvs-array" count="2">0.25 0.75</float_array>
      <technique_common>
        <accessor count="1" source="#poly-uvs-array" stride="2">
          <param name="S" type="float"/><param name="T" type="float"/>
        </accessor>
      </technique_common>
    </source>
    <vertices id="poly-vertices">
      <input semantic="POSITION" source="#poly-positions"/>
    </vertices>
    <polylist count="2">
      <input offset="0" semantic="VERTEX" source="#poly-vertices"/>
      <input offset="1" semantic="TEXCOORD" source="#poly-uvs" set="0"/>
      <vcount>4 5</vcount>
      <p>0 0 1 0 2 0 3 0  4 0 5 0 6 0 7 0 8 0</p>
    </polylist>
  </mesh>
</geometry>
"""


def _collada(
    geometries: str,
    nodes: str,
    asset: str = "<up_axis>Y_UP</up_axis>",
    libraries: str = "",
) -> bytes:
    """Wrap geometries and visual-scene nodes into a Collada 1.4.1 document."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>{asset}</asset>
  {libraries}
  <library_geometries>{geometries}</library_geometries>
  <library_visual_scenes>
    <visual_scene id="scene" name="scene">{nodes}</visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>
""".encode("utf-8")


def _corners(mesh) -> np.ndarray:
    """Positions of every triangle corner, in the order Meshcat draws them."""
    return mesh.positions[mesh.triangles.ravel()]


TRI_CORNERS = np.array(
    [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [0, 1, 0], [0, 0, 1]]
)
INSTANCE_TRI = '<node><instance_geometry url="#tri-lib"/></node>'
INSTANCE_POLY = '<node><instance_geometry url="#poly-lib"/></node>'


class TestColladaParsing:
    """Parsing of Collada geometry and primitives."""

    def test_triangles_with_interleaved_inputs(self):
        """VERTEX/COLOR/NORMAL offsets are followed; COLOR is not used."""
        mesh = parse_collada(_collada(TRIANGLE_GEOMETRY, INSTANCE_TRI))

        assert mesh.warnings == []
        assert mesh.notes == []
        assert len(mesh.positions) == 4
        np.testing.assert_allclose(_corners(mesh), TRI_CORNERS)
        np.testing.assert_allclose(
            mesh.corner_normals, [[0, 0, 1]] * 3 + [[1, 0, 0]] * 3
        )
        assert mesh.corner_uvs is None

    def test_polylist_triangulated_like_colladaloader(self):
        """Quads split as (0,1,3),(1,2,3); larger polygons fan from corner 0."""
        mesh = parse_collada(_collada(POLYLIST_GEOMETRY, INSTANCE_POLY))

        expected_corners = [0, 1, 3, 1, 2, 3, 4, 5, 6, 4, 6, 7, 4, 7, 8]
        positions = np.array(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [3, 0, 0],
             [3, 1, 0], [2.5, 2, 0], [2, 1, 0]]
        )  # fmt: skip
        np.testing.assert_allclose(_corners(mesh), positions[expected_corners])
        # No NORMAL input: Meshcat computes flat normals, and so does the importer.
        assert mesh.corner_normals is None
        np.testing.assert_allclose(mesh.corner_uvs, [[0.25, 0.75]] * 15)

    def test_geometries_with_matching_attributes_are_merged(self):
        """Every instanced geometry ends up in the one merged mesh."""
        other = TRIANGLE_GEOMETRY.replace("tri-", "tri2-")
        nodes = INSTANCE_TRI + (
            '<node><translate>0 0 5</translate><instance_geometry url="#tri2-lib"/>'
            "</node>"
        )
        mesh = parse_collada(_collada(TRIANGLE_GEOMETRY + other, nodes))

        np.testing.assert_allclose(
            _corners(mesh), np.r_[TRI_CORNERS, TRI_CORNERS + [0, 0, 5]]
        )
        assert mesh.warnings == []

    def test_mismatched_attributes_show_nothing(self):
        """Meshcat cannot merge meshes with and without normals; it shows nothing."""
        mesh = parse_collada(
            _collada(
                TRIANGLE_GEOMETRY + POLYLIST_GEOMETRY, INSTANCE_TRI + INSTANCE_POLY
            )
        )

        assert len(mesh.triangles) == 0
        assert any("cannot merge" in w for w in mesh.warnings)

    def test_degenerate_triangles_dropped(self):
        """Zero-area triangles draw nothing and are not kept."""
        geometry = TRIANGLE_GEOMETRY.replace(
            "<p>0 0 0  1 0 0  2 0 0  0 0 1  2 0 1  3 0 1</p>",
            "<p>0 0 0  1 0 0  2 0 0  1 0 1  1 0 1  2 0 1</p>",
        )
        mesh = parse_collada(_collada(geometry, INSTANCE_TRI))

        np.testing.assert_allclose(_corners(mesh), TRI_CORNERS[:3])
        assert len(mesh.positions) == 3
        assert len(mesh.corner_normals) == 3

    def test_unreadable_file_raises(self):
        """Files pycollada cannot read raise; the Blender side reports them."""
        with pytest.raises(DaeError):
            parse_collada(b"<COLLADA><library_geometries>")


class TestColladaTransforms:
    """Node transforms, units and up axis, matched to Meshcat."""

    def test_node_transforms_compose_in_document_order(self):
        """translate, rotate (degrees), scale and matrix are all baked in."""
        nodes = """
        <node>
          <translate>1 2 3</translate>
          <rotate>0 0 1 90</rotate>
          <node>
            <scale>2 2 2</scale>
            <matrix>1 0 0 0.5  0 1 0 0  0 0 1 0  0 0 0 1</matrix>
            <instance_geometry url="#tri-lib"/>
          </node>
        </node>
        """
        mesh = parse_collada(_collada(TRIANGLE_GEOMETRY, nodes))

        # local p -> translate(1,2,3) @ Rz(90) @ scale(2) @ (p + (0.5, 0, 0))
        x, y, z = (2 * (TRI_CORNERS + [0.5, 0, 0])).T
        expected = np.c_[-y, x, z] + [1, 2, 3]
        np.testing.assert_allclose(_corners(mesh), expected, atol=1e-6)
        # Normals rotate with the node; uniform scale does not change them.
        np.testing.assert_allclose(mesh.corner_normals[0], [0, 0, 1], atol=1e-6)
        np.testing.assert_allclose(mesh.corner_normals[3], [0, 1, 0], atol=1e-6)

    def test_normals_follow_nonuniform_scale(self):
        """Normals take the inverse transpose of the node transform, as in
        three.js, so they stay perpendicular to the scaled surface."""
        geometry = TRIANGLE_GEOMETRY.replace(
            "0 0 1  1 0 0</float_array>", "0 0.6 0.8  1 0 0</float_array>"
        )
        nodes = '<node><scale>1 1 4</scale><instance_geometry url="#tri-lib"/></node>'
        mesh = parse_collada(_collada(geometry, nodes))

        expected = np.array([0, 0.6, 0.2]) / np.linalg.norm([0, 0.6, 0.2])
        np.testing.assert_allclose(mesh.corner_normals[0], expected, atol=1e-6)

    def test_instance_node(self):
        """instance_node places a copy of a library node under the instancing
        node, keeping the copy's own transform.

        The node also holds a geometry: when an instance_node is a node's only
        content, three.js drops the copy's transform, which is not reproduced.
        """
        library = """
        <library_nodes>
          <node id="part">
            <translate>0 0 5</translate>
            <instance_geometry url="#tri-lib"/>
          </node>
        </library_nodes>
        """
        nodes = """
        <node>
          <translate>1 0 0</translate>
          <instance_geometry url="#tri2-lib"/>
          <instance_node url="#part"/>
        </node>
        """
        geometries = TRIANGLE_GEOMETRY + TRIANGLE_GEOMETRY.replace("tri-", "tri2-")
        mesh = parse_collada(_collada(geometries, nodes, libraries=library))

        np.testing.assert_allclose(
            _corners(mesh), np.r_[TRI_CORNERS + [1, 0, 0], TRI_CORNERS + [1, 0, 5]]
        )

    @pytest.mark.parametrize(
        "asset",
        [
            '<unit meter="0.001" name="millimeter"/><up_axis>Z_UP</up_axis>',
            '<unit meter="0.0254" name="inch"/><up_axis>X_UP</up_axis>',
        ],
    )
    def test_unit_and_up_axis_ignored_like_meshcat(self, asset):
        """Meshcat applies neither <unit> nor <up_axis>, so neither do we."""
        reference = parse_collada(_collada(TRIANGLE_GEOMETRY, INSTANCE_TRI))
        mesh = parse_collada(_collada(TRIANGLE_GEOMETRY, INSTANCE_TRI, asset=asset))

        np.testing.assert_allclose(mesh.positions, reference.positions)
        np.testing.assert_allclose(mesh.corner_normals, reference.corner_normals)
        assert mesh.warnings == []
        assert any("<unit" in n for n in mesh.notes)
        assert any("<up_axis>" in n for n in mesh.notes)

    def test_unit_of_one_meter_is_silent(self):
        """A unit of one meter and Y_UP match Meshcat with nothing to report."""
        mesh = parse_collada(
            _collada(
                TRIANGLE_GEOMETRY,
                INSTANCE_TRI,
                asset='<unit meter="1" name="meter"/><up_axis>Y_UP</up_axis>',
            )
        )

        assert mesh.warnings == []
        assert mesh.notes == []


SKIN_CONTROLLER = """
<library_controllers>
  <controller id="skin">
    <skin source="#poly-lib">
      <bind_shape_matrix>1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1</bind_shape_matrix>
      <source id="joints">
        <Name_array id="joints-array" count="1">root</Name_array>
        <technique_common>
          <accessor source="#joints-array" count="1" stride="1">
            <param name="JOINT" type="name"/>
          </accessor>
        </technique_common>
      </source>
      <source id="weights">
        <float_array id="weights-array" count="1">1</float_array>
        <technique_common>
          <accessor source="#weights-array" count="1" stride="1">
            <param name="WEIGHT" type="float"/>
          </accessor>
        </technique_common>
      </source>
      <source id="bind">
        <float_array id="bind-array" count="16">
          1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1
        </float_array>
        <technique_common>
          <accessor source="#bind-array" count="1" stride="16">
            <param name="TRANSFORM" type="float4x4"/>
          </accessor>
        </technique_common>
      </source>
      <joints>
        <input semantic="JOINT" source="#joints"/>
        <input semantic="INV_BIND_MATRIX" source="#bind"/>
      </joints>
      <vertex_weights count="9">
        <input semantic="JOINT" source="#joints" offset="0"/>
        <input semantic="WEIGHT" source="#weights" offset="1"/>
        <vcount>1 1 1 1 1 1 1 1 1</vcount>
        <v>0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0</v>
      </vertex_weights>
    </skin>
  </controller>
</library_controllers>
"""


class TestColladaSkipped:
    """Content Meshcat does not draw is skipped with a warning."""

    def test_skinned_mesh_skipped(self):
        """Skinned meshes are dropped, as merge_geometries ignores SkinnedMesh."""
        nodes = """
        <node><instance_controller url="#skin"/></node>
        <node><instance_geometry url="#tri-lib"/></node>
        """
        mesh = parse_collada(
            _collada(
                TRIANGLE_GEOMETRY + POLYLIST_GEOMETRY, nodes, libraries=SKIN_CONTROLLER
            )
        )

        assert len(mesh.triangles) == 2
        assert any("skinned" in w for w in mesh.warnings)

    def test_polygons_skipped(self):
        """<polygons> is unsupported by ColladaLoader and is skipped."""
        geometry = POLYLIST_GEOMETRY.replace(
            "</polylist>",
            """</polylist>
            <polygons count="1">
              <input offset="0" semantic="VERTEX" source="#poly-vertices"/>
              <input offset="1" semantic="TEXCOORD" source="#poly-uvs" set="0"/>
              <p>0 0 1 0 2 0 3 0</p>
            </polygons>""",
        )
        mesh = parse_collada(_collada(geometry, INSTANCE_POLY))

        assert len(mesh.triangles) == 5
        assert any("<polygons>" in w for w in mesh.warnings)

    def test_lines_skipped(self):
        """Lines are drawn as LineSegments, which merge_geometries skips."""
        geometry = POLYLIST_GEOMETRY.replace(
            "</polylist>",
            """</polylist>
            <lines count="1">
              <input offset="0" semantic="VERTEX" source="#poly-vertices"/>
              <p>0 1</p>
            </lines>""",
        )
        mesh = parse_collada(_collada(geometry, INSTANCE_POLY))

        assert len(mesh.triangles) == 5
        assert any("lines" in w for w in mesh.warnings)

    def test_only_unsupported_content_gives_empty_mesh(self):
        """A file with nothing Meshcat draws yields an empty mesh and warnings."""
        geometry = (
            POLYLIST_GEOMETRY.replace("polylist", "polygons")
            .replace("<vcount>4 5</vcount>", "")
            .replace(
                "<p>0 0 1 0 2 0 3 0  4 0 5 0 6 0 7 0 8 0</p>",
                "<p>0 0 1 0 2 0 3 0</p><p>4 0 5 0 6 0 7 0 8 0</p>",
            )
        )
        mesh = parse_collada(_collada(geometry, INSTANCE_POLY))

        assert len(mesh.triangles) == 0
        assert any("<polygons>" in w for w in mesh.warnings)
        assert any("no triangle geometry" in w for w in mesh.warnings)
