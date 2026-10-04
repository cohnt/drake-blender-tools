# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""Materials, bind_material, effects and malformed documents."""

from .exporters import *  # noqa: F401,F403

E_OK = '<library_effects><effect id="E"><profile_COMMON><technique sid="c"><phong><diffuse><color>1 0 0 1</color></diffuse></phong></technique></profile_COMMON></effect></library_effects>'
MATS = (
    E_OK
    + '<library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
)
TRI_M = tri("T").replace(
    '<triangles count="1">', '<triangles count="1" material="sym">'
)
TRI_M2 = tri("U", 7).replace(
    '<triangles count="1">', '<triangles count="1" material="sym2">'
)
N = lambda bind, url="#T": doc(
    MATS
    + geoms(TRI_M, TRI_M2)
    + vs(
        f'<node id="a"><instance_geometry url="{url}">{bind}</instance_geometry></node><node id="b"><instance_geometry url="#U"/></node>'
    )
)
BM = (
    lambda inner: f"<bind_material><technique_common>{inner}</technique_common></bind_material>"
)

cases = {
    # --- instance_material binding ---
    "bind_ok": N(BM('<instance_material symbol="sym" target="#M"/>')),
    "bind_missing_target": N(BM('<instance_material symbol="sym" target="#NOPE"/>')),
    "bind_unbound_symbol": N(
        BM('<instance_material symbol="other" target="#NOPE"/>')
    ),  # symbol not used by prim: warn + fallback, NOPE never looked up
    "bind_no_target_attr": N(
        BM('<instance_material symbol="sym"/>')
    ),  # parse-time throw (o(null))
    "bind_no_target_attr_unused_libnode": doc(
        MATS
        + geoms(tri("T"))
        + libnodes(
            '<node id="L"><instance_geometry url="#T">'
            + BM('<instance_material symbol="x"/>')
            + "</instance_geometry></node>"
        )
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "bind_target_no_hash": N(BM('<instance_material symbol="sym" target="M"/>')),
    "bind_in_technique_profile": N(
        '<bind_material><technique profile="x"><instance_material symbol="sym" target="#NOPE"/></technique></bind_material>'
    ),
    "bind_missing_target_on_other_type": doc(
        MATS
        + geoms(
            tri("T").replace(
                "</mesh>",
                '<lines count="1" material="lsym"><input semantic="VERTEX" source="#T-v" offset="0"/><p>0 1</p></lines></mesh>',
            )
        )
        + vs(
            '<node id="a"><instance_geometry url="#T">'
            + BM('<instance_material symbol="lsym" target="#NOPE"/>')
            + "</instance_geometry></node>"
        )
    ),
    "bind_missing_target_second_matlib": doc(
        MATS
        + '<library_materials><material id="M2"><instance_effect url="#E"/></material></library_materials>'
        + geoms(TRI_M)
        + vs(
            '<node id="a"><instance_geometry url="#T">'
            + BM('<instance_material symbol="sym" target="#M2"/>')
            + "</instance_geometry></node>"
        )
    ),
    "bind_missing_target_controller": doc(
        MATS
        + SKIN.replace("#Cube-mesh", "#T").replace("Armature_Cube-skin", "SK")
        + geoms(TRI_M)
        + vs(
            '<node id="a"><instance_controller url="#SK">'
            + BM('<instance_material symbol="sym" target="#NOPE"/>')
            + '</instance_controller></node><node id="b"><instance_geometry url="#T"/></node>'
        )
    ),
    "bind_material_attr_empty": N(
        BM('<instance_material symbol="" target="#NOPE"/>')
    ).replace('material="sym"', 'material=""'),
    "material_attr_no_bind": N(""),
    "bind_missing_target_in_libnode_instanced": doc(
        MATS
        + geoms(TRI_M)
        + libnodes(
            '<node id="L"><instance_geometry url="#T">'
            + BM('<instance_material symbol="sym" target="#NOPE"/>')
            + "</instance_geometry></node>"
        )
        + vs('<node id="a"><instance_node url="#L"/></node>')
    ),
    "bind_missing_target_in_libnode_unused": doc(
        MATS
        + geoms(TRI_M)
        + libnodes(
            '<node id="L"><instance_geometry url="#T">'
            + BM('<instance_material symbol="sym" target="#NOPE"/>')
            + "</instance_geometry></node>"
        )
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "bind_duplicate_symbol_last_wins": N(
        BM(
            '<instance_material symbol="sym" target="#NOPE"/><instance_material symbol="sym" target="#M"/>'
        )
    ),
    "bind_duplicate_symbol_last_bad": N(
        BM(
            '<instance_material symbol="sym" target="#M"/><instance_material symbol="sym" target="#NOPE"/>'
        )
    ),
    # --- effects ---
    "effect_two_techniques_last_empty": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong/></technique><technique sid="b"/></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_two_profiles_last_empty": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong/></technique></profile_COMMON><profile_COMMON/></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_constant_only": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><constant/></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_bump_extra_no_texture": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong/><extra><technique profile="FCOLLADA"><bump/></technique></extra></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_transparent_no_opaque_short_color": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong><transparent><color>1 1 1</color></transparent></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_transparent_empty_weird_opaque": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong><transparent opaque="WEIRD"/></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_transparent_empty_default_opaque": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong><transparent/></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_transparency_only": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="a"><phong><transparency><float>0.5</float></transparency></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_sampler_no_source": doc(
        '<library_effects><effect id="E"><profile_COMMON><newparam sid="s"><sampler2D/></newparam><technique sid="c"><phong><diffuse><texture texture="s" texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_texture_no_texture_attr": doc(
        '<library_effects><effect id="E"><profile_COMMON><technique sid="c"><phong><diffuse><texture texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_texture_direct_image": doc(
        '<library_images><image id="img"><init_from>a.png</init_from></image></library_images><library_effects><effect id="E"><profile_COMMON><technique sid="c"><phong><diffuse><texture texture="img" texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_texture_tga": doc(
        '<library_images><image id="img"><init_from>a.tga</init_from></image></library_images><library_effects><effect id="E"><profile_COMMON><technique sid="c"><phong><diffuse><texture texture="img" texcoord="UV"/></diffuse></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_specular_texture_sampler_missing_surface": doc(
        '<library_effects><effect id="E"><profile_COMMON><newparam sid="s"><sampler2D><source>nosurf</source></sampler2D></newparam><technique sid="c"><phong><specular><texture texture="s" texcoord="UV"/></specular></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_shininess_texture_sampler_missing_surface": doc(
        '<library_effects><effect id="E"><profile_COMMON><newparam sid="s"><sampler2D><source>nosurf</source></sampler2D></newparam><technique sid="c"><phong><shininess><texture texture="s" texcoord="UV"/></shininess></phong></technique></profile_COMMON></effect></library_effects><library_materials><material id="M"><instance_effect url="#E"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "effect_unused_bad_no_material": doc(
        '<library_effects><effect id="E"><profile_COMMON/></effect></library_effects>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "material_two_instance_effects_last_bad": doc(
        E_OK
        + '<library_materials><material id="M"><instance_effect url="#E"/><instance_effect url="#NOPE"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "material_in_second_library_bad": doc(
        MATS
        + '<library_materials><material id="M2"><instance_effect url="#NOPE"/></material></library_materials>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    # --- images / lights / cameras ---
    "image_init_from_ref_15": doc(
        '<library_images><image id="I"><init_from><ref>a.png</ref></init_from></image></library_images>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "image_empty": doc(
        '<library_images><image id="I"/></library_images>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "image_in_second_library_bad": doc(
        '<library_images/><library_images><image id="I"/></library_images>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "light_technique_unknown_child": doc(
        '<library_lights><light id="L"><technique_common><area/></technique_common></light></library_lights>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "light_point_no_color": doc(
        '<library_lights><light id="L"><technique_common><point/></technique_common></light></library_lights>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "light_two_tc_last_bad": doc(
        '<library_lights><light id="L"><technique_common><point/></technique_common><technique_common/></light></library_lights>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "light_ambient_ok": doc(
        '<library_lights><light id="L"><technique_common><ambient><color>1 1 1</color></ambient></technique_common></light></library_lights>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "camera_optics_perspective_no_params": doc(
        '<library_cameras><camera id="C"><optics><technique_common><perspective/></technique_common></optics></camera></library_cameras>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "camera_orthographic_ok": doc(
        '<library_cameras><camera id="C"><optics><technique_common><orthographic><xmag>1</xmag><znear>0.1</znear><zfar>10</zfar></orthographic></technique_common></optics></camera></library_cameras>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "camera_two_optics_last_ok": doc(
        '<library_cameras><camera id="C"><extra/><optics><technique_common><perspective/></technique_common></optics></camera></library_cameras>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    # --- polylist count / vcount ---
    "polylist_no_vcount_count0": doc(
        geoms(tri("T", prim="polylist", p="0 0 1 0 2 0", count=0))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "polylist_no_vcount_count_nan": doc(
        geoms(tri("T", prim="polylist", p="0 0 1 0 2 0", count="x"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "polylist_no_vcount_no_count": doc(
        geoms(
            tri("T", prim="polylist", p="0 0 1 0 2 0").replace(
                '<polylist count="1">', "<polylist>"
            )
        )
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "polylist_vcount_shorter_than_count": doc(
        geoms(tri("T", prim="polylist", p="0 0 1 0 2 0", vcount="3", count=5))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "polylist_empty_vcount_count1": doc(
        geoms(tri("T", prim="polylist", p="0 0 1 0 2 0", vcount="", count=1))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    # --- skins ---
    "skin_two_joints_last_bad": doc(
        SKIN.replace(
            "</joints>",
            '</joints><joints><input semantic="INV_BIND_MATRIX" source="#Armature_Cube-skin-bind_poses"/></joints>',
        )
        + geoms(blender_geom(), tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "skin_two_vw_last_bad": doc(
        SKIN.replace(
            "</vertex_weights>", '</vertex_weights><vertex_weights count="0"/>'
        )
        + geoms(blender_geom(), tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "skin_v_too_short": doc(
        SKIN.replace(
            "<v>0 0 0 0 0 0 0 0 0 1 1 1 0 1 1 1 0 1 1 1 0 1 1 1</v>", "<v>0 0</v>"
        )
        + geoms(blender_geom(), tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "skin_bind_shape_short": doc(
        SKIN.replace(
            "<bind_shape_matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</bind_shape_matrix>",
            "<bind_shape_matrix>1 0</bind_shape_matrix>",
        )
        + geoms(blender_geom(), tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "skeleton_builds_failing_libnode": doc(
        SKIN.replace("#Cube-mesh", "#T").replace("Armature_Cube-skin", "SK")
        + geoms(TRI_M.replace('material="sym"', ""))
        + libnodes(
            '<node id="Bone" type="JOINT" sid="Bone"><instance_geometry url="#MISSING"/></node>'
        )
        + vs(
            '<node id="a"><instance_controller url="#SK"><skeleton>#Bone</skeleton></instance_controller></node><node id="b"><instance_geometry url="#T"/></node>'
        )
    ),
    "skeleton_missing_root": doc(
        SKIN.replace("#Cube-mesh", "#T").replace("Armature_Cube-skin", "SK")
        + geoms(tri("T"))
        + vs(
            '<node id="a"><instance_controller url="#SK"><skeleton>#nowhere</skeleton></instance_controller></node><node id="b"><instance_geometry url="#T"/></node>'
        )
    ),
    # --- misc structure ---
    "doctype_no_entity": doc(
        geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ).replace("<COLLADA", "<!DOCTYPE COLLADA><COLLADA", 1),
    "geometry_two_meshes": doc(
        geoms(
            '<geometry id="T"><mesh>'
            + src("T-p", "0 0 0 1 0 0 0 1 0")
            + '<vertices id="T-v"><input semantic="POSITION" source="#T-p"/></vertices><triangles count="1"><input semantic="VERTEX" source="#T-v" offset="0"/><p>0 1 2</p></triangles></mesh><mesh>'
            + src("T-q", "0 0 9 1 0 9 0 1 9")
            + '<vertices id="T-w"><input semantic="POSITION" source="#T-q"/></vertices><triangles count="1"><input semantic="VERTEX" source="#T-w" offset="0"/><p>0 1 2</p></triangles></mesh></geometry>'
        )
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "source_two_float_arrays": doc(
        geoms(
            tri("T").replace(
                '<technique_common><accessor source="#T-p-array"',
                '<float_array id="x" count="9">0 0 9 1 0 9 0 1 9</float_array><technique_common><accessor source="#T-p-array"',
            )
        )
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "source_two_technique_common": doc(
        geoms(
            tri("T").replace(
                '</technique_common></source><source id="T-n">',
                '</technique_common><technique_common><accessor source="#T-p-array" count="1" stride="4"/></technique_common></source><source id="T-n">',
            )
        )
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "unit_no_meter_attr": doc(
        geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'),
        asset=ASSET.replace('<unit name="meter" meter="1"/>', '<unit name="meter"/>'),
    ),
    "asset_empty": doc(
        geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'),
        asset="<asset/>",
    ),
    "two_assets_second_has_zup": doc(
        geoms(tri("T")) + vs('<node id="a"><instance_geometry url="#T"/></node>'),
        asset=ASSET + ASSET.replace("Y_UP", "Z_UP"),
    ),
    "animation_library_garbage": doc(
        '<library_animations><animation id="a"><channel/></animation></library_animations>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "animation_realistic_blender": doc(
        '<library_animations><animation id="action_container" name="Cube"><animation id="Cube_location_X" name="Cube"><source id="Cube_location_X-input"><float_array id="Cube_location_X-input-array" count="2">0.04 1</float_array><technique_common><accessor source="#Cube_location_X-input-array" count="2" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source><source id="Cube_location_X-output"><float_array id="Cube_location_X-output-array" count="2">0 1</float_array><technique_common><accessor source="#Cube_location_X-output-array" count="2" stride="1"><param name="X" type="float"/></accessor></technique_common></source><source id="Cube_location_X-interpolation"><Name_array id="Cube_location_X-interpolation-array" count="2">BEZIER BEZIER</Name_array><technique_common><accessor source="#Cube_location_X-interpolation-array" count="2" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source><sampler id="Cube_location_X-sampler"><input semantic="INPUT" source="#Cube_location_X-input"/><input semantic="OUTPUT" source="#Cube_location_X-output"/><input semantic="INTERPOLATION" source="#Cube_location_X-interpolation"/></sampler><channel source="#Cube_location_X-sampler" target="Cube/location.X"/></animation></animation></library_animations>'
        + geoms(tri("T"))
        + vs(
            '<node id="Cube" name="Cube"><translate sid="location">0 0 0</translate><instance_geometry url="#T"/></node>'
        )
    ),
    "animation_matrix_channel": doc(
        '<library_animations><animation id="Cube_transform"><source id="in"><float_array id="ina" count="2">0 1</float_array><technique_common><accessor source="#ina" count="2" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source><source id="out"><float_array id="outa" count="32">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 1 0 0 5 0 1 0 0 0 0 1 0 0 0 0 1</float_array><technique_common><accessor source="#outa" count="2" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common></source><source id="interp"><Name_array id="interpa" count="2">LINEAR LINEAR</Name_array><technique_common><accessor source="#interpa" count="2" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source><sampler id="s"><input semantic="INPUT" source="#in"/><input semantic="OUTPUT" source="#out"/><input semantic="INTERPOLATION" source="#interp"/></sampler><channel source="#s" target="Cube/transform"/></animation></library_animations>'
        + geoms(tri("T"))
        + vs(
            '<node id="Cube" name="Cube"><matrix sid="transform">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix><instance_geometry url="#T"/></node>'
        )
    ),
    "kinematics_scene_present": doc(
        '<library_kinematics_models><kinematics_model id="km"><technique_common><joint sid="j"><revolute sid="r"><axis>0 0 1</axis></revolute></joint><link sid="l"/></technique_common></kinematics_model></library_kinematics_models>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>'),
        scene='<scene><instance_visual_scene url="#Scene"/><instance_kinematics_scene url="#ks"/></scene>',
    ),
    "physics_scene_present": doc(
        '<library_physics_models><physics_model id="pm"><rigid_body sid="rb" name="rb"><technique_common><dynamic>true</dynamic><mass>1</mass></technique_common></rigid_body></physics_model></library_physics_models>'
        + geoms(tri("T"))
        + vs('<node id="a"><instance_geometry url="#T"/></node>')
    ),
    "position_stride2_two_tris": doc(
        geoms(
            '<geometry id="G"><mesh>'
            + src("G-p", "0 0 1 0 0 1 1 1 2 2 3 3", 2, "XY")
            + '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices><triangles count="2"><input semantic="VERTEX" source="#G-v" offset="0"/><p>0 1 2 3 4 5</p></triangles></mesh></geometry>'
        )
        + vs('<node id="a"><instance_geometry url="#G"/></node>')
    ),
    "instance_node_url_no_hash": doc(
        geoms(tri("T"))
        + libnodes('<node id="L"><instance_geometry url="#T"/></node>')
        + vs('<node id="a"><instance_node url="L"/></node>')
    ),
    "instance_node_self": doc(
        geoms(tri("T"))
        + vs(
            '<node id="a"><instance_node url="#a"/><instance_geometry url="#T"/></node>'
        )
    ),
    "instance_node_mutual": doc(
        geoms(tri("T"))
        + libnodes(
            '<node id="L"><instance_node url="#M"/></node><node id="M"><instance_node url="#L"/></node>'
        )
        + vs(
            '<node id="a"><instance_node url="#L"/><instance_geometry url="#T"/></node>'
        )
    ),
    "node_child_is_visual_scene_root_dup": doc(
        geoms(tri("T"), tri("U", 7))
        + vs(
            '<node id="a"><translate>1 0 0</translate><instance_geometry url="#T"/><node id="b"><instance_geometry url="#U"/></node></node><node id="b"><translate>0 5 0</translate><instance_geometry url="#U"/></node>'
        )
    ),
}
