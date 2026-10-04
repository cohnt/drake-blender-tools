# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""Cases from a static read of ColladaLoader's throw paths."""

from .basic import doc, tri_geom  # noqa: F401


def geom(gid, prim, srcs=""):
    return f'''<geometry id="{gid}"><mesh>
<source id="{gid}-p"><float_array id="{gid}-pa" count="12">0 0 0 1 0 0 0 1 0 1 1 0</float_array>
<technique_common><accessor source="#{gid}-pa" count="4" stride="3"/></technique_common></source>
<source id="{gid}-n"><float_array id="{gid}-na" count="3">0 0 1</float_array>
<technique_common><accessor source="#{gid}-na" count="1" stride="3"/></technique_common></source>
{srcs}
<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-p"/></vertices>
{prim}</mesh></geometry>'''


N = '<node id="a"><instance_geometry url="#G"/></node>'
V = '<input semantic="VERTEX" source="#G-v" offset="0"/>'
NI = '<input semantic="NORMAL" source="#G-n" offset="1"/>'
cases = {
    "control_ok": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    ),
    "polylist_no_vcount_count2": doc(
        geom(
            "G", f'<polylist count="2">{V}{NI}<p>0 0 1 0 2 0 1 0 3 0 2 0</p></polylist>'
        ),
        N,
    ),
    "polylist_no_vcount_count0": doc(
        geom(
            "G", f'<polylist count="0">{V}{NI}<p>0 0 1 0 2 0 1 0 3 0 2 0</p></polylist>'
        ),
        N,
    ),
    "polylist_no_vcount_nocount": doc(
        geom("G", f"<polylist>{V}{NI}<p>0 0 1 0 2 0 1 0 3 0 2 0</p></polylist>"), N
    ),
    "polylist_vcount_short_count_big": doc(
        geom(
            "G",
            f'<polylist count="5">{V}{NI}<vcount>3 3</vcount><p>0 0 1 0 2 0 1 0 3 0 2 0</p></polylist>',
        ),
        N,
    ),
    "instance_material_no_target": doc(
        geom(
            "G",
            f'<triangles count="1" material="m">{V}{NI}<p>0 0 1 0 2 0</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"><bind_material><technique_common><instance_material symbol="m"/></technique_common></bind_material></instance_geometry></node>',
    ),
    "bind_target_missing_material": doc(
        geom(
            "G",
            f'<triangles count="1" material="m">{V}{NI}<p>0 0 1 0 2 0</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"><bind_material><technique_common><instance_material symbol="m" target="#nope"/></technique_common></bind_material></instance_geometry></node>',
    ),
    "bind_target_missing_no_prim_material": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'),
        '<node id="a"><instance_geometry url="#G"><bind_material><technique_common><instance_material symbol="m" target="#nope"/></technique_common></bind_material></instance_geometry></node>',
    ),
    "two_tris_one_without_normals": doc(
        geom(
            "G",
            f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles><triangles count="1">{V}<p>1 3 2</p></triangles>',
        ),
        N,
    ),
    "vertices_extra_child": doc(
        geom(
            "G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'
        ).replace("</vertices>", "<extra/></vertices>"),
        N,
    ),
    "camera_no_optics": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    ).replace(
        "<library_geometries>",
        '<library_cameras><camera id="c"/></library_cameras><library_geometries>',
    ),
    "light_no_technique": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    ).replace(
        "<library_geometries>",
        '<library_lights><light id="l"/></library_lights><library_geometries>',
    ),
    "image_no_init_from": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    ).replace(
        "<library_geometries>",
        '<library_images><image id="i"><data>00</data></image></library_images><library_geometries>',
    ),
    "skin_no_v": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>')
        + tri_geom("H"),
        '<node id="a"><instance_controller url="#sk"/></node><node id="b"><instance_geometry url="#H"/></node>',
    ).replace(
        "<library_geometries>",
        """<library_controllers><controller id="sk"><skin source="#G">
<source id="j"><Name_array id="ja" count="1">root</Name_array></source><source id="w"><float_array id="wa" count="1">1</float_array></source>
<source id="ib"><float_array id="iba" count="16">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</float_array><technique_common><accessor source="#iba" count="1" stride="16"/></technique_common></source>
<joints><input semantic="JOINT" source="#j"/><input semantic="INV_BIND_MATRIX" source="#ib"/></joints>
<vertex_weights count="4"><input semantic="JOINT" source="#j" offset="0"/><input semantic="WEIGHT" source="#w" offset="1"/><vcount>1 1 1 1</vcount></vertex_weights>
</skin></controller></library_controllers><library_geometries>""",
    ),
    "effect_sampler_missing_surface": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    ).replace(
        "<library_geometries>",
        """<library_effects><effect id="e"><profile_COMMON>
<newparam sid="s"><sampler2D><source>nosurf</source></sampler2D></newparam>
<technique sid="t"><phong><diffuse><texture texture="s" texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects>
<library_materials><material id="m"><instance_effect url="#e"/></material></library_materials><library_geometries>""",
    ),
    "transparent_no_color": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    ).replace(
        "<library_geometries>",
        """<library_effects><effect id="e"><profile_COMMON>
<technique sid="t"><phong><transparent/><transparency><float>0.5</float></transparency></phong></technique></profile_COMMON></effect></library_effects>
<library_materials><material id="m"><instance_effect url="#e"/></material></library_materials><library_geometries>""",
    ),
    "prefixed_root": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'), N
    )
    .replace(
        '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema"',
        '<c:COLLADA xmlns:c="http://www.collada.org/2005/11/COLLADASchema"',
    )
    .replace("</COLLADA>", "</c:COLLADA>"),
    "shear_matrix": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'),
        '<node id="a"><matrix>1 0.5 0 0  0 1 0 0  0 0 2 0  0 0 0 1</matrix><instance_geometry url="#G"/></node>',
    ),
    "neg_scale_rot": doc(
        geom("G", f'<triangles count="1">{V}{NI}<p>0 0 1 0 2 0</p></triangles>'),
        '<node id="a"><rotate>1 1 0 30</rotate><scale>-1 2 1</scale><instance_geometry url="#G"/></node>',
    ),
}
