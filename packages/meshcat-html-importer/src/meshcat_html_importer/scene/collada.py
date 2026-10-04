# SPDX-License-Identifier: MIT
"""Collada (.dae) reader that follows what Meshcat displays.

Drake sends a .dae mesh as a ``_meshfile_geometry`` with format "dae". Meshcat
turns it into one geometry with
``merge_geometries(new ColladaLoader().parse(data).scene)`` (three.js) and
shades it with the material Drake sends alongside it. The file is read with
pycollada, and the result follows the same rules:

- Node transforms (``matrix``, ``translate``, ``rotate``, ``scale``), nested
  nodes and ``instance_node`` are baked into the vertices.
- ``<unit>`` and ``<up_axis>`` are ignored. ColladaLoader applies them only to
  ``scene.rotation`` and ``scene.scale``, which merge_geometries never reads.
- ``triangles`` and ``polylist`` are drawn, with polylist quads split as
  three.js splits them. ``polygons``, ``tristrips``, ``trifans``, lines and
  skinned meshes are not drawn.
- Materials, textures and vertex colors are not shown, since Meshcat uses the
  material Drake sends.
- Meshes whose attributes differ (say one with normals and one without)
  cannot be merged, and Meshcat shows nothing. Within one geometry, three.js
  gives texture coordinates of zero to the primitives that have none.

Malformed or unusual files can still differ from Meshcat. For example,
three.js transforms a geometry that is instanced more than once in place, once
per instance, so every copy lands at the product of the transforms, whereas
pycollada places each copy where the file says. A geometry or scene that
pycollada cannot read (say a geometry with ``linestrips``) is skipped with a
warning, though Meshcat may draw part of it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import collada
import numpy as np
from collada.asset import UP_AXIS
from collada.common import DaeBrokenRefError, DaeUnsupportedError
from collada.polylist import Polylist
from collada.triangleset import TriangleSet


@dataclass
class ColladaMesh:
    """Triangle mesh as Meshcat draws it, in the file's own coordinates."""

    positions: np.ndarray  # Nx3 vertex positions
    triangles: np.ndarray  # Mx3 indices into positions
    corner_normals: np.ndarray | None = None  # (3M)x3 normals, one per corner
    corner_uvs: np.ndarray | None = None  # (3M)x2 texture coordinates per corner
    warnings: list[str] = field(default_factory=list)  # content that was dropped
    notes: list[str] = field(default_factory=list)  # settings ignored, as in Meshcat


@dataclass
class _Corners:
    """Per-corner data of one drawn primitive, three corners per triangle."""

    positions: np.ndarray
    normals: np.ndarray | None
    uvs: np.ndarray | None
    has_color: bool


def parse_collada(data: bytes | str) -> ColladaMesh:
    """Read a Collada document into the triangle mesh Meshcat would draw.

    Raises pycollada's errors for documents it cannot read.
    """
    if isinstance(data, str):
        data = data.encode()
    # Exporters often leave references to cameras or lights they did not
    # write. Those do not affect the geometry, so read on past them.
    dae = collada.Collada(
        io.BytesIO(data), ignore=[DaeUnsupportedError, DaeBrokenRefError]
    )

    notes = []
    asset = dae.assetInfo
    if asset.unitmeter is not None and asset.unitmeter != 1.0:
        notes.append(
            f"<unit meter={asset.unitmeter:g}> is ignored, as in Meshcat; "
            "vertices are used as written"
        )
    if asset.upaxis != UP_AXIS.Y_UP:
        notes.append(f"<up_axis> {asset.upaxis} is ignored, as in Meshcat")

    warnings = []
    read = {geometry.id for geometry in dae.geometries}
    for node in dae.xmlnode.iter(dae.tag("geometry")):
        if node.find(dae.tag("mesh")) is not None and node.get("id") not in read:
            warnings.append(f"geometry {node.get('id')} could not be read; skipped")
    if dae.scene is None:
        return _empty_mesh(warnings + ["the file has no scene that can be read"], notes)
    if any(True for _ in dae.scene.objects("controller")):
        warnings.append("skinned or morphed meshes are not drawn by Meshcat; skipped")

    pieces = []
    skipped = set()
    for bound in dae.scene.objects("geometry"):
        # three.js builds one mesh per geometry and primitive type.
        groups = {}
        for primitive in bound.original.primitives:
            # pycollada reads tristrips and trifans as triangles; three.js skips them.
            kind = primitive.xmlnode.tag.rpartition("}")[2]
            if kind in ("triangles", "polylist"):
                corners = _corners(primitive, bound.matrix)
                if corners is not None:
                    groups.setdefault(kind, []).append(corners)
            else:
                skipped.add(f"<{kind}>")
        for group in groups.values():
            if any(p.uvs is not None for p in group):
                for p in group:
                    if p.uvs is None:
                        p.uvs = np.zeros((len(p.positions), 2))
            pieces.extend(group)
    for kind in sorted(skipped):
        warnings.append(f"{kind} are not drawn by Meshcat; skipped")

    if not pieces:
        return _empty_mesh(warnings + ["no triangle geometry found"], notes)
    layouts = {(p.normals is None, p.uvs is None, p.has_color) for p in pieces}
    if len(layouts) > 1:
        return _empty_mesh(
            warnings
            + [
                "Meshcat cannot merge meshes whose normals, texture coordinates "
                "or colors differ, and shows nothing"
            ],
            notes,
        )
    return _triangle_mesh(pieces, warnings, notes)


def _corners(primitive: TriangleSet | Polylist, matrix: np.ndarray) -> _Corners | None:
    """Per-corner positions, normals and UVs of a primitive, transformed."""
    if primitive.vertex is None:
        return None
    if isinstance(primitive, Polylist):
        triangles = _split_polygons(np.asarray(primitive.vcounts, dtype=np.int64))
    else:
        triangles = np.arange(3 * len(primitive.vertex_index)).reshape(-1, 3)
    triangles = triangles.ravel()

    def gather(values, index):
        return np.asarray(values, dtype=np.float64)[np.ravel(index)[triangles]]

    linear, translation = matrix[:3, :3], matrix[:3, 3]
    positions = gather(primitive.vertex, primitive.vertex_index) @ linear.T
    positions += translation

    normals = None
    if primitive.normal is not None:
        # Normals take the inverse transpose, renormalized, as in three.js.
        if np.linalg.det(linear) == 0:
            normals = np.zeros_like(positions)
        else:
            normal_matrix = np.linalg.inv(linear)
            normals = gather(primitive.normal, primitive.normal_index) @ normal_matrix
            lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            normals /= np.where(lengths > 0, lengths, 1)

    uvs = None
    if primitive.texcoordset:
        uvs = gather(primitive.texcoordset[0], primitive.texcoord_indexset[0])[:, :2]

    has_color = bool(primitive.sources.get("COLOR"))
    return _Corners(positions, normals, uvs, has_color)


def _split_polygons(vcounts: np.ndarray) -> np.ndarray:
    """Corner indices of each triangle of a polylist, split as three.js does.

    A quad becomes (0, 1, 3) and (1, 2, 3), and a larger polygon a fan around
    its first corner. Polygons with fewer than three corners are dropped.
    """
    starts = np.cumsum(vcounts) - vcounts
    per_polygon = np.maximum(vcounts - 2, 0)
    polygon = np.repeat(np.arange(len(vcounts)), per_polygon)
    k = np.arange(per_polygon.sum()) - np.repeat(
        np.cumsum(per_polygon) - per_polygon, per_polygon
    )
    local = np.stack([np.zeros_like(k), k + 1, k + 2], axis=1)
    quad = vcounts[polygon] == 4
    local[quad & (k == 0)] = (0, 1, 3)
    local[quad & (k == 1)] = (1, 2, 3)
    return starts[polygon, None] + local


def _triangle_mesh(
    pieces: list[_Corners], warnings: list[str], notes: list[str]
) -> ColladaMesh:
    """Merge the primitives into one indexed triangle mesh."""
    positions = np.concatenate([p.positions for p in pieces])
    normals = uvs = None
    if pieces[0].normals is not None:
        normals = np.concatenate([p.normals for p in pieces])
    if pieces[0].uvs is not None:
        uvs = np.concatenate([p.uvs for p in pieces])

    # Triangles with infinite corners draw nothing in three.js. (pycollada
    # reads NaN as 0, whereas three.js would skip those too.)
    finite = np.repeat(np.isfinite(positions).all(axis=1).reshape(-1, 3).all(1), 3)
    positions = positions[finite]
    if len(positions) == 0:
        return _empty_mesh(warnings + ["no triangle geometry found"], notes)

    # Share vertices between corners at the same position, so the mesh is
    # connected in Blender. Zero-area triangles draw nothing; drop them.
    unique, inverse = np.unique(positions, axis=0, return_inverse=True)
    triangles = inverse.reshape(-1, 3)
    nondegenerate = (
        (triangles[:, 0] != triangles[:, 1])
        & (triangles[:, 1] != triangles[:, 2])
        & (triangles[:, 0] != triangles[:, 2])
    )
    kept = np.flatnonzero(finite)[np.repeat(nondegenerate, 3)]
    triangles = triangles[nondegenerate]
    if len(triangles) == 0:
        return _empty_mesh(warnings + ["no triangle geometry found"], notes)

    used, remap = np.unique(triangles, return_inverse=True)
    return ColladaMesh(
        positions=unique[used],
        triangles=remap.reshape(-1, 3).astype(np.int32),
        corner_normals=np.nan_to_num(normals[kept]) if normals is not None else None,
        corner_uvs=np.nan_to_num(uvs[kept]) if uvs is not None else None,
        warnings=warnings,
        notes=notes,
    )


def _empty_mesh(warnings: list[str], notes: list[str]) -> ColladaMesh:
    return ColladaMesh(
        positions=np.zeros((0, 3)),
        triangles=np.zeros((0, 3), dtype=np.int32),
        warnings=warnings,
        notes=notes,
    )
