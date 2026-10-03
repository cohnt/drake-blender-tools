# SPDX-License-Identifier: MIT
"""Minimal Collada (.dae) reader that matches how Meshcat displays .dae meshes.

Drake sends a .dae mesh as a ``_meshfile_geometry`` with format "dae". Meshcat
turns it into a single geometry with
``merge_geometries(new ColladaLoader().parse(data).scene)`` (three.js r176), and
shades it with the material Drake sends alongside it. Reading meshcat.js and
three.js's ColladaLoader gives the rules this reader follows:

- Node transforms (``matrix``, ``translate``, ``rotate``, ``scale``), nested
  nodes and ``instance_node`` are baked into the vertices, because
  merge_geometries multiplies each node's ``.matrix`` into its meshes.
- ``<unit>`` and ``<up_axis>`` are ignored. ColladaLoader applies them only by
  setting ``scene.rotation`` and ``scene.scale``, without updating
  ``scene.matrix``, and ``scene.matrix`` is what merge_geometries reads.
- Only ``triangles`` and ``polylist`` primitives are kept, and they are
  triangulated the way ColladaLoader does it. ColladaLoader rejects
  ``polygons``. Lines and skinned meshes (``instance_controller``) do not
  become ``Mesh`` objects, so merge_geometries drops them.
- Materials, textures and vertex colors are not read. Meshcat ignores them.

Anything dropped this way is reported in ``ColladaMesh.warnings``.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np

# Primitive types that ColladaLoader parses but that never reach the screen
# in Meshcat, or that it rejects outright.
_DROPPED_PRIMITIVES = {
    "polygons": "not supported by three.js's ColladaLoader",
    "lines": "not drawn as a mesh by Meshcat",
    "linestrips": "not drawn as a mesh by Meshcat",
    "tristrips": "not supported by three.js's ColladaLoader",
    "trifans": "not supported by three.js's ColladaLoader",
}

# Guard against instance_node cycles.
_MAX_NODE_DEPTH = 64


@dataclass
class ColladaMesh:
    """Triangle mesh read from a Collada file, in the file's own coordinates."""

    positions: np.ndarray  # Nx3 vertex positions
    triangles: np.ndarray  # Mx3 indices into positions
    corner_normals: np.ndarray | None = None  # (3M)x3 normals, one per corner
    corner_uvs: np.ndarray | None = None  # (3M)x2 texture coordinates per corner
    warnings: list[str] = field(default_factory=list)


@dataclass
class _GeometryData:
    """Triangulated geometry of one <geometry>, before any node transform."""

    positions: np.ndarray  # Px3 position source
    corners: np.ndarray  # (3T,) indices into positions
    normals: np.ndarray | None  # (3T)x3
    uvs: np.ndarray | None  # (3T)x2


class _Reader:
    """Stateful helper that walks one parsed Collada document."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.warnings: list[str] = []
        self.ids: dict[str, ET.Element] = {}
        for el in root.iter():
            el_id = el.get("id")
            if el_id:
                self.ids.setdefault(el_id, el)
        self._geometry_cache: dict[str, _GeometryData | None] = {}

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def lookup(self, url: str | None) -> ET.Element | None:
        if not url:
            return None
        return self.ids.get(url[1:] if url.startswith("#") else url)

    # Asset

    def check_asset(self) -> None:
        """Report asset settings that Meshcat (and so this reader) ignores."""
        asset = self.root.find("asset")
        if asset is None:
            return

        unit = asset.find("unit")
        if unit is not None:
            meter = unit.get("meter", "1")
            try:
                is_meter = math.isclose(float(meter), 1.0)
            except ValueError:
                is_meter = False
            if not is_meter:
                self.warn(
                    f'<unit meter="{meter}"> ignored; Meshcat does not apply '
                    "Collada units"
                )

        up_axis = asset.find("up_axis")
        if up_axis is not None and up_axis.text:
            axis = up_axis.text.strip()
            if axis != "Y_UP":
                self.warn(
                    f"<up_axis>{axis}</up_axis> ignored; Meshcat does not "
                    "rotate Collada content"
                )

    # Scene graph

    def collect_instances(self) -> list[tuple[str, np.ndarray]]:
        """Return (geometry id, world matrix) for every instanced geometry."""
        scene = self.root.find("scene")
        instance = scene.find("instance_visual_scene") if scene is not None else None
        visual_scene = self.lookup(
            instance.get("url") if instance is not None else None
        )
        if visual_scene is None:
            self.warn("no <scene>/<instance_visual_scene>; Meshcat shows nothing")
            return []

        instances: list[tuple[str, np.ndarray]] = []
        for node in visual_scene.findall("node"):
            self._visit_node(node, np.eye(4), instances, depth=0)
        return instances

    def _visit_node(
        self,
        node: ET.Element,
        parent_matrix: np.ndarray,
        instances: list[tuple[str, np.ndarray]],
        depth: int,
    ) -> None:
        if depth > _MAX_NODE_DEPTH:
            self.warn("node hierarchy too deep (instance_node cycle?); truncated")
            return

        matrix = parent_matrix @ self._local_matrix(node)

        for child in node:
            tag = child.tag
            if tag == "instance_geometry":
                url = child.get("url") or ""
                instances.append((url.lstrip("#"), matrix))
            elif tag == "instance_controller":
                self.warn(
                    "<instance_controller> (skin/morph) skipped; Meshcat does "
                    "not draw skinned meshes"
                )
            elif tag == "node":
                self._visit_node(child, matrix, instances, depth + 1)
            elif tag == "instance_node":
                target = self.lookup(child.get("url"))
                if target is None:
                    self.warn(f"instance_node {child.get('url')!r} not found")
                else:
                    self._visit_node(target, matrix, instances, depth + 1)

    def _local_matrix(self, node: ET.Element) -> np.ndarray:
        """Compose a node's transform elements in document order."""
        matrix = np.eye(4)
        for child in node:
            tag = child.tag
            if tag not in ("matrix", "translate", "rotate", "scale", "lookat", "skew"):
                continue
            if tag in ("lookat", "skew"):
                self.warn(f"<{tag}> transform ignored, as Meshcat does")
                continue

            values = _floats(child.text)
            if tag == "matrix" and len(values) >= 16:
                # Collada matrices are row-major.
                matrix = matrix @ values[:16].reshape(4, 4)
            elif tag == "translate" and len(values) >= 3:
                step = np.eye(4)
                step[:3, 3] = values[:3]
                matrix = matrix @ step
            elif tag == "rotate" and len(values) >= 4:
                matrix = matrix @ _rotation_matrix(values[:3], math.radians(values[3]))
            elif tag == "scale" and len(values) >= 3:
                matrix = matrix @ np.diag([values[0], values[1], values[2], 1.0])
        return matrix

    # Geometry

    def geometry(self, geometry_id: str) -> _GeometryData | None:
        if geometry_id not in self._geometry_cache:
            self._geometry_cache[geometry_id] = self._read_geometry(geometry_id)
        return self._geometry_cache[geometry_id]

    def _read_geometry(self, geometry_id: str) -> _GeometryData | None:
        geometry = self.ids.get(geometry_id)
        if geometry is None or geometry.tag != "geometry":
            self.warn(f"instance_geometry {geometry_id!r} not found")
            return None
        mesh = geometry.find("mesh")
        if mesh is None:
            self.warn(f"geometry {geometry_id!r} has no <mesh>; skipped")
            return None

        vertices = mesh.find("vertices")
        vertex_inputs = {}
        if vertices is not None:
            for inp in vertices.findall("input"):
                vertex_inputs[inp.get("semantic")] = self._source(inp.get("source"))
        positions = vertex_inputs.get("POSITION")
        if positions is None or positions.shape[1] < 3:
            self.warn(f"geometry {geometry_id!r} has no usable POSITION; skipped")
            return None
        positions = positions[:, :3]

        parts = []
        for prim in mesh:
            if prim.tag in _DROPPED_PRIMITIVES:
                self.warn(
                    f"<{prim.tag}> in geometry {geometry_id!r} skipped; "
                    f"{_DROPPED_PRIMITIVES[prim.tag]}"
                )
            elif prim.tag in ("triangles", "polylist"):
                part = self._read_primitive(prim, vertex_inputs, len(positions))
                if part is not None:
                    parts.append(part)

        if not parts:
            return None

        corners = np.concatenate([p[0] for p in parts])
        normals = None
        if all(p[1] is not None for p in parts):
            normals = np.concatenate([p[1] for p in parts])
        elif any(p[1] is not None for p in parts):
            self.warn(
                f"geometry {geometry_id!r} has NORMAL on only some primitives; "
                "normals left to Blender"
            )
        uvs = None
        if any(p[2] is not None for p in parts):
            # Like ColladaLoader, give primitives without UVs zero UVs.
            uvs = np.concatenate(
                [p[2] if p[2] is not None else np.zeros((len(p[0]), 2)) for p in parts]
            )
        return _GeometryData(positions, corners, normals, uvs)

    def _read_primitive(
        self,
        prim: ET.Element,
        vertex_inputs: dict[str, np.ndarray | None],
        num_positions: int,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None] | None:
        """Triangulate one primitive into per-corner index and attribute arrays."""
        inputs: dict[str, tuple[str | None, int]] = {}
        stride = 0
        for inp in prim.findall("input"):
            semantic = inp.get("semantic") or ""
            offset = int(inp.get("offset", "0"))
            set_index = int(inp.get("set", "0") or "0")
            key = f"{semantic}{set_index}" if set_index > 0 else semantic
            inputs[key] = (inp.get("source"), offset)
            stride = max(stride, offset + 1)

        if "VERTEX" not in inputs or stride == 0:
            self.warn(f"<{prim.tag}> without a VERTEX input skipped")
            return None

        # ColladaLoader keeps the last <p> of a primitive.
        p_elements = prim.findall("p")
        p = _ints(p_elements[-1].text) if p_elements else np.zeros(0, dtype=np.int64)
        rows = p[: len(p) // stride * stride].reshape(-1, stride)

        if prim.tag == "triangles":
            order = np.arange(len(rows) // 3 * 3)
        else:
            order = _polylist_corner_order(_ints(_text(prim.find("vcount"))))
            if len(order) and order.max() >= len(rows):
                self.warn("<polylist> vcount exceeds its <p> data; truncated")
                order = order[: len(order) // 3 * 3]
                keep = (order.reshape(-1, 3) < len(rows)).all(axis=1)
                order = order.reshape(-1, 3)[keep].ravel()
        if len(order) == 0:
            return None
        rows = rows[order]

        vertex_index = rows[:, inputs["VERTEX"][1]]
        if vertex_index.min() < 0 or vertex_index.max() >= num_positions:
            self.warn(f"<{prim.tag}> indexes past its POSITION data; skipped")
            return None

        normals = self._corner_attribute(
            inputs.get("NORMAL"), vertex_inputs.get("NORMAL"), rows, vertex_index, 3
        )
        uvs = self._corner_attribute(
            inputs.get("TEXCOORD"), vertex_inputs.get("TEXCOORD"), rows, vertex_index, 2
        )
        return vertex_index, normals, uvs

    def _corner_attribute(
        self,
        prim_input: tuple[str | None, int] | None,
        vertex_source: np.ndarray | None,
        rows: np.ndarray,
        vertex_index: np.ndarray,
        width: int,
    ) -> np.ndarray | None:
        """Gather a per-corner attribute from the primitive or <vertices> inputs."""
        if prim_input is not None:
            source = self._source(prim_input[0])
            index = rows[:, prim_input[1]]
        else:
            source = vertex_source
            index = vertex_index
        if source is None or source.shape[1] < width:
            return None
        if index.min() < 0 or index.max() >= len(source):
            self.warn("attribute index out of range; attribute dropped")
            return None
        return source[index, :width]

    def _source(self, url: str | None) -> np.ndarray | None:
        """Read a <source> as a (count, stride) float array, as ColladaLoader does.

        ColladaLoader reads the whole float_array in steps of the accessor's
        stride, ignoring the accessor's count and offset.
        """
        source = self.lookup(url)
        if source is None:
            return None
        if source.tag == "vertices":
            # A NORMAL/TEXCOORD input may point at <vertices>; use its POSITION.
            for inp in source.findall("input"):
                if inp.get("semantic") == "POSITION":
                    return self._source(inp.get("source"))
            return None
        array = source.find("float_array")
        if array is None:
            return None
        values = _floats(array.text)
        accessor = source.find("technique_common/accessor")
        stride = int(accessor.get("stride", "1")) if accessor is not None else 1
        stride = max(stride, 1)
        return values[: len(values) // stride * stride].reshape(-1, stride)


def parse_collada(data: bytes | str) -> ColladaMesh:
    """Read the triangle geometry of a Collada document the way Meshcat shows it.

    Args:
        data: Contents of a .dae file

    Returns:
        ColladaMesh with every instanced geometry merged into one triangle mesh,
        node transforms baked in. ``warnings`` lists everything that was skipped
        or ignored. The mesh is empty if nothing drawable was found.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return _empty_mesh([f"not valid Collada XML: {exc}"])

    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    if root.tag != "COLLADA":
        return _empty_mesh([f"root element is <{root.tag}>, not <COLLADA>"])

    reader = _Reader(root)
    reader.check_asset()

    positions = []
    triangles = []
    normals = []
    uvs = []
    vertex_count = 0
    for geometry_id, matrix in reader.collect_instances():
        geom = reader.geometry(geometry_id)
        if geom is None:
            continue

        tris = geom.corners.reshape(-1, 3)
        # Degenerate triangles draw nothing in three.js. Drop them so Blender's
        # mesh validation does not have to (and corner data stays aligned).
        keep = (
            (tris[:, 0] != tris[:, 1])
            & (tris[:, 1] != tris[:, 2])
            & (tris[:, 0] != tris[:, 2])
        )
        tris = tris[keep]
        corner_keep = np.repeat(keep, 3)

        # Keep only the positions this instance uses.
        used, remapped = np.unique(tris, return_inverse=True)
        linear = matrix[:3, :3]
        positions.append(geom.positions[used] @ linear.T + matrix[:3, 3])
        triangles.append(remapped.reshape(-1, 3) + vertex_count)
        vertex_count += len(used)

        if geom.normals is not None:
            normals.append(_transform_normals(geom.normals[corner_keep], linear))
        else:
            normals.append(None)
        uvs.append(geom.uvs[corner_keep] if geom.uvs is not None else None)

    if not triangles:
        reader.warn("no triangle geometry found")
        return _empty_mesh(reader.warnings)

    corner_normals = None
    if all(n is not None for n in normals):
        corner_normals = np.concatenate(normals)
    elif any(n is not None for n in normals):
        reader.warn("NORMAL present on only some geometries; normals left to Blender")

    corner_uvs = None
    if any(u is not None for u in uvs):
        corner_uvs = np.concatenate(
            [
                u if u is not None else np.zeros((len(t) * 3, 2))
                for u, t in zip(uvs, triangles)
            ]
        )

    return ColladaMesh(
        positions=np.concatenate(positions),
        triangles=np.concatenate(triangles).astype(np.int32),
        corner_normals=corner_normals,
        corner_uvs=corner_uvs,
        warnings=reader.warnings,
    )


def _polylist_corner_order(vcount: np.ndarray) -> np.ndarray:
    """Row indices that triangulate a polylist exactly like ColladaLoader.

    Quads become (0, 1, 3), (1, 2, 3); larger polygons become a fan around
    their first corner; polygons with fewer than three corners are dropped.
    """
    order = []
    base = 0
    for n in vcount.tolist():
        if n == 3:
            order.extend((base, base + 1, base + 2))
        elif n == 4:
            order.extend((base, base + 1, base + 3, base + 1, base + 2, base + 3))
        elif n > 4:
            for k in range(1, n - 1):
                order.extend((base, base + k, base + k + 1))
        base += n
    return np.array(order, dtype=np.int64)


def _rotation_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    """4x4 rotation about ``axis``, using three.js's makeRotationAxis formula.

    Like three.js, the axis is used as given (not normalized).
    """
    x, y, z = (float(v) for v in axis)
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c
    tx = t * x
    ty = t * y
    return np.array(
        [
            [tx * x + c, tx * y - s * z, tx * z + s * y, 0.0],
            [tx * y + s * z, ty * y + c, ty * z - s * x, 0.0],
            [tx * z - s * y, ty * z + s * x, t * z * z + c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def _transform_normals(normals: np.ndarray, linear: np.ndarray) -> np.ndarray:
    """Apply the normal matrix of ``linear`` and renormalize, as three.js does."""
    try:
        normal_matrix = np.linalg.inv(linear).T
    except np.linalg.LinAlgError:
        normal_matrix = np.zeros((3, 3))
    out = normals @ normal_matrix.T
    lengths = np.linalg.norm(out, axis=1, keepdims=True)
    return np.divide(out, lengths, out=np.zeros_like(out), where=lengths > 0)


def _empty_mesh(warnings: list[str]) -> ColladaMesh:
    return ColladaMesh(
        positions=np.zeros((0, 3)),
        triangles=np.zeros((0, 3), dtype=np.int32),
        warnings=list(warnings),
    )


def _text(el: ET.Element | None) -> str:
    return (el.text or "") if el is not None else ""


def _floats(text: str | None) -> np.ndarray:
    return np.array((text or "").split(), dtype=np.float64)


def _ints(text: str | None) -> np.ndarray:
    return np.array((text or "").split(), dtype=np.int64)
