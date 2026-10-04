# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""Primitive, input and source edge cases."""

from .basic import doc, tri_geom

G = tri_geom


def geom_custom(gid, body):
    return f'<geometry id="{gid}"><mesh>{body}</mesh></geometry>'


POS = lambda gid, vals, stride=3, tc=True: (
    f'<source id="{gid}-p"><float_array id="{gid}-pa">{vals}</float_array>'
    + (
        f'<technique_common><accessor source="#{gid}-pa" stride="{stride}"/></technique_common>'
        if tc
        else ""
    )
    + "</source>"
)
cases = {
    # shared geometry, rotations: cumulative product order
    "shared_rot": doc(
        G("G"),
        '<node id="a"><rotate>0 0 1 90</rotate><instance_geometry url="#G"/></node>'
        '<node id="b"><rotate>1 0 0 90</rotate><translate>0 2 0</translate><instance_geometry url="#G"/></node>',
    ),
    # triangles + polylist + triangles in one geometry: grouping by type
    "prim_type_order": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0 1 1 0 5 5 5 6 5 5 5 6 5")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles>'
            '<polylist count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><vcount>4</vcount><p>0 1 3 2</p></polylist>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>4 5 6</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    # vertices-level NORMAL and primitive-level NORMAL both present
    "both_normals": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0")
            + '<source id="G-n1"><float_array id="G-n1a">1 0 0 1 0 0 1 0 0</float_array><technique_common><accessor source="#G-n1a" stride="3"/></technique_common></source>'
            '<source id="G-n2"><float_array id="G-n2a">0 0 1</float_array><technique_common><accessor source="#G-n2a" stride="3"/></technique_common></source>'
            '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/><input semantic="NORMAL" source="#G-n1"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><input semantic="NORMAL" source="#G-n2" offset="1"/><p>0 0 1 0 2 0</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    # source without technique_common (three.js defaults stride 3)
    "no_accessor": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0", tc=False)
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    # accessor without stride attr (spec default 1; three.js NaN)
    "accessor_nostride": doc(
        geom_custom(
            "G",
            '<source id="G-p"><float_array id="G-pa">0 0 0 1 0 0 0 1 0</float_array><technique_common><accessor source="#G-pa" count="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    # source ids colliding across two geometries (sloppy exporter)
    "src_id_collision": doc(
        geom_custom(
            "G",
            '<source id="pos"><float_array id="pa">0 0 0 1 0 0 0 1 0</float_array><technique_common><accessor source="#pa" stride="3"/></technique_common></source><vertices id="v"><input semantic="POSITION" source="#pos"/></vertices><triangles count="1"><input semantic="VERTEX" source="#v" offset="0"/><p>0 1 2</p></triangles>',
        )
        + geom_custom(
            "H",
            '<source id="pos"><float_array id="pa">0 0 7 1 0 7 0 1 7</float_array><technique_common><accessor source="#pa" stride="3"/></technique_common></source><vertices id="v"><input semantic="POSITION" source="#pos"/></vertices><triangles count="1"><input semantic="VERTEX" source="#v" offset="0"/><p>0 1 2</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ),
    # geometry id equals the id of an earlier element (e.g. a material)
    "geom_id_collision": doc(
        G("Mat"), '<node id="a"><instance_geometry url="#Mat"/></node>'
    ).replace(
        "<library_geometries>",
        '<library_materials><material id="Mat"><instance_effect url="#E"/></material></library_materials><library_geometries>',
    ),
    # second library_geometries
    "two_libs": doc(
        G("G"),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ).replace(
        "</library_geometries>",
        "</library_geometries><library_geometries>"
        + G("H").replace("0 0 0 1 0 0 0 1 0", "0 0 3 1 0 3 0 1 3")
        + "</library_geometries>",
    ),
    # polylist with vcount exceeding p
    "polylist_short": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0 1 1 0")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<polylist count="2"><input semantic="VERTEX" source="#G-v" offset="0"/><vcount>3 3</vcount><p>0 1 2 1 3</p></polylist>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    # triangles with incomplete trailing row, followed by another geometry
    "tri_trailing": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0 1 1 0")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2 3</p></triangles>',
        )
        + G("H"),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><translate>0 0 4</translate><instance_geometry url="#H"/></node>',
    ),
    # NORMAL input pointing at <vertices>
    "normal_to_vertices": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><input semantic="NORMAL" source="#G-v" offset="0"/><p>0 1 2</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
    # JOINT node
    "joint_node": doc(
        G("G"),
        '<node id="a" sid="j" type="JOINT"><translate>0 0 2</translate><instance_geometry url="#G"/><node id="b"><instance_geometry url="#G"/></node></node>',
    ),
    # UV on one geometry, not on another
    "mixed_uv": doc(
        G("G")
        .replace(
            "<vertices",
            '<source id="G-t"><float_array id="G-ta">0 0 1 0 0 1</float_array><technique_common><accessor source="#G-ta" stride="2"/></technique_common></source><vertices',
        )
        .replace("<p>0 0 1 0 2 0</p>", "<p>0 0 0 1 0 1 2 0 2</p>")
        .replace(
            'offset="1"/>',
            'offset="1"/><input semantic="TEXCOORD" source="#G-t" offset="2" set="0"/>',
        )
        + G("H"),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ),
    # instance_node to a visual-scene node (clone shares geometry)
    "inode_to_scene_node": doc(
        G("G"),
        '<node id="a"><translate>3 0 0</translate><instance_geometry url="#G"/></node><node id="b"><translate>0 3 0</translate><instance_node url="#a"/><node id="c"/></node>',
    ),
    # missing asset
    "no_asset": doc(
        G("G"), '<node id="a"><instance_geometry url="#G"/></node>', asset=""
    ),
    # invalid float token
    "bad_float": doc(
        G("G").replace("0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 -1.#IND00"),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
}
