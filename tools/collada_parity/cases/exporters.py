# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""Cases shaped like real exporter output (Blender, SketchUp, SolidWorks, assimp, ...)."""

HDR = '<?xml version="1.0" encoding="utf-8"?>\n<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
ASSET = '<asset><contributor><author>x</author><authoring_tool>t</authoring_tool></contributor><created>2020-01-01T00:00:00</created><modified>2020-01-01T00:00:00</modified><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>'
ASSET_Z_MM = ASSET.replace('meter="1"', 'meter="0.001"').replace("Y_UP", "Z_UP")


def doc(
    body, asset=ASSET, scene='<scene><instance_visual_scene url="#Scene"/></scene>'
):
    return f"{HDR}\n{asset}\n{body}\n{scene}\n</COLLADA>"


def src(sid, vals, stride=3, params=None, extra_acc=""):
    n = len(vals.split())
    if params is None:
        params = {3: "XYZ", 2: "ST", 4: "RGBA", 1: "X"}[stride]
    ps = "".join(f'<param name="{c}" type="float"/>' for c in params)
    return (
        f'<source id="{sid}"><float_array id="{sid}-array" count="{n}">{vals}</float_array>'
        f'<technique_common><accessor source="#{sid}-array" count="{n // stride}" stride="{stride}"{extra_acc}>{ps}</accessor></technique_common></source>'
    )


# Cube-ish quad data as Blender writes it: positions, normals, uvs, colors
QUAD_POS = "0 0 0  1 0 0  1 1 0  0 1 0  0 0 1  1 0 1  1 1 1  0 1 1"
QUAD_NRM = "0 0 -1  0 0 1  0 -1 0  1 0 0"
QUAD_UV = "0 0  1 0  1 1  0 1"
QUAD_COL = "1 0 0 1  0 1 0 1"


def blender_geom(gid="Cube-mesh", two_mats=True, with_color=True):
    inputs = (
        f'<input semantic="VERTEX" source="#{gid}-vertices" offset="0"/>'
        f'<input semantic="NORMAL" source="#{gid}-normals" offset="1"/>'
        f'<input semantic="TEXCOORD" source="#{gid}-map-0" offset="2" set="0"/>'
    )
    if with_color:
        inputs += (
            f'<input semantic="COLOR" source="#{gid}-colors-Col" offset="3" set="0"/>'
        )
    k = 4 if with_color else 3

    def corner(v, n, t, c):
        return f"{v} {n} {t} {c}" if with_color else f"{v} {n} {t}"

    # face 0: bottom quad (0 1 2 3), face 1: top quad (4 5 6 7), face 2: front tri (0 1 5)
    p1 = (
        " ".join(corner(v, 0, i, 0) for i, v in enumerate([0, 1, 2, 3]))
        + " "
        + " ".join(corner(v, 1, i, 1) for i, v in enumerate([4, 5, 6, 7]))
    )
    p2 = " ".join(corner(v, 2, i, 0) for i, v in enumerate([0, 1, 5]))
    prims = f'<polylist material="Material-material" count="2">{inputs}<vcount>4 4</vcount><p>{p1}</p></polylist>'
    if two_mats:
        prims += f'<polylist material="Material_001-material" count="1">{inputs}<vcount>3</vcount><p>{p2}</p></polylist>'
    else:
        prims = (
            prims.replace("<vcount>4 4</vcount>", "<vcount>4 4 3</vcount>")
            .replace(f"{p1}</p>", f"{p1} {p2}</p>")
            .replace('count="2"', 'count="3"')
        )
    return (
        f'<geometry id="{gid}" name="Cube"><mesh>'
        + src(f"{gid}-positions", QUAD_POS)
        + src(f"{gid}-normals", QUAD_NRM)
        + src(f"{gid}-map-0", QUAD_UV, 2)
        + (src(f"{gid}-colors-Col", QUAD_COL, 4) if with_color else "")
        + f'<vertices id="{gid}-vertices"><input semantic="POSITION" source="#{gid}-positions"/></vertices>'
        + prims
        + "</mesh></geometry>"
    )


BLENDER_LIBS = """
<library_images><image id="tex_png" name="tex_png"><init_from>tex.png</init_from></image></library_images>
<library_effects>
  <effect id="Material-effect"><profile_COMMON>
    <newparam sid="tex_png-surface"><surface type="2D"><init_from>tex_png</init_from></surface></newparam>
    <newparam sid="tex_png-sampler"><sampler2D><source>tex_png-surface</source></sampler2D></newparam>
    <technique sid="common"><phong>
      <emission><color sid="emission">0 0 0 1</color></emission>
      <ambient><color sid="ambient">0 0 0 1</color></ambient>
      <diffuse><texture texture="tex_png-sampler" texcoord="UVMap"/></diffuse>
      <specular><color sid="specular">0.5 0.5 0.5 1</color></specular>
      <shininess><float sid="shininess">50</float></shininess>
      <index_of_refraction><float sid="ior">1.45</float></index_of_refraction>
    </phong></technique>
    <extra><technique profile="GOOGLEEARTH"><double_sided>1</double_sided></technique></extra>
  </profile_COMMON></effect>
  <effect id="Material_001-effect"><profile_COMMON><technique sid="common"><lambert>
      <diffuse><color sid="diffuse">0.8 0.1 0.1 1</color></diffuse>
      <transparent opaque="A_ONE"><color>1 1 1 1</color></transparent>
      <transparency><float>1</float></transparency>
  </lambert></technique></profile_COMMON></effect>
</library_effects>
<library_materials>
  <material id="Material-material" name="Material"><instance_effect url="#Material-effect"/></material>
  <material id="Material_001-material" name="Material.001"><instance_effect url="#Material_001-effect"/></material>
</library_materials>
<library_cameras><camera id="Camera-camera" name="Camera"><optics><technique_common><perspective><xfov sid="xfov">39.6</xfov><aspect_ratio>1.777</aspect_ratio><znear sid="znear">0.1</znear><zfar sid="zfar">100</zfar></perspective></technique_common></optics><extra><technique profile="blender"><shiftx>0</shiftx></technique></extra></camera></library_cameras>
<library_lights><light id="Light-light" name="Light"><technique_common><point><color sid="color">1000 1000 1000</color><constant_attenuation>1</constant_attenuation><linear_attenuation>0</linear_attenuation><quadratic_attenuation>0.00111</quadratic_attenuation></point></technique_common><extra><technique profile="blender"><type sid="type" type="int">0</type></technique></extra></light></library_lights>
"""

BIND = (
    "<bind_material><technique_common>"
    '<instance_material symbol="Material-material" target="#Material-material"><bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/></instance_material>'
    '<instance_material symbol="Material_001-material" target="#Material_001-material"/>'
    "</technique_common></bind_material>"
)
MAT4 = lambda tx=0, ty=0, tz=0: f"1 0 0 {tx} 0 1 0 {ty} 0 0 1 {tz} 0 0 0 1"
EXTRA = '<extra><technique profile="blender"><layer sid="layer" type="string">0</layer></technique></extra>'


def tri(
    gid,
    z=0.0,
    normals=True,
    extra_inputs="",
    extra_src="",
    p=None,
    prim="triangles",
    vcount=None,
    count=1,
):
    pos = f"0 0 {z} 1 0 {z} 0 1 {z}"
    body = src(f"{gid}-p", pos)
    inputs = f'<input semantic="VERTEX" source="#{gid}-v" offset="0"/>'
    if normals:
        body += src(f"{gid}-n", "0 0 1")
        inputs += f'<input semantic="NORMAL" source="#{gid}-n" offset="1"/>'
    body += extra_src
    inputs += extra_inputs
    if p is None:
        p = "0 0 1 0 2 0" if normals else "0 1 2"
    vc = f"<vcount>{vcount}</vcount>" if vcount is not None else ""
    body += f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-p"/></vertices>'
    body += f'<{prim} count="{count}">{inputs}{vc}<p>{p}</p></{prim}>'
    return f'<geometry id="{gid}"><mesh>{body}</mesh></geometry>'


def vs(nodes, sid="Scene"):
    return f'<library_visual_scenes><visual_scene id="{sid}" name="{sid}">{nodes}</visual_scene></library_visual_scenes>'


def geoms(*g):
    return "<library_geometries>" + "".join(g) + "</library_geometries>"


def libnodes(*n):
    return "<library_nodes>" + "".join(n) + "</library_nodes>"


cases = {}

# ---------------- Blender exporter ----------------
cases["blender_full"] = doc(
    BLENDER_LIBS
    + geoms(blender_geom())
    + vs(
        f'<node id="Camera" name="Camera" type="NODE"><matrix sid="transform">{MAT4(7, 5, 6)}</matrix><instance_camera url="#Camera-camera"/>{EXTRA}</node>'
        f'<node id="Light" name="Light" type="NODE"><matrix sid="transform">{MAT4(4, 1, 5)}</matrix><instance_light url="#Light-light"/>{EXTRA}</node>'
        f'<node id="Cube" name="Cube" type="NODE"><matrix sid="transform">{MAT4(0, 0, 2)}</matrix><instance_geometry url="#Cube-mesh" name="Cube">{BIND}</instance_geometry>{EXTRA}</node>'
    ),
    asset=ASSET_Z_MM,
)
# same, one polylist with three polygons (quad quad tri)
cases["blender_one_polylist"] = doc(
    BLENDER_LIBS
    + geoms(blender_geom(two_mats=False))
    + vs(
        f'<node id="Cube" name="Cube" type="NODE"><matrix sid="transform">{MAT4(0, 0, 2)}</matrix><instance_geometry url="#Cube-mesh" name="Cube">{BIND}</instance_geometry>{EXTRA}</node>'
    )
)
# node with name but no id, nested under a parent with a matrix
cases["blender_noid_nested"] = doc(
    BLENDER_LIBS
    + geoms(blender_geom())
    + vs(
        f'<node name="Empty" type="NODE"><matrix sid="transform">{MAT4(1, 0, 0)}</matrix>'
        f'<node name="Cube" type="NODE"><matrix sid="transform">{MAT4(0, 0, 2)}</matrix><instance_geometry url="#Cube-mesh">{BIND}</instance_geometry></node></node>'
    )
)
# armature: JOINT hierarchy + skinned controller + a plain mesh child of a JOINT
SKIN = """<library_controllers><controller id="Armature_Cube-skin" name="Armature"><skin source="#Cube-mesh">
<bind_shape_matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</bind_shape_matrix>
<source id="Armature_Cube-skin-joints"><Name_array id="Armature_Cube-skin-joints-array" count="2">Bone Bone_001</Name_array><technique_common><accessor source="#Armature_Cube-skin-joints-array" count="2" stride="1"><param name="JOINT" type="name"/></accessor></technique_common></source>
<source id="Armature_Cube-skin-bind_poses"><float_array id="Armature_Cube-skin-bind_poses-array" count="32">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</float_array><technique_common><accessor source="#Armature_Cube-skin-bind_poses-array" count="2" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common></source>
<source id="Armature_Cube-skin-weights"><float_array id="Armature_Cube-skin-weights-array" count="2">1 0.5</float_array><technique_common><accessor source="#Armature_Cube-skin-weights-array" count="2" stride="1"><param name="WEIGHT" type="float"/></accessor></technique_common></source>
<joints><input semantic="JOINT" source="#Armature_Cube-skin-joints"/><input semantic="INV_BIND_MATRIX" source="#Armature_Cube-skin-bind_poses"/></joints>
<vertex_weights count="8"><input semantic="JOINT" source="#Armature_Cube-skin-joints" offset="0"/><input semantic="WEIGHT" source="#Armature_Cube-skin-weights" offset="1"/><vcount>1 1 1 1 2 2 2 2</vcount><v>0 0 0 0 0 0 0 0 0 1 1 1 0 1 1 1 0 1 1 1 0 1 1 1</v></vertex_weights>
</skin></controller></library_controllers>"""
cases["blender_armature"] = doc(
    BLENDER_LIBS
    + SKIN
    + geoms(blender_geom(), tri("T", 3))
    + vs(
        f'<node id="Armature" name="Armature" type="NODE"><matrix sid="transform">{MAT4(0, 0, 1)}</matrix>'
        f'<node id="Armature_Bone" name="Bone" sid="Bone" type="JOINT"><matrix sid="transform">{MAT4(0, 1, 0)}</matrix>'
        f'<node id="Armature_Bone_001" name="Bone_001" sid="Bone_001" type="JOINT"><matrix sid="transform">{MAT4(0, 0, 1)}</matrix>'
        f'<node id="Hat" name="Hat" type="NODE"><matrix sid="transform">{MAT4(1, 0, 0)}</matrix><instance_geometry url="#T"/></node>'
        f'<extra><technique profile="blender"><connect>1</connect><tip_x>0</tip_x></technique></extra></node></node>'
        f'<node id="Cube" name="Cube" type="NODE"><matrix sid="transform">{MAT4()}</matrix><instance_controller url="#Armature_Cube-skin"><skeleton>#Armature_Bone</skeleton>{BIND}</instance_controller></node>'
        f"</node>"
    )
)
# JOINT node that is the lone child of a node (no objects): group path with Bone
cases["joint_lone_child_chain"] = doc(
    geoms(tri("T"))
    + vs(
        '<node id="A"><translate>1 0 0</translate><node id="B" type="JOINT" sid="B"><translate>0 1 0</translate><node id="C" type="JOINT" sid="C"><translate>0 0 1</translate><instance_geometry url="#T"/></node></node></node>'
    )
)

# ---------------- SketchUp ----------------
SU_MESH = (
    f'<geometry id="ID3"><mesh>'
    + src("ID4", "0 0 0  1 0 0  1 1 0  0 1 0")
    + src("ID5", "0 0 1 0 0 1 0 0 1 0 0 1")
    + src("ID7", "0 0 1 0 1 1 0 1", 2)
    + '<vertices id="ID6"><input semantic="POSITION" source="#ID4"/><input semantic="NORMAL" source="#ID5"/></vertices>'
    '<triangles count="2" material="Material2"><input offset="0" semantic="VERTEX" source="#ID6"/><input offset="1" semantic="TEXCOORD" source="#ID7"/><p>0 0 1 1 2 2 0 0 2 2 3 3</p></triangles>'
    '<lines count="4" material="Material3"><input offset="0" semantic="VERTEX" source="#ID6"/><p>0 1 1 2 2 3 3 0</p></lines>'
    "</mesh></geometry>"
)
SU_MESH2 = (
    SU_MESH.replace("ID3", "ID13")
    .replace("ID4", "ID14")
    .replace("ID5", "ID15")
    .replace("ID6", "ID16")
    .replace("ID7", "ID17")
    .replace("0 0 0  1 0 0  1 1 0  0 1 0", "0 0 5  1 0 5  1 1 5  0 1 5")
)
SU_LIBS = """<library_materials><material id="ID2" name="Material2"><instance_effect url="#ID8"/></material><material id="ID9" name="Material3"><instance_effect url="#ID10"/></material></library_materials>
<library_effects><effect id="ID8"><profile_COMMON><technique sid="COMMON"><lambert><diffuse><color>0.5 0.5 0.5 1</color></diffuse></lambert></technique></profile_COMMON></effect>
<effect id="ID10"><profile_COMMON><technique sid="COMMON"><constant><transparent opaque="A_ONE"><color>1 1 1 1</color></transparent><transparency><float>1</float></transparency></constant></technique></profile_COMMON></effect></library_effects>"""
SU_BIND = '<bind_material><technique_common><instance_material symbol="Material2" target="#ID2"><bind_vertex_input semantic="UVSET0" input_semantic="TEXCOORD" input_set="0"/></instance_material><instance_material symbol="Material3" target="#ID9"/></technique_common></bind_material>'
cases["sketchup_tri_lines_nested"] = doc(
    SU_LIBS
    + geoms(SU_MESH, SU_MESH2)
    + vs(
        f'<node id="ID1" name="SketchUp"><node id="ID20" name="group1"><matrix>{MAT4(1, 0, 0)}</matrix><node id="ID21" name="group2"><matrix>{MAT4(0, 1, 0)}</matrix>'
        f'<node id="ID22" name="group3"><matrix>{MAT4(0, 0, 1)}</matrix><instance_geometry url="#ID3">{SU_BIND}</instance_geometry></node></node></node>'
        f'<node id="ID30" name="other"><matrix>{MAT4(2, 0, 0)}</matrix><instance_geometry url="#ID13">{SU_BIND}</instance_geometry></node></node>'
    ),
    asset=ASSET.replace('meter="1"', 'meter="0.0254"').replace("Y_UP", "Z_UP"),
)
# instance_node chain: scene node A -> lib node B (lone instance_node -> C) ; C has a geometry with transform
cases["su_inode_chain"] = doc(
    geoms(tri("T"))
    + libnodes(
        f'<node id="B" name="comp_B"><matrix>{MAT4(0, 10, 0)}</matrix><instance_node url="#C"/></node>',
        f'<node id="C" name="comp_C"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>',
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#B"/></node>'
    )
)
# chain where B has an extra geometry so it is a Group
cases["su_inode_chain_group"] = doc(
    geoms(tri("T"), tri("U", 50))
    + libnodes(
        f'<node id="B" name="comp_B"><matrix>{MAT4(0, 10, 0)}</matrix><instance_node url="#C"/><instance_geometry url="#U"/></node>',
        f'<node id="C" name="comp_C"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>',
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#B"/></node>'
    )
)
# same library node instanced three times (component definitions), each instance its own transform
cases["su_component_x3"] = doc(
    geoms(tri("T"))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="I1"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#Comp"/></node>'
        f'<node id="I2"><matrix>{MAT4(2, 0, 0)}</matrix><instance_node url="#Comp"/></node>'
        f'<node id="I3"><matrix>{MAT4(3, 0, 0)}</matrix><instance_node url="#Comp"/></node>'
    )
)
# library node with child nodes (a component containing nested groups)
cases["su_libnode_children"] = doc(
    geoms(tri("T"), tri("U", 50))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><node id="Comp_g1"><matrix>{MAT4(0, 1, 0)}</matrix><instance_geometry url="#T"/></node><node id="Comp_g2"><matrix>{MAT4(0, 2, 0)}</matrix><instance_geometry url="#U"/></node></node>'
    )
    + vs(
        f'<node id="I1"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#Comp"/></node>'
        f'<node id="I2"><matrix>{MAT4(2, 0, 0)}</matrix><instance_node url="#Comp"/></node>'
    )
)
# two instance_node of the same lib node in one node
cases["two_inodes_same_target"] = doc(
    geoms(tri("T"))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="I1"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#Comp"/><instance_node url="#Comp"/></node>'
    )
)
# node instancing the same geometry twice
cases["same_geom_twice_in_node"] = doc(
    geoms(tri("T"))
    + vs(
        f'<node id="I1"><matrix>{MAT4(1, 0, 0)}</matrix><instance_geometry url="#T"/><instance_geometry url="#T"/></node>'
    )
)
# instance_node to a scene node defined later in the document
cases["inode_forward_scene_node"] = doc(
    geoms(tri("T"))
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#B"/></node>'
        f'<node id="B"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
)
# instance_node to an id-less lib node (key null) and extra instance_node with bad url
cases["inode_lib_noid"] = doc(
    geoms(tri("T"))
    + libnodes(
        f'<node><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_node url="#null"/></node>'
    )
)
# only an <extra> plus a geometry (still single-object shortcut)
cases["extra_plus_geom"] = doc(
    geoms(tri("T"))
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_geometry url="#T"/>{EXTRA}<asset><up_axis>Z_UP</up_axis></asset></node>'
    )
)

# ---------------- SolidWorks / assimp ----------------
SW_GEOM = (
    f'<geometry id="shape0-lib" name="shape0"><mesh>'
    + src("shape0-lib-positions", "0 0 0 1 0 0 0 1 0 1 1 0")
    + src("shape0-lib-normals", "0 0 1 0 0 -1")
    + src("shape0-lib-map", "0 0 1 0 0 1 1 1", 2)
    + src("shape0-lib-map1", "0.5 0.5", 2)
    + '<vertices id="shape0-lib-vertices"><input semantic="POSITION" source="#shape0-lib-positions"/><input semantic="NORMAL" source="#shape0-lib-normals"/></vertices>'
    '<triangles count="1" material="defaultMaterial"><input offset="0" semantic="VERTEX" source="#shape0-lib-vertices"/><input offset="1" semantic="NORMAL" source="#shape0-lib-normals"/>'
    '<input offset="2" semantic="TEXCOORD" source="#shape0-lib-map" set="0"/><input offset="3" semantic="TEXCOORD" source="#shape0-lib-map1" set="1"/><p>0 0 0 0  1 0 1 0  2 0 2 0</p></triangles>'
    '<triangles count="1" material="defaultMaterial"><input offset="0" semantic="VERTEX" source="#shape0-lib-vertices"/><input offset="1" semantic="NORMAL" source="#shape0-lib-normals"/>'
    '<input offset="2" semantic="TEXCOORD" source="#shape0-lib-map" set="0"/><input offset="3" semantic="TEXCOORD" source="#shape0-lib-map1" set="1"/><p>1 1 1 0  3 1 3 0  2 1 2 0</p></triangles>'
    "</mesh></geometry>"
)
SW_LIBS = '<library_materials><material id="defaultMaterial"><instance_effect url="#defaultMaterial-fx"/></material></library_materials><library_effects><effect id="defaultMaterial-fx"><profile_COMMON><technique sid="standard"><phong><diffuse><color sid="diffuse">0.6 0.6 0.6 1</color></diffuse></phong></technique></profile_COMMON></effect></library_effects>'
cases["sw_two_triangles_two_uvsets"] = doc(
    SW_LIBS
    + geoms(SW_GEOM)
    + vs(
        '<node id="shape0" name="shape0"><instance_geometry url="#shape0-lib"><bind_material><technique_common><instance_material symbol="defaultMaterial" target="#defaultMaterial"/></technique_common></bind_material></instance_geometry></node>'
    ),
    asset=ASSET_Z_MM,
)
# accessor with offset attribute and count/float_array count disagreeing
cases["accessor_offset_badcounts"] = doc(
    geoms(
        '<geometry id="G"><mesh><source id="G-p"><float_array id="G-pa" count="99">0 0 0 1 0 0 0 1 0</float_array><technique_common><accessor source="#G-pa" count="1" stride="3" offset="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
        '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices><triangles count="7"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
# <p> split across several <p> in <triangles> (invalid but seen): last wins in JS
cases["multi_p_triangles"] = doc(
    geoms(tri("T", p="0 0 1 0 2 0</p><p>2 0 1 0 0 0"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# vertices element with NORMAL + primitive with no NORMAL input (normals from vertices)
cases["normals_via_vertices_only"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 0 1 0 0 0 1 0")
        + src("G-n", "1 0 0 0 1 0 0 0 1")
        + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/><input semantic="NORMAL" source="#G-n"/></vertices>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
# vertices with COLOR + TEXCOORD inside vertices; uv stride set by vertices TEXCOORD1
cases["vertices_color_tex"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 0 1 0 0 0 1 0")
        + src("G-c", "1 0 0 0 1 0 0 0 1")
        + src("G-t", "0 0 1 0 0 1", 2)
        + src("G-t1", "0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5", 3)
        + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/><input semantic="COLOR" source="#G-c"/><input semantic="TEXCOORD" source="#G-t"/><input semantic="TEXCOORD1" source="#G-t1"/></vertices>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
# polylist with vcount containing 0/1/2 entries and triangle count mismatch
cases["polylist_degenerate_vcounts"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 0 1 0 0 0 1 0 1 1 0 2 2 0")
        + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
        '<polylist count="99"><input semantic="VERTEX" source="#G-v" offset="0"/><vcount>2 0 3 1 3</vcount><p>0 1 0 1 2 4 0 2 3</p></polylist></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
# input offsets with a gap (offset 0 and 2, nothing at 1)
cases["offset_gap"] = doc(
    geoms(
        tri("T", p="0 9 0  1 9 0  2 9 0").replace(
            'semantic="NORMAL" source="#T-n" offset="1"',
            'semantic="NORMAL" source="#T-n" offset="2"',
        )
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# two inputs sharing an offset (VERTEX and NORMAL both at 0), common in assimp output
cases["shared_offset"] = doc(
    geoms(
        tri("T", p="0 1 2")
        .replace(
            'semantic="NORMAL" source="#T-n" offset="1"',
            'semantic="NORMAL" source="#T-n" offset="0"',
        )
        .replace(src("T-n", "0 0 1"), src("T-n", "0 0 1 0 1 0 1 0 0"))
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# unknown semantics TEXTANGENT/TEXBINORMAL at offsets (OpenCOLLADA), raising stride
cases["textangent_inputs"] = doc(
    geoms(
        tri(
            "T",
            extra_inputs='<input semantic="TEXTANGENT" source="#T-tan" offset="2" set="0"/><input semantic="TEXBINORMAL" source="#T-tan" offset="3" set="0"/>',
            extra_src=src("T-tan", "1 0 0"),
            p="0 0 0 0  1 0 0 0  2 0 0 0",
        )
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# unknown semantic inside <vertices>
cases["vertices_unknown_semantic"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 0 1 0 0 0 1 0")
        + '<vertices id="G-v"><input semantic="TANGENT" source="#missing"/><input semantic="POSITION" source="#G-p"/></vertices>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
# input with missing offset attribute (parseInt(null) = NaN)
cases["input_no_offset"] = doc(
    geoms(tri("T", normals=False).replace('source="#T-v" offset="0"', 'source="#T-v"'))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# second TEXCOORD set only on one of two primitives (uvsNeedsFix for uv, not uv1)
cases["uv1_partial"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 0 1 0 0 0 1 0")
        + src("G-t", "0 0", 2)
        + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><input semantic="TEXCOORD" source="#G-t" offset="1" set="0"/><input semantic="TEXCOORD" source="#G-t" offset="1" set="1"/><p>0 0 1 0 2 0</p></triangles>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><input semantic="TEXCOORD" source="#G-t" offset="1" set="0"/><p>2 0 1 0 0 0</p></triangles>'
        "</mesh></geometry>"
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
# uvsNeedsFix with position stride 4 (vertex count = len/4)
cases["uvfix_stride4"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 0 1 1 0 0 1 0 1 0 1 2 2 0 1", 4, "XYZW")
        + src("G-t", "0 0", 2)
        + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><input semantic="TEXCOORD" source="#G-t" offset="1" set="0"/><p>0 0 1 0 2 0</p></triangles>'
        '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>2 1 0</p></triangles>'
        "</mesh></geometry>"
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)

# ---------------- OpenCOLLADA (Max/Maya) ----------------
OC_LIBS = """<library_materials><material id="lambert1" name="lambert1"><instance_effect url="#lambert1-fx"/></material><material id="blinn1" name="blinn1"><instance_effect url="#blinn1-fx"/></material></library_materials>
<library_effects><effect id="lambert1-fx"><profile_COMMON><technique sid="common"><lambert><emission><color>0 0 0 1</color></emission><ambient><color>0 0 0 1</color></ambient><diffuse><color>0.4 0.4 0.4 1</color></diffuse><transparent opaque="RGB_ZERO"><color>0 0 0 1</color></transparent><transparency><float>1</float></transparency></lambert></technique></profile_COMMON><extra><technique profile="OpenCOLLADA3dsMax"><double_sided>1</double_sided></technique></extra></effect>
<effect id="blinn1-fx"><profile_COMMON><technique sid="common"><blinn><diffuse><color>0.4 0.4 0.4 1</color></diffuse><specular><color>0.5 0.5 0.5 1</color></specular><shininess><float>0.3</float></shininess><reflectivity><float>0.5</float></reflectivity><index_of_refraction><float>1</float></index_of_refraction></blinn></technique></profile_COMMON></effect></library_effects>"""
cases["oc_tristrips_trifans_plus_tri"] = doc(
    OC_LIBS
    + geoms(
        '<geometry id="pCubeShape1" name="pCubeShape1"><mesh>'
        + src("pCubeShape1-positions", "0 0 0 1 0 0 0 1 0 1 1 0 2 2 0")
        + src("pCubeShape1-normals", "0 0 1")
        + '<vertices id="pCubeShape1-vertices"><input semantic="POSITION" source="#pCubeShape1-positions"/></vertices>'
        '<tristrips count="1" material="lambert1SG"><input semantic="VERTEX" source="#pCubeShape1-vertices" offset="0"/><input semantic="NORMAL" source="#pCubeShape1-normals" offset="1"/><p>0 0 1 0 2 0 3 0</p></tristrips>'
        '<trifans count="1" material="lambert1SG"><input semantic="VERTEX" source="#pCubeShape1-vertices" offset="0"/><input semantic="NORMAL" source="#pCubeShape1-normals" offset="1"/><p>0 0 1 0 2 0 3 0</p></trifans>'
        '<triangles count="1" material="blinn1SG"><input semantic="VERTEX" source="#pCubeShape1-vertices" offset="0"/><input semantic="NORMAL" source="#pCubeShape1-normals" offset="1"/><p>1 0 3 0 2 0</p></triangles>'
        "</mesh></geometry>"
    )
    + vs(
        '<node id="pCube1" name="pCube1"><translate sid="translate">0 0 1</translate><rotate sid="rotateZ">0 0 1 0</rotate><rotate sid="rotateY">0 1 0 0</rotate><rotate sid="rotateX">1 0 0 0</rotate><scale sid="scale">1 1 1</scale>'
        '<instance_geometry url="#pCubeShape1"><bind_material><technique_common><instance_material symbol="lambert1SG" target="#lambert1"/><instance_material symbol="blinn1SG" target="#missingMaterial"/></technique_common></bind_material></instance_geometry></node>'
    )
)
# effect technique without a shader element (only extra)  -> JS: parameters undefined -> Q.transparent throws
cases["effect_technique_no_shader"] = doc(
    '<library_effects><effect id="E"><profile_COMMON><technique sid="common"><extra/></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# effect technique lacking sid, with phong: fine
cases["effect_technique_no_sid"] = doc(
    '<library_effects><effect id="E"><profile_COMMON><technique><phong/></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# instance_effect url lacking '#'
cases["instance_effect_no_hash"] = doc(
    '<library_effects><effect id="E"><profile_COMMON><technique sid="c"><phong/></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="E"/></material></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# material without instance_effect, while an id-less effect exists
cases["material_no_instance_effect_idless_effect"] = doc(
    '<library_effects><effect><profile_COMMON><technique sid="c"><phong/></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"/></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# texture referencing a sampler whose surface is missing -> JS throws
cases["sampler_missing_surface"] = doc(
    '<library_effects><effect id="E"><profile_COMMON><newparam sid="s"><sampler2D><source>nosurface</source></sampler2D></newparam><technique sid="c"><phong><diffuse><texture texture="s" texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# texture with sampler+surface but image missing from library_images (JS: warn only)
cases["texture_missing_image"] = doc(
    '<library_effects><effect id="E"><profile_COMMON><newparam sid="surf"><surface type="2D"><init_from>img</init_from></surface></newparam><newparam sid="s"><sampler2D><source>surf</source></sampler2D></newparam><technique sid="c"><phong><diffuse><texture texture="s" texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# <transparent> with <param ref> instead of color -> JS: A[3] of undefined
cases["transparent_param_ref"] = doc(
    '<library_effects><effect id="E"><profile_COMMON><technique sid="c"><phong><transparent opaque="A_ONE"><param ref="x"/></transparent></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# image without init_from (embedded <data>) -> JS throws in parseImage
cases["image_without_init_from"] = doc(
    '<library_images><image id="I"><data>00ff</data></image></library_images>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# light without technique_common (built even if unused) -> JS throws in buildLight
cases["light_no_technique_unused"] = doc(
    '<library_lights><light id="L"><extra/></light></library_lights>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# camera without optics (unused) -> JS throws in buildCamera
cases["camera_no_optics_unused"] = doc(
    '<library_cameras><camera id="C"><extra/></camera></library_cameras>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# proper light + camera instanced together with instance_node (group vs single)
cases["camera_present_breaks_shortcut"] = doc(
    BLENDER_LIBS
    + geoms(tri("T"))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_camera url="#Camera-camera"/><instance_node url="#Comp"/></node>'
    )
)
cases["missing_camera_keeps_shortcut"] = doc(
    geoms(tri("T"))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_camera url="#nocam"/><instance_node url="#Comp"/></node>'
    )
)
cases["light_present_breaks_shortcut"] = doc(
    BLENDER_LIBS
    + geoms(tri("T"))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_light url="#Light-light"/><instance_node url="#Comp"/></node>'
    )
)
# camera with optics but empty technique_common (default PerspectiveCamera, no throw)
cases["camera_empty_optics"] = doc(
    '<library_cameras><camera id="C"><optics><technique_common/></optics></camera></library_cameras>'
    + geoms(tri("T"))
    + libnodes(
        f'<node id="Comp"><matrix>{MAT4(0, 0, 100)}</matrix><instance_geometry url="#T"/></node>'
    )
    + vs(
        f'<node id="A"><matrix>{MAT4(1, 0, 0)}</matrix><instance_camera url="#C"/><instance_node url="#Comp"/></node>'
    )
)

# ---------------- MeshLab ----------------
cases["meshlab_two_scenes"] = doc(
    geoms(tri("T"), tri("U", 7))
    + '<library_visual_scenes><visual_scene id="S1"><node id="a"><instance_geometry url="#T"/></node></visual_scene><visual_scene id="S2"><node id="b"><instance_geometry url="#U"/></node></visual_scene></library_visual_scenes>',
    scene='<scene><instance_visual_scene url="#S2"/></scene>',
)
cases["meshlab_vertex_color"] = doc(
    geoms(
        '<geometry id="shape0-lib"><mesh>'
        + src("shape0-lib-positions", "0 0 0 1 0 0 0 1 0")
        + src("shape0-lib-normals", "0 0 1 0 0 1 0 0 1")
        + src("shape0-lib-vcolor", "1 0 0 1 0 1 0 1 0 0 1 1", 4)
        + '<vertices id="shape0-lib-vertices"><input semantic="POSITION" source="#shape0-lib-positions"/><input semantic="NORMAL" source="#shape0-lib-normals"/><input semantic="COLOR" source="#shape0-lib-vcolor"/></vertices>'
        '<triangles count="1"><input semantic="VERTEX" source="#shape0-lib-vertices" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="node" name="node"><instance_geometry url="#shape0-lib"/></node>')
)
# Name_array used as a geometry source for positions (strings -> NaN)
cases["name_array_positions"] = doc(
    geoms(
        '<geometry id="G"><mesh><source id="G-p"><Name_array id="G-pa" count="9">a b c d e f g h i</Name_array><technique_common><accessor source="#G-pa" count="3" stride="3"/></technique_common></source>'
        '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices><triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)

# ---------------- transforms ----------------
TN = lambda t: doc(
    geoms(tri("T")) + vs(f'<node id="a">{t}<instance_geometry url="#T"/></node>')
)
cases["rotate_zero_angle"] = TN("<rotate>0 0 1 0</rotate><translate>1 2 3</translate>")
cases["rotate_negative"] = TN("<rotate>0 1 0 -90</rotate>")
cases["rotate_zero_axis"] = TN("<rotate>0 0 0 45</rotate>")
cases["rotate_nan_axis"] = TN("<rotate>0 0 1</rotate>")
cases["scale_negative_x"] = TN("<scale>-1 1 1</scale>")
cases["scale_nonuniform"] = TN("<scale>2 3 4</scale><rotate>1 0 0 30</rotate>")
cases["scale_zero_component"] = TN("<scale>1 1 0</scale>")
cases["matrix_w_scale"] = TN("<matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 2</matrix>")
cases["matrix_projective"] = TN("<matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 1 1</matrix>")
cases["matrix_shear"] = TN("<matrix>1 0.5 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>")
cases["lookat_plus_translate"] = TN(
    "<lookat>0 0 10 0 0 0 0 1 0</lookat><translate>1 0 0</translate>"
)
cases["skew_plus_translate"] = TN(
    "<skew>45 0 0 1 1 0 0</skew><translate>1 0 0</translate>"
)
cases["matrix_17_values"] = TN("<matrix>1 0 0 5 0 1 0 0 0 0 1 0 0 0 0 1 99</matrix>")
cases["translate_two_values"] = TN("<translate>1 2</translate>")
cases["scale_four_values"] = TN("<scale>2 2 2 2</scale>")
cases["matrix_with_f_suffix"] = TN(
    "<matrix>1.0f 0 0 5 0 1 0 0 0 0 1 0 0 0 0 1</matrix>"
)
cases["nested_scale_normals"] = doc(
    geoms(tri("T"))
    + vs(
        '<node id="a"><scale>1 1 3</scale><node id="b"><rotate>0 0 1 90</rotate><scale>2 1 1</scale><instance_geometry url="#T"/></node></node>'
    )
)

# ---------------- morph controller sharing geometry ----------------
cases["morph_unused_shared_geom"] = doc(
    '<library_controllers><controller id="C"><morph source="#T" method="NORMALIZED"><targets/></morph></controller></library_controllers>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["morph_missing_source_unused"] = doc(
    '<library_controllers><controller id="C"><morph source="#nope"/></controller></library_controllers>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["skin_missing_source_unused"] = doc(
    '<library_controllers><controller id="C"><skin source="#nope"><joints/><vertex_weights count="0"/></skin></controller></library_controllers>'
    + geoms(tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["controller_empty"] = doc(
    '<library_controllers><controller id="C"/></library_controllers>'
    + geoms(tri("T"))
    + vs(
        '<node id="a"><instance_controller url="#C"/></node><node id="b"><instance_geometry url="#T"/></node>'
    )
)
# skin with vcount>0 but no <v>
cases["skin_vcount_no_v"] = doc(
    SKIN.replace("<v>0 0 0 0 0 0 0 0 0 1 1 1 0 1 1 1 0 1 1 1 0 1 1 1</v>", "")
    + geoms(blender_geom(), tri("T"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
# skin with zero-weight vertices (vcount all 0): geometry is skinned? JS: skinIndex pushes per corner anyway
cases["skin_all_zero_vcount"] = doc(
    SKIN.replace(
        "<vcount>1 1 1 1 2 2 2 2</vcount>", "<vcount>0 0 0 0 0 0 0 0</vcount>"
    ).replace("<v>0 0 0 0 0 0 0 0 0 1 1 1 0 1 1 1 0 1 1 1 0 1 1 1</v>", "<v></v>")
    + geoms(blender_geom(), tri("T"))
    + vs(
        '<node id="a"><instance_geometry url="#Cube-mesh"/></node><node id="b"><instance_geometry url="#T"/></node>'
    )
)

# ---------------- text / number forms ----------------
cases["bom"] = "﻿" + doc(
    geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["comment_in_p"] = doc(
    geoms(tri("T", p="0 0 1 0 <!-- c --> 2 0"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["cdata_float_array"] = doc(
    geoms(tri("T").replace("0 0 0 1 0 0 0 1 0", "<![CDATA[0 0 0 1 0 0 0 1 0]]>"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["whitespace_forms"] = doc(
    geoms(tri("T").replace("0 0 0 1 0 0 0 1 0", "\n\t0\t0 0\r\n1 0 0\n\n0 1 0\t\n"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["number_forms"] = doc(
    geoms(tri("T").replace("0 0 0 1 0 0 0 1 0", "-0 .5 5. +3 1e-5 1E+1 0x10 1_0 -.5e1"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["number_forms_p"] = doc(
    geoms(
        tri("T", normals=False, p="0x0 01 2.9").replace(
            "0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 0 5 5 5"
        )
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["unicode_digits"] = doc(
    geoms(
        tri("T", normals=False, p="0 1 ２").replace(
            "0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 ١"
        )
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["nbsp_separator"] = doc(
    geoms(tri("T").replace("0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 0"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["nan_inf_tokens"] = doc(
    geoms(
        tri("T")
        .replace("0 0 0 1 0 0 0 1 0", "NaN 0 0 1 0 0 0 1 Infinity")
        .replace("0 0 1</float_array>", "inf nan -Infinity</float_array>")
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["empty_p"] = doc(
    geoms(tri("T", p="")) + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["whitespace_p"] = doc(
    geoms(tri("T", p="   ")) + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["empty_float_array"] = doc(
    geoms(tri("T").replace("0 0 0 1 0 0 0 1 0", ""))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["child_elem_in_p"] = doc(
    geoms(tri("T", p="0 0 1 0 <extra/> 2 0"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["namespace_prefix"] = (
    doc(geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'))
    .replace(
        '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema"',
        '<c:COLLADA xmlns:c="http://www.collada.org/2005/11/COLLADASchema"',
    )
    .replace("</COLLADA>", "</c:COLLADA>")
)
cases["no_namespace"] = doc(
    geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>')
).replace(' xmlns="http://www.collada.org/2005/11/COLLADASchema"', "")
cases["collada15"] = (
    doc(geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'))
    .replace("2005/11/COLLADASchema", "2008/03/COLLADASchema")
    .replace('version="1.4.1"', 'version="1.5.0"')
)
cases["doctype_entity"] = doc(
    geoms(tri("T").replace("0 0 0 1 0 0 0 1 0", "0 0 0 1 0 0 0 1 &z;"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
).replace("<COLLADA", '<!DOCTYPE COLLADA [<!ENTITY z "0">]><COLLADA', 1)
cases["geometry_without_id_instanced_by_hash_only"] = doc(
    geoms(tri("T").replace('id="T"', ""))
    + vs('<node id="a"><instance_geometry url="#"/></node>')
)
cases["geometry_without_id_unused"] = doc(
    geoms(tri("T").replace('id="T"', ""), tri("U"))
    + vs('<node id="a"><instance_geometry url="#U"/></node>')
)
cases["two_scene_elements"] = doc(
    geoms(tri("T"), tri("U", 7))
    + '<library_visual_scenes><visual_scene id="S1"><node id="a"><instance_geometry url="#T"/></node></visual_scene><visual_scene id="S2"><node id="b"><instance_geometry url="#U"/></node></visual_scene></library_visual_scenes>',
    scene='<scene><instance_visual_scene url="#S1"/><instance_visual_scene url="#S2"/></scene><scene><instance_visual_scene url="#S2"/></scene>',
)
cases["scene_with_kinematics_only_first"] = doc(
    geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'),
    scene='<scene><instance_physics_scene url="#P"/><instance_visual_scene url="#Scene"/></scene>',
)
cases["visual_scene_nodes_in_extra"] = doc(
    geoms(tri("T"))
    + vs(
        '<extra><node id="x"><instance_geometry url="#T"/></node></extra><node id="a"><instance_geometry url="#T"/></node>'
    )
)
cases["nested_geometry_tag_in_extra"] = doc(
    "<library_geometries>"
    + tri("T")
    + "<extra>"
    + tri("U", 7)
    + "</extra></library_geometries>"
    + vs(
        '<node id="a"><instance_geometry url="#T"/></node><node id="b"><instance_geometry url="#U"/></node>'
    )
)
# unit attribute weird + up_axis with whitespace
cases["up_axis_whitespace"] = doc(
    geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'),
    asset=ASSET.replace("<up_axis>Y_UP</up_axis>", "<up_axis> Z_UP </up_axis>").replace(
        'meter="1"', 'meter="abc"'
    ),
)
# default id collision: a real node named three_default_0
cases["three_default_collision"] = doc(
    geoms(tri("T"), tri("U", 7))
    + vs(
        '<node><translate>5 0 0</translate><instance_geometry url="#T"/></node><node id="three_default_0"><instance_geometry url="#U"/></node>'
    )
)
# instance_node to a node that is also a visual-scene child, appearing BEFORE: moved by add()
cases["inode_moves_scene_node"] = doc(
    geoms(tri("T"))
    + vs(
        '<node id="b"><translate>0 0 100</translate><instance_geometry url="#T"/></node><node id="a"><translate>1 0 0</translate><instance_node url="#b"/><node id="c"/></node>'
    )
)
# instance_node to a node that is a CHILD of another scene node (child built twice? shares build)
cases["inode_to_child_node"] = doc(
    geoms(tri("T"))
    + vs(
        '<node id="p"><translate>0 10 0</translate><node id="b"><translate>0 0 100</translate><instance_geometry url="#T"/></node></node><node id="a"><translate>1 0 0</translate><instance_node url="#b"/><node id="c"/></node>'
    )
)
# child node listed in a parent AND also instanced as lone instance_node by a later node (shortcut uses clone)
cases["inode_lone_to_child_node"] = doc(
    geoms(tri("T"))
    + vs(
        '<node id="p"><translate>0 10 0</translate><node id="b"><translate>0 0 100</translate><instance_geometry url="#T"/></node></node><node id="a"><translate>1 0 0</translate><instance_node url="#b"/></node>'
    )
)
# duplicate child node ids within different parents: second child resolves to first node's build and is moved
cases["dup_child_ids_moved"] = doc(
    geoms(tri("T"), tri("U", 7))
    + vs(
        '<node id="p"><translate>0 10 0</translate><node id="k"><instance_geometry url="#T"/></node></node><node id="q"><translate>1 0 0</translate><node id="k"><instance_geometry url="#U"/></node></node>'
    )
)
# polylist with vcount but <p> missing / vcount missing in polylist
cases["polylist_no_vcount"] = doc(
    geoms(tri("T", prim="polylist", p="0 0 1 0 2 0"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["triangles_with_vcount"] = doc(
    geoms(tri("T", vcount="3", p="0 0 1 0 2 0"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["prim_no_p"] = doc(
    geoms(tri("T").replace("<p>0 0 1 0 2 0</p>", ""))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["prim_no_inputs"] = doc(
    geoms(
        tri("T").replace(
            '<input semantic="VERTEX" source="#T-v" offset="0"/><input semantic="NORMAL" source="#T-n" offset="1"/>',
            "",
        )
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["input_no_source"] = doc(
    geoms(tri("T").replace(' source="#T-n" offset="1"', ' offset="1"'))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["vertices_input_no_source"] = doc(
    geoms(
        tri("T").replace(
            '<input semantic="POSITION" source="#T-p"/>', '<input semantic="POSITION"/>'
        )
    )
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["instance_geometry_no_url"] = doc(
    geoms(tri("T"))
    + vs(
        '<node id="a"><instance_geometry/></node><node id="b"><instance_geometry url="#T"/></node>'
    )
)
cases["geometry_no_mesh_instanced"] = doc(
    geoms('<geometry id="S"><spline/></geometry>', tri("T"))
    + vs(
        '<node id="a"><instance_geometry url="#S"/></node><node id="b"><instance_geometry url="#T"/></node>'
    )
)
cases["geometry_no_mesh_unused"] = doc(
    geoms('<geometry id="S"><convex_mesh convex_hull_of="#T"/></geometry>', tri("T"))
    + vs('<node id="b"><instance_geometry url="#T"/></node>')
)
cases["mesh_empty"] = doc(
    geoms('<geometry id="S"><mesh/></geometry>', tri("T"))
    + vs(
        '<node id="a"><instance_geometry url="#S"/></node><node id="b"><instance_geometry url="#T"/></node>'
    )
)
cases["mesh_sources_only_instanced_alone"] = doc(
    geoms('<geometry id="S"><mesh>' + src("S-p", "0 0 0") + "</mesh></geometry>")
    + vs('<node id="a"><instance_geometry url="#S"/></node>')
)
cases["normal_stride_nan_two_geoms"] = doc(
    geoms(
        tri("T").replace(
            'stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><vertices',
            '><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><vertices',
        ),
        tri("U", 7).replace(
            'stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><vertices',
            '><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><vertices',
        ),
    )
    + vs(
        '<node id="a"><instance_geometry url="#T"/></node><node id="b"><instance_geometry url="#U"/></node>'
    )
)
cases["position_stride2"] = doc(
    geoms(
        '<geometry id="G"><mesh>'
        + src("G-p", "0 0 1 0 0 1", 2, "XY")
        + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices><triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
    )
    + vs('<node id="a"><instance_geometry url="#G"/></node>')
)
cases["huge_index"] = doc(
    geoms(tri("T", normals=False, p="0 1 99999999999"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
cases["negative_index"] = doc(
    geoms(tri("T", normals=False, p="0 1 -1 0 1 2"))
    + vs('<node id="a"><instance_geometry url="#T"/></node>')
)
