# SPDX-License-Identifier: MIT
# ruff: noqa  (test data: long XML strings and shared helpers)
"""A geometry whose normal attribute is shorter than its positions."""

from .basic import doc
from .primitives import POS, geom_custom

cases = {
    "partial_normals_one_geom": doc(
        geom_custom(
            "G",
            POS("G", "0 0 0 1 0 0 0 1 0 0 0 3 1 0 3 0 1 3")
            + '<source id="G-n"><float_array id="G-na">0 0 1</float_array><technique_common><accessor source="#G-na" stride="3"/></technique_common></source>'
            '<vertices id="G-v"><input semantic="POSITION" source="#G-p"/></vertices>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><p>3 4 5</p></triangles>'
            '<triangles count="1"><input semantic="VERTEX" source="#G-v" offset="0"/><input semantic="NORMAL" source="#G-n" offset="1"/><p>0 0 1 0 2 0</p></triangles>',
        ),
        '<node id="a"><instance_geometry url="#G"/></node>',
    )
}
