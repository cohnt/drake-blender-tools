# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""Skins, morphs, strides, number parsing and other loader quirks."""

import numpy as np  # noqa: F401

from .basic import doc
from .basic import tri_geom as G
from .primitives import POS, geom_custom

SKIN = (
    lambda ctrl,
    geom: f'''<library_controllers><controller id="{ctrl}"><skin source="#{geom}">
<bind_shape_matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</bind_shape_matrix>
<source id="{ctrl}-j"><Name_array id="{ctrl}-ja" count="1">J</Name_array><technique_common><accessor source="#{ctrl}-ja" count="1" stride="1"><param name="JOINT" type="name"/></accessor></technique_common></source>
<source id="{ctrl}-b"><float_array id="{ctrl}-ba" count="16">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</float_array><technique_common><accessor source="#{ctrl}-ba" count="1" stride="16"/></technique_common></source>
<source id="{ctrl}-w"><float_array id="{ctrl}-wa" count="1">1</float_array><technique_common><accessor source="#{ctrl}-wa" count="1" stride="1"/></technique_common></source>
<joints><input semantic="JOINT" source="#{ctrl}-j"/><input semantic="INV_BIND_MATRIX" source="#{ctrl}-b"/></joints>
<vertex_weights count="3"><input semantic="JOINT" source="#{ctrl}-j" offset="0"/><input semantic="WEIGHT" source="#{ctrl}-w" offset="1"/><vcount>1 1 1</vcount><v>0 0 0 0 0 0</v></vertex_weights>
</skin></controller></library_controllers>'''
)
nonorm = lambda gid, vals: geom_custom(
    gid,
    POS(gid, vals)
    + f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-p"/></vertices><triangles count="1"><input semantic="VERTEX" source="#{gid}-v" offset="0"/><p>0 1 2</p></triangles>',
)
cases = {
    "tri_trailing2": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0 1 1 0")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2 3</p></triangles>',
        )
        + nonorm("H", "0 0 4 1 0 4 0 1 4"),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ),
    "polylist_short2": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0 1 1 0")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<polylist count="2"><input semantic="VERTEX" source="#G-v" offset="0"/><vcount>3 3</vcount><p>0 1 2 1 3</p></polylist>',
        )
        + nonorm("H", "0 0 4 1 0 4 0 1 4"),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ),
    "skin_plus_geom": doc(
        G("G") + G("H"),
        '<node id="J" sid="J" type="JOINT"/><node id="a"><instance_controller url="#C"><skeleton>#J</skeleton></instance_controller></node><node id="b"><translate>0 0 3</translate><instance_geometry url="#G"/></node><node id="c"><instance_geometry url="#H"/></node>',
    ).replace("<library_geometries>", SKIN("C", "G") + "<library_geometries>"),
    "morph": doc(
        G("G") + G("H"),
        '<node id="a"><instance_controller url="#C"/></node><node id="c"><instance_geometry url="#H"/></node>',
    ).replace(
        "<library_geometries>",
        '<library_controllers><controller id="C"><morph source="#G" method="NORMALIZED"><targets/></morph></controller></library_controllers><library_geometries>',
    ),
    "pos_stride4_mixed": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 9 1 0 0 9 0 1 0 9", stride=4)
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices><triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles>',
        )
        + nonorm("H", "0 0 4 1 0 4 0 1 4"),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ),
    "short_matrix": doc(
        G("G"),
        '<node id="a"><matrix>1 0 0 1 0 1 0 0 0 0 1 0</matrix><instance_geometry url="#G"/></node>',
    ),
    "lines_only_plus_tri": doc(
        geom_custom(
            "L",
            POS("L", "0 0 0 1 0 0")
            + '<vertices id="L-v"><input semantic="POSITION" source="#L-p"/></vertices><lines count="1"><input semantic="VERTEX" source="#L-v" offset="0"/><p>0 1</p></lines>',
        )
        + G("G"),
        '<node id="a"><instance_geometry url="#L"/></node><node id="b"><instance_geometry url="#G"/></node>',
    ),
    "uv_set1": doc(
        G("G")
        .replace(
            "<vertices",
            '<source id="G-t"><float_array id="G-ta">0 0 1 0 0 1</float_array><technique_common><accessor source="#G-ta" stride="2"/></technique_common></source><vertices',
        )
        .replace("<p>0 0 1 0 2 0</p>", "<p>0 0 0 1 0 1 2 0 2</p>")
        .replace(
            'offset="1"/>',
            'offset="1"/><input semantic="TEXCOORD" source="#G-t" offset="2" set="1"/>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    "two_vertices": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0")
            + '<source id="G-q"><float_array id="G-qa">0 0 8 1 0 8 0 1 8</float_array><technique_common><accessor source="#G-qa" stride="3"/></technique_common></source>'
            '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices><vertices id="G-w"><input semantic="POSITION" source="#G-q"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    "dup_geom_id": doc(
        G("G") + G("G").replace("0 0 0 1 0 0 0 1 0", "0 0 6 1 0 6 0 1 6"),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    "nested_mesh_dir": doc(
        G("G"), '<node id="a"><instance_geometry url="#G"/></node>'
    ).replace("<mesh>", "<extra/><mesh>"),
    "float_trailing_f": doc(
        G("G").replace("0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 0.5f"),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    "bad_float": doc(
        G("G").replace("0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 -1.#IND00"),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
}
