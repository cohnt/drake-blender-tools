# SPDX-License-Identifier: MIT
"""Tests for the Collada reader, which mirrors how Meshcat shows .dae meshes."""

import numpy as np
import pytest
from meshcat_html_importer.scene.collada import parse_collada

# Hubo-style geometry: one <triangles>, with VERTEX, COLOR and NORMAL
# interleaved at offsets 0, 1 and 2.
TRIANGLE_GEOMETRY = """
<geometry id="tri-lib" name="tri">
  <mesh>
    <source id="tri-positions">
      <float_array id="tri-positions-array" count="12">
        0 0 0  1 0 0  0 1 0  0 0 1
      </float_array>
      <technique_common>
        <accessor count="4" source="#tri-positions-array" stride="3"/>
      </technique_common>
    </source>
    <source id="tri-colors">
      <float_array id="tri-colors-array" count="4">1 1 0 1</float_array>
      <technique_common>
        <accessor count="1" source="#tri-colors-array" stride="4"/>
      </technique_common>
    </source>
    <source id="tri-normals">
      <float_array id="tri-normals-array" count="6">0 0 1  1 0 0</float_array>
      <technique_common>
        <accessor count="2" source="#tri-normals-array" stride="3"/>
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
POLYLIST_GEOMETRY = """
<geometry id="poly-lib">
  <mesh>
    <source id="poly-positions">
      <float_array id="poly-positions-array" count="27">
        0 0 0  1 0 0  1 1 0  0 1 0
        2 0 0  3 0 0  3 1 0  2.5 2 0  2 1 0
      </float_array>
      <technique_common>
        <accessor count="9" source="#poly-positions-array" stride="3"/>
      </technique_common>
    </source>
    <source id="poly-uvs">
      <float_array id="poly-uvs-array" count="2">0.25 0.75</float_array>
      <technique_common>
        <accessor count="1" source="#poly-uvs-array" stride="2"/>
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
    library_nodes: str = "",
) -> bytes:
    """Wrap geometries and visual-scene nodes into a Collada 1.4.1 document."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>{asset}</asset>
  <library_images/>
  <library_geometries>{geometries}</library_geometries>
  {library_nodes}
  <library_visual_scenes>
    <visual_scene id="scene" name="scene">{nodes}</visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>
""".encode("utf-8")


def _corner_positions(mesh) -> np.ndarray:
    """Positions of every triangle corner, in triangle order."""
    return mesh.positions[mesh.triangles.ravel()]


class TestColladaParsing:
    """Parsing of Collada geometry and primitives."""

    def test_triangles_with_interleaved_inputs(self):
        """VERTEX/COLOR/NORMAL offsets are followed; COLOR is not used."""
        mesh = parse_collada(
            _collada(
                TRIANGLE_GEOMETRY, '<node><instance_geometry url="#tri-lib"/></node>'
            )
        )

        assert mesh.warnings == []
        assert mesh.positions.shape == (4, 3)
        assert mesh.triangles.tolist() == [[0, 1, 2], [0, 2, 3]]
        np.testing.assert_allclose(
            mesh.corner_normals, [[0, 0, 1]] * 3 + [[1, 0, 0]] * 3
        )
        assert mesh.corner_uvs is None

    def test_polylist_triangulated_like_colladaloader(self):
        """Quads split as (0,1,3),(1,2,3); larger polygons fan from corner 0."""
        mesh = parse_collada(
            _collada(
                POLYLIST_GEOMETRY, '<node><instance_geometry url="#poly-lib"/></node>'
            )
        )

        expected_corners = [0, 1, 3, 1, 2, 3, 4, 5, 6, 4, 6, 7, 4, 7, 8]
        positions = np.array(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [3, 0, 0],
             [3, 1, 0], [2.5, 2, 0], [2, 1, 0]]
        )  # fmt: skip
        np.testing.assert_allclose(_corner_positions(mesh), positions[expected_corners])
        assert len(mesh.triangles) == 5
        # No NORMAL input, so Blender computes normals.
        assert mesh.corner_normals is None
        np.testing.assert_allclose(mesh.corner_uvs, [[0.25, 0.75]] * 15)

    def test_several_geometries_are_merged(self):
        """Every instanced geometry ends up in the one merged mesh."""
        mesh = parse_collada(
            _collada(
                TRIANGLE_GEOMETRY + POLYLIST_GEOMETRY,
                '<node><instance_geometry url="#tri-lib"/></node>'
                '<node><instance_geometry url="#poly-lib"/></node>',
            )
        )

        assert len(mesh.triangles) == 2 + 5
        assert len(mesh.positions) == 4 + 9
        # Only one geometry has normals, so normals are left to Blender.
        assert mesh.corner_normals is None
        # UVs of the geometry without UVs are zero, as in ColladaLoader.
        np.testing.assert_allclose(mesh.corner_uvs[:6], 0.0)
        np.testing.assert_allclose(mesh.corner_uvs[6:], [[0.25, 0.75]] * 15)
        assert any("NORMAL" in w for w in mesh.warnings)

    def test_unused_and_degenerate_data_dropped(self):
        """Unreferenced vertices and zero-area triangles are not kept."""
        geometry = TRIANGLE_GEOMETRY.replace(
            "<p>0 0 0  1 0 0  2 0 0  0 0 1  2 0 1  3 0 1</p>",
            "<p>0 0 0  1 0 0  2 0 0  1 0 1  1 0 1  2 0 1</p>",
        )
        mesh = parse_collada(
            _collada(geometry, '<node><instance_geometry url="#tri-lib"/></node>')
        )

        assert mesh.triangles.tolist() == [[0, 1, 2]]
        assert len(mesh.positions) == 3
        assert len(mesh.corner_normals) == 3

    def test_invalid_xml_returns_empty_mesh(self):
        """Malformed files give an empty mesh and a warning, not an exception."""
        mesh = parse_collada(b"<COLLADA><library_geometries>")

        assert len(mesh.triangles) == 0
        assert mesh.warnings


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
        def expected(p):
            x, y, z = 2 * (np.array(p) + [0.5, 0, 0])
            return np.array([-y, x, z]) + [1, 2, 3]

        np.testing.assert_allclose(
            mesh.positions,
            [expected(p) for p in ([0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1])],
            atol=1e-12,
        )
        # Normals rotate with the node; uniform scale does not change them.
        np.testing.assert_allclose(mesh.corner_normals[0], [0, 0, 1], atol=1e-12)
        np.testing.assert_allclose(mesh.corner_normals[3], [0, 1, 0], atol=1e-12)

    def test_instance_node(self):
        """instance_node pulls in a library node under the instancing node."""
        library_nodes = """
        <library_nodes>
          <node id="part"><instance_geometry url="#tri-lib"/></node>
        </library_nodes>
        """
        nodes = """
        <node><instance_node url="#part"/></node>
        <node><translate>5 0 0</translate><instance_node url="#part"/></node>
        """
        mesh = parse_collada(
            _collada(TRIANGLE_GEOMETRY, nodes, library_nodes=library_nodes)
        )

        assert len(mesh.triangles) == 4
        np.testing.assert_allclose(mesh.positions[4:], mesh.positions[:4] + [5, 0, 0])

    @pytest.mark.parametrize(
        "asset",
        [
            '<unit meter="0.001" name="millimeter"/><up_axis>Z_UP</up_axis>',
            '<unit meter="0.0254" name="inch"/><up_axis>X_UP</up_axis>',
        ],
    )
    def test_unit_and_up_axis_ignored_like_meshcat(self, asset):
        """Meshcat applies neither <unit> nor <up_axis>, so neither do we."""
        nodes = '<node><instance_geometry url="#tri-lib"/></node>'
        reference = parse_collada(_collada(TRIANGLE_GEOMETRY, nodes))
        mesh = parse_collada(_collada(TRIANGLE_GEOMETRY, nodes, asset=asset))

        np.testing.assert_allclose(mesh.positions, reference.positions)
        np.testing.assert_allclose(mesh.corner_normals, reference.corner_normals)
        assert any("<unit" in w for w in mesh.warnings)
        assert any("<up_axis>" in w for w in mesh.warnings)

    def test_unit_of_one_meter_is_silent(self):
        """A unit of one meter and Y_UP match Meshcat with nothing to report."""
        mesh = parse_collada(
            _collada(
                TRIANGLE_GEOMETRY,
                '<node><instance_geometry url="#tri-lib"/></node>',
                asset='<unit meter="1" name="meter"/><up_axis>Y_UP</up_axis>',
            )
        )

        assert mesh.warnings == []


class TestColladaSkipped:
    """Content Meshcat does not draw is skipped with a warning."""

    def test_instance_controller_skipped(self):
        """Skinned meshes are dropped, as merge_geometries ignores SkinnedMesh."""
        nodes = """
        <node><instance_controller url="#skin"/></node>
        <node><instance_geometry url="#tri-lib"/></node>
        """
        mesh = parse_collada(_collada(TRIANGLE_GEOMETRY, nodes))

        assert len(mesh.triangles) == 2
        assert any("instance_controller" in w for w in mesh.warnings)

    def test_polygons_skipped(self):
        """<polygons> is unsupported by ColladaLoader and is skipped."""
        geometry = POLYLIST_GEOMETRY.replace(
            "</polylist>",
            """</polylist>
            <polygons count="1">
              <input offset="0" semantic="VERTEX" source="#poly-vertices"/>
              <p>0 1 2 3</p>
            </polygons>""",
        )
        mesh = parse_collada(
            _collada(geometry, '<node><instance_geometry url="#poly-lib"/></node>')
        )

        assert len(mesh.triangles) == 5
        assert any("<polygons>" in w for w in mesh.warnings)

    def test_only_unsupported_content_gives_empty_mesh(self):
        """A file with nothing Meshcat draws yields an empty mesh and warnings."""
        geometry = POLYLIST_GEOMETRY.replace("polylist", "polygons").replace(
            "<vcount>4 5</vcount>", ""
        )
        mesh = parse_collada(
            _collada(geometry, '<node><instance_geometry url="#poly-lib"/></node>')
        )

        assert len(mesh.triangles) == 0
        assert any("no triangle geometry" in w for w in mesh.warnings)
