# SPDX-License-Identifier: MIT
"""Collada (.dae) reader that reproduces what Meshcat displays.

Drake sends a .dae mesh as a ``_meshfile_geometry`` with format "dae". Meshcat
turns it into one non-indexed geometry with
``merge_geometries(new ColladaLoader().parse(data).scene)`` (three.js r176) and
shades it with the material Drake sends alongside it. This module follows the
same steps, quirks included, so the Blender object matches the browser:

- Each primitive type (``triangles``, ``polylist``, ...) of a ``<geometry>``
  becomes one stream of per-corner values. Corners whose ``<p>`` entry is
  missing push nothing, so short or ragged data shifts every later triangle,
  as in three.js.
- Node transforms (``matrix``, ``translate``, ``rotate``, ``scale``), nested
  nodes and ``instance_node`` are baked into the vertices. A geometry
  instanced more than once is one shared three.js geometry, and
  merge_geometries transforms it in place once per instance. Every copy is
  therefore drawn at the product of all the instance transforms.
- ``<unit>`` and ``<up_axis>`` are ignored. ColladaLoader applies them only to
  ``scene.rotation`` and ``scene.scale``, and merge_geometries reads
  ``scene.matrix``, which is never updated.
- ``polygons``, lines and skinned meshes are not drawn. Merging meshes whose
  attributes differ (say one with normals and one without) fails, and so do
  several malformed inputs; Meshcat then shows nothing, and so is nothing
  imported here.
- Materials, textures and vertex colors are not shown by Meshcat, so they are
  only tracked as far as they affect the steps above.

Each skipped or ignored item is reported in ``ColladaMesh.warnings`` or
``ColladaMesh.notes``. Parsing of libraries that do not affect geometry
(materials, effects, animations, ...) is not reproduced, so a file that
three.js rejects only because of those still imports.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ColladaMesh:
    """Triangle mesh as Meshcat draws it, in the file's own coordinates."""

    positions: np.ndarray  # Nx3 vertex positions
    triangles: np.ndarray  # Mx3 indices into positions
    corner_normals: np.ndarray | None = None  # (3M)x3 normals, one per corner
    corner_uvs: np.ndarray | None = None  # (3M)x2 texture coordinates per corner
    warnings: list[str] = field(default_factory=list)  # content that was dropped
    notes: list[str] = field(default_factory=list)  # settings ignored, as in Meshcat


class _MeshcatFails(Exception):
    """three.js throws while loading the file, so Meshcat shows nothing."""


# JavaScript number parsing: parseFloat and parseInt accept the longest valid
# prefix of a token and give NaN when there is none.
_JS_FLOAT = re.compile(r"[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_JS_INT = re.compile(r"([+-]?)(?:0[xX]([0-9a-fA-F]+)|(\d+))")
_NOT_PLAIN_FLOAT = re.compile(r"[^0-9eE+\-.\s]")
_NOT_PLAIN_INT = re.compile(r"[^0-9+\-\s]")


def _js_float(token: str) -> float:
    match = _JS_FLOAT.match(token.lstrip())
    if match is None:
        return math.nan
    return float(match.group(0).replace("Infinity", "inf"))


def _js_int(token: str | None) -> float:
    """parseInt, returned as a float so that NaN can be represented."""
    if token is None:
        return math.nan
    match = _JS_INT.match(token.lstrip())
    if match is None:
        return math.nan
    sign, hex_digits, digits = match.groups()
    value = int(hex_digits, 16) if hex_digits else int(digits)
    return float(-value if sign == "-" else value)


def _tokens(text: str | None) -> list[str]:
    # Like ``text.trim().split(/\s+/)``: whitespace-only text is one empty token.
    if not text:
        return []
    return text.split() or [""]


def _floats(text: str | None) -> np.ndarray:
    tokens = _tokens(text)
    if tokens and not _NOT_PLAIN_FLOAT.search(text):
        try:
            return np.array(tokens, dtype=np.float64)
        except ValueError:
            pass
    return np.array([_js_float(t) for t in tokens], dtype=np.float64)


def _ints(text: str | None) -> np.ndarray:
    tokens = _tokens(text)
    if tokens and not _NOT_PLAIN_INT.search(text):
        try:
            return np.array(tokens, dtype=np.int64).astype(np.float64)
        except ValueError:
            pass
    return np.array([_js_int(t) for t in tokens], dtype=np.float64)


def _js_max(a: float, b: float) -> float:
    return math.nan if math.isnan(a) or math.isnan(b) else max(a, b)


def _url_id(url: str | None) -> str:
    # ColladaLoader drops the first character ("#") of every URL.
    if url is None:
        raise _MeshcatFails("a reference has no url/source attribute")
    return url[1:]


def _children(el: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in el if child.tag == tag]


def _first_library(root: ET.Element, library: str, tag: str) -> list[ET.Element]:
    # ColladaLoader reads only the first library element of each kind.
    libraries = _children(root, library)
    return _children(libraries[0], tag) if libraries else []


@dataclass
class _Source:
    array: np.ndarray  # Flat values
    stride: float  # parseInt of the accessor stride; may be NaN


@dataclass
class _Primitive:
    type: str
    inputs: dict[str, tuple[str, float]]  # key -> (source id, offset)
    stride: float
    has_uv: bool
    vcount: np.ndarray | None
    p: np.ndarray | None


@dataclass
class _GeometryData:
    sources: dict[str | None, _Source]
    vertices: dict[str | None, str]  # semantic -> source id
    primitives: list[_Primitive]
    skinned: bool = False
    build: list[_TypeGeometry] | None = None


class _TypeGeometry:
    """One three.js BufferGeometry: a geometry's primitives of one type."""

    def __init__(self, primitive_type: str):
        self.type = primitive_type
        self.attributes: dict[str, tuple[np.ndarray, float]] = {}
        self.skinned = False

    def apply_matrix(self, matrix: np.ndarray) -> None:
        """BufferGeometry.applyMatrix4, which mutates the shared geometry."""
        positions = self._xyz("position")
        if positions is not None:
            homogeneous = np.c_[positions, np.ones(len(positions))] @ matrix.T
            with np.errstate(divide="ignore", invalid="ignore"):
                positions[:] = homogeneous[:, :3] / homogeneous[:, 3:]
        normals = self._xyz("normal")
        if normals is not None:
            linear = matrix[:3, :3]
            if not np.isfinite(linear).all() or np.linalg.det(linear) == 0:
                normal_matrix = np.zeros((3, 3))
            else:
                normal_matrix = np.linalg.inv(linear).T
            normals[:] = normals @ normal_matrix.T
            lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            lengths[(lengths == 0) | np.isnan(lengths)] = 1.0
            normals /= lengths

    def _xyz(self, name: str) -> np.ndarray | None:
        """Writable view of the xyz part of each vector of an attribute."""
        if name not in self.attributes:
            return None
        values, size = self.attributes[name]
        vectors = _vectors(values, size)
        return vectors[:, :3] if vectors is not None else None


def _vectors(values: np.ndarray, size: float) -> np.ndarray | None:
    """View a flat attribute as rows of ``size``, if it has an xyz part."""
    if math.isnan(size) or size < 3:
        return None
    size = int(size)
    count = len(values) // size
    return values[: count * size].reshape(count, size)


class _Object3D:
    """The parts of a three.js Object3D that merge_geometries depends on."""

    def __init__(self, kind: str, geometry: _TypeGeometry | None = None):
        self.kind = kind  # "group", "mesh", "skinned", "line" or "other"
        self.geometry = geometry
        self.matrix = np.eye(4)
        self.children: list[_Object3D] = []
        self.parent: _Object3D | None = None

    def add(self, child: _Object3D) -> None:
        if child.parent is not None:
            child.parent.children.remove(child)
        child.parent = self
        self.children.append(child)

    def clone(self) -> _Object3D:
        # Object3D.clone is recursive, but meshes keep sharing their geometry.
        copy = _Object3D(self.kind, self.geometry)
        copy.matrix = self.matrix.copy()
        for child in self.children:
            copy.add(child.clone())
        return copy


@dataclass
class _NodeData:
    id: str | None
    matrix: np.ndarray
    nodes: list[str | None] = field(default_factory=list)
    cameras: list[str] = field(default_factory=list)
    controllers: list[str] = field(default_factory=list)
    lights: list[str] = field(default_factory=list)
    geometries: list[str] = field(default_factory=list)
    instance_nodes: list[str] = field(default_factory=list)
    build: _Object3D | None = None
    building: bool = False


class _Loader:
    """ColladaLoader.parse followed by Meshcat's merge_geometries."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.warnings: list[str] = []
        self.notes: list[str] = []
        self.geometries: dict[str | None, _GeometryData] = {}
        self.nodes: dict[str | None, _NodeData] = {}
        self.controllers: dict[str | None, dict] = {}
        self.visual_scenes: dict[str | None, list[_NodeData]] = {}
        self.cameras: set[str | None] = set()
        self.lights: set[str | None] = set()
        self._default_ids = 0

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def load(self) -> _TypeGeometry | None:
        self._read_asset()
        self.cameras = {
            el.get("id")
            for el in _first_library(self.root, "library_cameras", "camera")
        }
        self.lights = {
            el.get("id") for el in _first_library(self.root, "library_lights", "light")
        }
        for el in _first_library(self.root, "library_controllers", "controller"):
            self._read_controller(el)
        for el in _first_library(self.root, "library_geometries", "geometry"):
            self._read_geometry(el)
        for el in _first_library(self.root, "library_nodes", "node"):
            self._read_node(el)
        for el in _first_library(self.root, "library_visual_scenes", "visual_scene"):
            self._read_visual_scene(el)

        # Like ColladaLoader, build every material, controller, geometry and
        # visual scene, used or not; any of them can make the whole load fail.
        self._check_materials()
        for controller in self.controllers.values():
            self._build_controller(controller)
        for geometry in self.geometries.values():
            self._build_geometry(geometry)
        scenes = {
            scene_id: self._build_visual_scene(children)
            for scene_id, children in self.visual_scenes.items()
        }

        scene_elements = _children(self.root, "scene")
        instances = (
            _children(scene_elements[0], "instance_visual_scene")
            if scene_elements
            else []
        )
        if not instances:
            raise _MeshcatFails("no <scene>/<instance_visual_scene>")
        scene_id = _url_id(instances[0].get("url"))
        if scene_id not in scenes:
            raise _MeshcatFails(f"visual scene {scene_id!r} not found")
        return self._merge(scenes[scene_id])

    # Libraries

    def _read_asset(self) -> None:
        assets = _children(self.root, "asset")
        if not assets:
            raise _MeshcatFails("no <asset>")
        units = _children(assets[0], "unit")
        if units and units[0].get("meter") is not None:
            meter = units[0].get("meter")
            if _js_float(meter) != 1.0:
                self.notes.append(
                    f'<unit meter="{meter}"> ignored, as Meshcat does not apply it'
                )
        axes = _children(assets[0], "up_axis")
        if axes:
            axis = "".join(axes[0].itertext())
            if axis != "Y_UP":
                self.notes.append(
                    f"<up_axis>{axis}</up_axis> ignored, as Meshcat does not apply it"
                )

    def _read_controller(self, el: ET.Element) -> None:
        controller: dict = {}
        for child in el:
            if child.tag in ("skin", "morph"):
                controller["id"] = _url_id(child.get("source"))
            if child.tag == "skin":
                controller["skin"] = child
        self.controllers[el.get("id")] = controller

    def _read_geometry(self, el: ET.Element) -> None:
        meshes = _children(el, "mesh")
        if not meshes:
            return
        data = _GeometryData(sources={}, vertices={}, primitives=[])
        for child in meshes[0]:
            if child.tag == "source":
                data.sources[child.get("id")] = _read_source(child)
            elif child.tag == "vertices":
                data.vertices = {
                    inp.get("semantic"): _url_id(inp.get("source")) for inp in child
                }
            elif child.tag in ("triangles", "polylist", "lines", "linestrips"):
                data.primitives.append(_read_primitive(child))
            elif child.tag in ("polygons", "tristrips", "trifans"):
                self.warn(f"<{child.tag}> skipped; three.js's ColladaLoader rejects it")
        self.geometries[el.get("id")] = data

    def _read_node(self, el: ET.Element) -> _NodeData:
        data = _NodeData(id=el.get("id"), matrix=np.eye(4))
        for child in el:
            tag = child.tag
            if tag == "node":
                data.nodes.append(child.get("id"))
                self._read_node(child)
            elif tag == "instance_camera":
                data.cameras.append(_url_id(child.get("url")))
            elif tag == "instance_controller":
                data.controllers.append(_url_id(child.get("url")))
            elif tag == "instance_light":
                data.lights.append(_url_id(child.get("url")))
            elif tag == "instance_geometry":
                data.geometries.append(_url_id(child.get("url")))
            elif tag == "instance_node":
                data.instance_nodes.append(_url_id(child.get("url")))
            elif tag in ("matrix", "translate", "rotate", "scale"):
                data.matrix = data.matrix @ _transform(tag, _floats(child.text))
            elif tag in ("lookat", "skew"):
                self.warn(f"<{tag}> transform ignored, as Meshcat does")
        if data.id in self.nodes:
            self.warn(f"duplicate node id {data.id!r}; Meshcat uses the first one")
        else:
            self.nodes[data.id] = data
        return data

    def _read_visual_scene(self, el: ET.Element) -> None:
        for node in el.iter("node"):
            if node.get("id") is None:
                node.set("id", f"three_default_{self._default_ids}")
                self._default_ids += 1
        self.visual_scenes[el.get("id")] = [
            self._read_node(node) for node in _children(el, "node")
        ]

    # Building

    def _check_materials(self) -> None:
        """Raise where ColladaLoader's material build would throw.

        Materials do not change what Meshcat draws, but a material whose effect
        cannot be built makes the whole file fail to load.
        """
        effects = {
            el.get("id"): el
            for el in _first_library(self.root, "library_effects", "effect")
        }
        for material in _first_library(self.root, "library_materials", "material"):
            instances = _children(material, "instance_effect")
            effect_id = _url_id(instances[-1].get("url")) if instances else None
            effect = effects.get(effect_id)
            profiles = _children(effect, "profile_COMMON") if effect is not None else []
            if not profiles or not _children(profiles[-1], "technique"):
                raise _MeshcatFails(
                    f"material {material.get('id')!r} has no usable effect"
                )

    def _build_controller(self, controller: dict) -> None:
        if "skin" not in controller:
            return
        geometry = self.geometries.get(controller.get("id"))
        if geometry is None:
            raise _MeshcatFails("a skin controller's source geometry is missing")
        _check_skin(controller["skin"])
        geometry.skinned = True

    def _build_geometry(self, data: _GeometryData) -> list[_TypeGeometry]:
        if data.build is not None:
            return data.build
        groups: dict[str, list[_Primitive]] = {}
        for primitive in data.primitives:
            groups.setdefault(primitive.type, []).append(primitive)
        data.build = [
            self._build_type_geometry(prim_type, prims, data)
            for prim_type, prims in groups.items()
        ]
        return data.build

    def _build_type_geometry(
        self, prim_type: str, primitives: list[_Primitive], data: _GeometryData
    ) -> _TypeGeometry:
        """ColladaLoader's buildGeometryType for one primitive type."""
        streams: dict[str, list[np.ndarray]] = {
            name: [] for name in ("position", "normal", "color", "uv", "uv1")
        }
        sizes: dict[str, float] = {name: 0.0 for name in streams}
        num_uv = sum(prim.has_uv for prim in primitives)
        uvs_need_fix = 0 < num_uv < len(primitives)
        skin_count = 0

        def push(name, prim, source_id, offset, size_name=None):
            source = data.sources.get(source_id)
            if source is None:
                raise _MeshcatFails(f"source {source_id!r} not found")
            values = _gather(prim, source, offset)
            streams[name].append(values)
            sizes[size_name or name] = source.stride
            return values

        for prim in primitives:
            for key, (source_id, offset) in prim.inputs.items():
                if key == "VERTEX":
                    for semantic, vertex_source in data.vertices.items():
                        if semantic == "POSITION":
                            values = push("position", prim, vertex_source, offset)
                            stride = data.sources[vertex_source].stride
                            if data.skinned:
                                skin_count += _corner_count(prim, offset)
                            if not prim.has_uv and uvs_need_fix and stride > 0:
                                vertices = math.ceil(len(values) / stride)
                                streams["uv"].append(np.zeros(2 * vertices))
                        elif semantic == "NORMAL":
                            push("normal", prim, vertex_source, offset)
                        elif semantic == "COLOR":
                            push("color", prim, vertex_source, offset)
                        elif semantic == "TEXCOORD":
                            push("uv", prim, vertex_source, offset)
                        elif semantic == "TEXCOORD1":
                            # ColladaLoader sets the uv stride here, not uv1's.
                            push("uv1", prim, vertex_source, offset, "uv")
                elif key == "NORMAL":
                    push("normal", prim, source_id, offset)
                elif key == "COLOR":
                    push("color", prim, source_id, offset)
                elif key == "TEXCOORD":
                    push("uv", prim, source_id, offset)
                elif key == "TEXCOORD1":
                    push("uv1", prim, source_id, offset)

        geometry = _TypeGeometry(prim_type)
        for name, parts in streams.items():
            values = np.concatenate(parts) if parts else np.zeros(0)
            if len(values):
                geometry.attributes[name] = (values, sizes[name])
        geometry.skinned = skin_count > 0
        return geometry

    def _objects(self, data: _GeometryData) -> list[_Object3D]:
        """buildObjects: one new object per primitive type, sharing geometry."""
        objects = []
        for geometry in self._build_geometry(data):
            if geometry.type in ("lines", "linestrips"):
                objects.append(_Object3D("line", geometry))
            elif geometry.skinned:
                objects.append(_Object3D("skinned", geometry))
            else:
                objects.append(_Object3D("mesh", geometry))
        return objects

    def _node(self, node_id: str | None) -> _Object3D:
        data = self.nodes.get(node_id)
        if data is None:
            raise _MeshcatFails(f"node {node_id!r} not found")
        if data.build is None:
            if data.building:
                raise _MeshcatFails("instance_node cycle")
            data.building = True
            data.build = self._build_node(data)
        return data.build

    def _build_node(self, data: _NodeData) -> _Object3D:
        """ColladaLoader's buildNode."""
        objects = [self._node(node_id) for node_id in data.nodes]
        objects += [_Object3D("other") for cam in data.cameras if cam in self.cameras]
        for controller_id in data.controllers:
            controller = self.controllers.get(controller_id)
            if controller is None:
                raise _MeshcatFails(f"controller {controller_id!r} not found")
            geometry = self.geometries.get(controller.get("id"))
            if geometry is None:
                raise _MeshcatFails(f"controller {controller_id!r} has no geometry")
            if "skin" not in controller:
                raise _MeshcatFails("an instanced <morph> controller")
            objects += self._objects(geometry)
        objects += [_Object3D("other") for light in data.lights if light in self.lights]
        for geometry_id in data.geometries:
            geometry = self.geometries.get(geometry_id)
            if geometry is None:
                raise _MeshcatFails(f"geometry {geometry_id!r} not found")
            objects += self._objects(geometry)
        objects += [self._node(node_id).clone() for node_id in data.instance_nodes]

        if not data.nodes and len(objects) == 1:
            # A lone object stands in for the node, and takes the node's matrix
            # in place of its own.
            obj = objects[0]
        else:
            obj = _Object3D("group")
            for child in objects:
                obj.add(child)
        obj.matrix = data.matrix.copy()
        return obj

    def _build_visual_scene(self, children: list[_NodeData]) -> _Object3D:
        scene = _Object3D("group")
        for child in children:
            scene.add(self._node(child.id))
        return scene

    # Meshcat

    def _merge(self, scene: _Object3D) -> _TypeGeometry | None:
        """Meshcat's merge_geometries, then three.js's mergeGeometries."""
        geometries = []

        def visit(obj: _Object3D, parent_matrix: np.ndarray) -> None:
            matrix = parent_matrix @ obj.matrix
            if obj.kind == "mesh":
                obj.geometry.apply_matrix(matrix)
                geometries.append(obj.geometry)
            elif obj.kind == "line":
                self.warn("lines skipped; Meshcat does not draw them as a mesh")
            elif obj.kind == "skinned":
                self.warn("skinned mesh skipped; Meshcat does not draw skins")
            for child in obj.children:
                visit(child, matrix)

        visit(scene, scene.matrix)
        if not geometries:
            return None
        if len(geometries) == 1:
            return geometries[0]

        layout = {name: size for name, (_, size) in geometries[0].attributes.items()}
        for geometry in geometries[1:]:
            other = {name: size for name, (_, size) in geometry.attributes.items()}
            if other.keys() != layout.keys() or any(
                not _same_size(other[name], layout[name]) for name in layout
            ):
                raise _MeshcatFails(
                    "its meshes have different attributes (e.g. normals or UVs on "
                    "only some), so three.js cannot merge them"
                )
        merged = _TypeGeometry("triangles")
        for name, size in layout.items():
            merged.attributes[name] = (
                np.concatenate([g.attributes[name][0] for g in geometries]),
                size,
            )
        return merged


def _same_size(a: float, b: float) -> bool:
    return a == b or (math.isnan(a) and math.isnan(b))


def _read_source(el: ET.Element) -> _Source:
    source = _Source(np.zeros(0), 3.0)
    for child in el:
        if child.tag in ("float_array", "Name_array"):
            source.array = _floats(child.text)
        elif child.tag == "technique_common":
            accessors = _children(child, "accessor")
            if accessors:
                source.stride = _js_int(accessors[0].get("stride"))
    return source


def _read_primitive(el: ET.Element) -> _Primitive:
    prim = _Primitive(el.tag, {}, 0.0, False, None, None)
    for child in el:
        if child.tag == "input":
            semantic = child.get("semantic")
            offset = _js_int(child.get("offset"))
            set_index = _js_int(child.get("set"))
            key = f"{semantic}{int(set_index)}" if set_index > 0 else semantic
            prim.inputs[key] = (_url_id(child.get("source")), offset)
            prim.stride = _js_max(prim.stride, offset + 1)
            prim.has_uv |= semantic == "TEXCOORD"
        elif child.tag == "vcount":
            prim.vcount = _ints(child.text)
        elif child.tag == "p":
            prim.p = _ints(child.text)
    return prim


def _check_skin(skin: ET.Element) -> None:
    """Raise where ColladaLoader's skin build would throw."""
    sources = {s.get("id"): s for s in _children(skin, "source")}
    joints = _children(skin, "joints")
    weights = _children(skin, "vertex_weights")
    if not joints or not weights:
        raise _MeshcatFails("a <skin> lacks <joints> or <vertex_weights>")
    joint_inputs = {
        inp.get("semantic"): inp.get("source") for inp in _children(joints[0], "input")
    }
    weight_inputs = {
        inp.get("semantic"): inp.get("source") for inp in _children(weights[0], "input")
    }
    if (
        "JOINT" not in weight_inputs
        or "WEIGHT" not in weight_inputs
        or (weight_inputs["WEIGHT"] or "")[1:] not in sources
        or (joint_inputs.get("JOINT") or "")[1:] not in sources
        or not _children(weights[0], "vcount")
    ):
        raise _MeshcatFails("a <skin> is incomplete")
    joint_source = sources[joint_inputs["JOINT"][1:]]
    has_joints = any(
        _tokens(el.text)
        for el in joint_source
        if el.tag in ("float_array", "Name_array")
    )
    if has_joints and (joint_inputs.get("INV_BIND_MATRIX") or "")[1:] not in sources:
        raise _MeshcatFails("a <skin> lacks INV_BIND_MATRIX")


def _transform(tag: str, values: np.ndarray) -> np.ndarray:
    """A node transform element as a 4x4 matrix, padded with NaN like three.js."""
    needed = {"matrix": 16, "translate": 3, "rotate": 4, "scale": 3}[tag]
    if len(values) < needed:
        values = np.r_[values, np.full(needed - len(values), np.nan)]
    if tag == "matrix":
        return values[:16].reshape(4, 4)  # Collada matrices are row-major
    if tag == "translate":
        matrix = np.eye(4)
        matrix[:3, 3] = values[:3]
        return matrix
    if tag == "scale":
        return np.diag([values[0], values[1], values[2], 1.0])
    return _rotation_matrix(values[:3], math.radians(values[3]))


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


def _corner_starts(prim: _Primitive) -> np.ndarray:
    """Index into ``<p>`` of each corner's first input, like ColladaLoader.

    Quads become (0, 1, 3), (1, 2, 3); larger polygons fan around their first
    corner. Values can be NaN, which then read nothing.
    """
    stride = prim.stride
    if prim.p is None:
        raise _MeshcatFails(f"<{prim.type}> has no <p>")
    if prim.vcount is None:
        if math.isnan(stride):
            return np.zeros(1) if len(prim.p) else np.zeros(0)
        if stride <= 0:
            raise _MeshcatFails(f"<{prim.type}> has a zero stride")
        return np.arange(0, len(prim.p), stride, dtype=np.float64)

    starts = []
    base = 0.0
    for n in prim.vcount.tolist():
        if n == 3:
            starts += [base, base + stride, base + 2 * stride]
        elif n == 4:
            a, b, c, d = (base + k * stride for k in range(4))
            starts += [a, b, d, b, c, d]
        elif n > 4:
            for k in range(1, int(n) - 1):
                starts += [base, base + k * stride, base + (k + 1) * stride]
        base += stride * n
    return np.array(starts, dtype=np.float64)


def _p_entries(prim: _Primitive, offset: float) -> np.ndarray:
    """The ``<p>`` value at ``offset`` for each corner; NaN where there is none."""
    index = _corner_starts(prim) + offset
    valid = np.isfinite(index) & (index >= 0) & (index < len(prim.p))
    entries = np.full(len(index), np.nan)
    entries[valid] = prim.p[index[valid].astype(np.int64)]
    return entries


def _corner_count(prim: _Primitive, offset: float) -> int:
    return int(np.isfinite(_p_entries(prim, offset)).sum())


def _gather(prim: _Primitive, source: _Source, offset: float) -> np.ndarray:
    """Values ColladaLoader pushes for one input: ``stride`` per valid corner."""
    entries = _p_entries(prim, offset)
    entries = entries[np.isfinite(entries)]
    stride = source.stride
    if math.isnan(stride) or stride <= 0 or len(entries) == 0:
        return np.zeros(0)
    stride = int(stride)
    index = (entries * stride).astype(np.int64)[:, None] + np.arange(stride)
    inside = (index >= 0) & (index < len(source.array))
    values = np.full(index.shape, np.nan)
    values[inside] = source.array[index[inside]]
    return values.ravel()


def parse_collada(data: bytes | str) -> ColladaMesh:
    """Read a Collada document into the triangle mesh Meshcat would draw.

    Args:
        data: Contents of a .dae file

    Returns:
        ColladaMesh holding every drawn triangle, with node transforms baked
        in. ``warnings`` lists content that was dropped and why; ``notes``
        lists file settings ignored because Meshcat ignores them. The mesh is
        empty when Meshcat would show nothing.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return _empty_mesh([f"not valid XML ({exc}); Meshcat shows nothing"])

    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    if root.tag != "COLLADA":
        return _empty_mesh([f"root element is <{root.tag}>; Meshcat shows nothing"])

    loader = _Loader(root)
    try:
        geometry = loader.load()
    except _MeshcatFails as exc:
        message = f"Meshcat fails to load this file ({exc}) and shows nothing"
        return _empty_mesh(loader.warnings + [message], loader.notes)
    mesh = _triangle_mesh(geometry, loader.warnings)
    mesh.notes = loader.notes
    return mesh


def _triangle_mesh(geometry: _TypeGeometry | None, warnings: list[str]) -> ColladaMesh:
    """Turn the merged non-indexed geometry into an indexed triangle mesh."""
    if geometry is None or "position" not in geometry.attributes:
        return _empty_mesh(warnings + ["no triangle geometry found"])
    positions = _vectors(*geometry.attributes["position"])
    if positions is None:
        return _empty_mesh(warnings + ["unusable position data"])
    corners = len(positions) // 3 * 3
    positions = positions[:corners, :3]

    normals = _corner_attribute(geometry, "normal", corners, 3)
    uvs = _corner_attribute(geometry, "uv", corners, 2)

    # Triangles with NaN corners draw nothing in three.js.
    keep = np.isfinite(positions).all(axis=1).reshape(-1, 3).all(axis=1)
    corner_keep = np.repeat(keep, 3)
    positions = positions[corner_keep]
    if len(positions) == 0:
        return _empty_mesh(warnings + ["no triangle geometry found"])

    # Share vertices between corners at the same position, so the mesh is
    # connected in Blender. Zero-area triangles draw nothing; drop them.
    unique, inverse = _weld(positions)
    triangles = inverse.reshape(-1, 3)
    nondegenerate = (
        (triangles[:, 0] != triangles[:, 1])
        & (triangles[:, 1] != triangles[:, 2])
        & (triangles[:, 0] != triangles[:, 2])
    )
    kept_corners = np.flatnonzero(corner_keep)[np.repeat(nondegenerate, 3)]
    triangles = triangles[nondegenerate]
    if len(triangles) == 0:
        return _empty_mesh(warnings + ["no triangle geometry found"])

    used, remap = np.unique(triangles, return_inverse=True)
    return ColladaMesh(
        positions=unique[used],
        triangles=remap.reshape(-1, 3).astype(np.int32),
        corner_normals=normals[kept_corners] if normals is not None else None,
        corner_uvs=uvs[kept_corners] if uvs is not None else None,
        warnings=warnings,
    )


def _weld(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unique rows of ``points`` and, for each row, the index of its match.

    Same as ``np.unique(points, axis=0, return_inverse=True)``, but faster.
    """
    order = np.lexsort(points.T[::-1])
    ordered = points[order]
    starts = np.r_[True, (np.diff(ordered, axis=0) != 0).any(axis=1)]
    inverse = np.empty(len(points), dtype=np.int64)
    inverse[order] = np.cumsum(starts) - 1
    return ordered[starts], inverse


def _corner_attribute(
    geometry: _TypeGeometry, name: str, corners: int, width: int
) -> np.ndarray | None:
    """An attribute aligned with the first ``corners`` positions.

    WebGL reads zeros past the end of a short attribute, so it is zero-padded.
    """
    if name not in geometry.attributes:
        return None
    values, size = geometry.attributes[name]
    if math.isnan(size) or size < width:
        return None
    size = int(size)
    rows = values[: len(values) // size * size].reshape(-1, size)[:corners, :width]
    out = np.zeros((corners, width))
    out[: len(rows)] = rows
    return np.nan_to_num(out)


def _empty_mesh(warnings: list[str], notes: list[str] | None = None) -> ColladaMesh:
    return ColladaMesh(
        positions=np.zeros((0, 3)),
        triangles=np.zeros((0, 3), dtype=np.int32),
        warnings=list(warnings),
        notes=list(notes or []),
    )
