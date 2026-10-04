# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""Basic cases: transforms, instancing, attribute mixes, ids."""


def doc(
    geoms,
    nodes,
    libnodes="",
    asset='<asset><unit meter="1"/><up_axis>Y_UP</up_axis></asset>',
):
    ln = f"<library_nodes>{libnodes}</library_nodes>" if libnodes else ""
    return f"""<?xml version="1.0"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
{asset}
<library_geometries>{geoms}</library_geometries>
{ln}
<library_visual_scenes><visual_scene id="S">{nodes}</visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#S"/></scene></COLLADA>"""


def tri_geom(gid, normals=True, extra_prim=""):
    nsrc = (
        f'''<source id="{gid}-n"><float_array id="{gid}-na" count="3">0 0 1</float_array>
<technique_common><accessor source="#{gid}-na" count="1" stride="3"/></technique_common></source>'''
        if normals
        else ""
    )
    ninp = f'<input semantic="NORMAL" source="#{gid}-n" offset="1"/>' if normals else ""
    p = "0 0 1 0 2 0" if normals else "0 1 2"
    return f'''<geometry id="{gid}"><mesh>
<source id="{gid}-p"><float_array id="{gid}-pa" count="9">0 0 0 1 0 0 0 1 0</float_array>
<technique_common><accessor source="#{gid}-pa" count="3" stride="3"/></technique_common></source>
{nsrc}
<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-p"/></vertices>
<triangles count="1"><input semantic="VERTEX" source="#{gid}-v" offset="0"/>{ninp}<p>{p}</p></triangles>
{extra_prim}
</mesh></geometry>'''


T1 = "<translate>1 0 0</translate>"
T2 = "<translate>0 0 5</translate>"
cases = {
    # 1. same geometry instanced in two nodes
    "shared_geom": doc(
        tri_geom("G"),
        f'<node id="a">{T1}<instance_geometry url="#G"/></node><node id="b">{T2}<instance_geometry url="#G"/></node>',
    ),
    # 2. instance_node whose target has its own transform; instancing node has a single object
    "inode_single": doc(
        tri_geom("G"),
        f'<node id="a">{T1}<instance_node url="#L"/></node>',
        libnodes=f'<node id="L">{T2}<instance_geometry url="#G"/></node>',
    ),
    # 3. same, but instancing node also has a geometry -> Group
    "inode_group": doc(
        tri_geom("G") + tri_geom("H"),
        f'<node id="a">{T1}<instance_node url="#L"/><instance_geometry url="#H"/></node>',
        libnodes=f'<node id="L">{T2}<instance_geometry url="#G"/></node>',
    ),
    # 4. geometry with normals + geometry without normals
    "mixed_normals": doc(
        tri_geom("G") + tri_geom("H", normals=False),
        '<node id="a"><instance_geometry url="#G"/></node><node id="b"><translate>0 3 0</translate><instance_geometry url="#H"/></node>',
    ),
    # 5. Z_UP + unit
    "zup_unit": doc(
        tri_geom("G"),
        f'<node id="a"><instance_geometry url="#G"/></node>',
        asset='<asset><unit meter="0.01"/><up_axis>Z_UP</up_axis></asset>',
    ),
    # 6. duplicate node ids
    "dup_node_id": doc(
        tri_geom("G") + tri_geom("H"),
        f'<node id="a">{T1}<instance_geometry url="#G"/></node><node id="a">{T2}<instance_geometry url="#H"/></node>',
    ),
    # 7. child order: instance_geometry before child node; transforms differ
    "order": doc(
        tri_geom("G") + tri_geom("H"),
        f'<node id="a"><instance_geometry url="#G"/><node id="c">{T2}<instance_geometry url="#H"/></node></node>',
    ),
    # 8. rotate with non-normalized axis
    "rotate_unnorm": doc(
        tri_geom("G"),
        '<node id="a"><rotate>0 0 2 90</rotate><instance_geometry url="#G"/></node>',
    ),
    # 9. no normals at all
    "no_normals": doc(
        tri_geom("G", normals=False),
        '<node id="a"><instance_geometry url="#G"/></node>',
    ),
}
