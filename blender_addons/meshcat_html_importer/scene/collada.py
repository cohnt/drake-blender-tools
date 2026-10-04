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
  therefore drawn at the product of all the instance transforms. A node whose
  only content is an ``instance_node`` gives the instanced copy its own
  transform in place of the copy's.
- ``<unit>`` and ``<up_axis>`` are ignored. ColladaLoader applies them only to
  ``scene.rotation`` and ``scene.scale``, and merge_geometries reads
  ``scene.matrix``, which is never updated.
- ``polygons``, lines and skinned meshes are not drawn.
- Materials, textures and vertex colors are not shown, since Meshcat uses the
  material Drake sends. They are only checked where three.js would fail on
  them.
- Where three.js throws, Meshcat shows nothing, and nothing is imported. This
  covers meshes whose attributes differ (say one with normals and one
  without), which three.js cannot merge, and many malformed inputs: missing
  references, unusable materials, effects, images, cameras or lights,
  instanced morph controllers, incomplete skins, and more.

Each skipped or ignored item is reported in ``ColladaMesh.warnings`` or
``ColladaMesh.notes``. Not reproduced: failures that come only from
``<library_animations>``, ``<library_animation_clips>`` or the kinematics and
physics libraries, which do not affect geometry; such files still import.
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


# Larger inputs exhaust the browser before they draw anything.
_MAX_VALUES = 2**31

# JavaScript number parsing: parseFloat and parseInt accept the longest valid
# prefix of a token and give NaN when there is none.
_JS_FLOAT = re.compile(
    r"[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", re.ASCII
)
_JS_INT = re.compile(r"([+-]?)(?:0[xX]([0-9a-fA-F]*)|(\d+))", re.ASCII)
_NOT_PLAIN_FLOAT = re.compile(r"[^0-9eE+\-.\s]")
_NOT_PLAIN_INT = re.compile(r"[^0-9+\-\s]")

# Name of the document's root element, after any prolog.
_ROOT_NAME = re.compile(
    rb"\A(?:\xef\xbb\xbf)?(?:\s+|<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^\[>]*(?:\[.*?\])?\s*>)*"
    rb"<([^\s/>]+)",
    re.S,
)

_SHADERS = ("constant", "lambert", "blinn", "phong")
_TEXTURED_PARAMETERS = ("diffuse", "specular", "bump", "ambient", "emission")
_OPAQUE_MODES = ("A_ONE", "RGB_ZERO", "A_ZERO", "RGB_ONE")


def _js_float(token: str) -> float:
    match = _JS_FLOAT.match(token.lstrip())
    if match is None:
        return math.nan
    return float(match.group(0).replace("Infinity", "inf"))


def _js_int(token: str | None) -> float:
    """parseInt, returned as a float so that NaN and Infinity can be represented."""
    if token is None:
        return math.nan
    match = _JS_INT.match(token.lstrip())
    if match is None:
        return math.nan
    sign, hex_digits, digits = match.groups()
    if hex_digits == "":
        return math.nan  # "0x" with no digits
    value = int(hex_digits, 16) if hex_digits is not None else int(digits)
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    return -number if sign == "-" else number


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
        except (ValueError, OverflowError):
            pass
    return np.array([_js_float(t) for t in tokens], dtype=np.float64)


def _ints(text: str | None) -> np.ndarray:
    tokens = _tokens(text)
    if tokens and not _NOT_PLAIN_INT.search(text):
        try:
            return np.array(tokens, dtype=np.int64).astype(np.float64)
        except (ValueError, OverflowError):
            pass
    return np.array([_js_int(t) for t in tokens], dtype=np.float64)


def _js_max(a: float, b: float) -> float:
    return math.nan if math.isnan(a) or math.isnan(b) else max(a, b)


def _text(el: ET.Element) -> str:
    # Like the DOM's textContent: the text of the element and all descendants.
    return "".join(el.itertext())


def _key(value: str | None) -> str:
    # A missing attribute used as a JavaScript object key becomes "null".
    return "null" if value is None else value


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


def _by_id(elements: list[ET.Element]) -> dict[str, ET.Element]:
    # Library entries are stored by id, so a later duplicate replaces an earlier one.
    return {_key(el.get("id")): el for el in elements}


@dataclass
class _Source:
    array: np.ndarray  # Flat values
    stride: float  # parseInt of the accessor stride; may be NaN


@dataclass
class _Primitive:
    type: str
    material: str | None
    count: float  # parseInt of the count attribute
    inputs: dict[str, tuple[str, float]] = field(default_factory=dict)  # (id, offset)
    stride: float = 0.0
    has_uv: bool = False
    vcount: np.ndarray | None = None
    p: np.ndarray | None = None
    starts: np.ndarray | None = None  # Cached result of _corner_starts


@dataclass
class _GeometryData:
    sources: dict[str, _Source] = field(default_factory=dict)
    vertices: dict[str, str] = field(default_factory=dict)  # semantic -> source id
    primitives: list[_Primitive] = field(default_factory=list)
    skinned: bool = False
    build: list[_TypeGeometry] | None = None


@dataclass
class _Controller:
    geometry_id: str | None  # None when there is no <skin> or <morph>
    skin: ET.Element | None


@dataclass
class _Instance:
    """An instance_geometry or instance_controller."""

    id: str
    materials: dict[str, str]  # bind_material symbol -> material id


class _TypeGeometry:
    """One three.js BufferGeometry: a geometry's primitives of one type."""

    def __init__(self, primitive_type: str):
        self.type = primitive_type
        self.attributes: dict[str, tuple[np.ndarray, float]] = {}
        self.material_keys: list[str] = []
        self.skinned = False

    def apply_matrix(self, matrix: np.ndarray) -> None:
        """BufferGeometry.applyMatrix4, which mutates the shared geometry."""
        positions = self._xyz("position")
        if positions is not None:
            homogeneous = np.c_[positions, np.ones(len(positions))] @ matrix.T
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
    id: str
    matrix: np.ndarray
    nodes: list[str] = field(default_factory=list)
    cameras: list[str] = field(default_factory=list)
    controllers: list[_Instance] = field(default_factory=list)
    lights: list[str] = field(default_factory=list)
    geometries: list[_Instance] = field(default_factory=list)
    instance_nodes: list[str] = field(default_factory=list)
    build: _Object3D | None = None
    building: bool = False


class _Loader:
    """ColladaLoader.parse followed by Meshcat's merge_geometries."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.warnings: list[str] = []
        self.notes: list[str] = []
        self.geometries: dict[str, _GeometryData] = {}
        self.nodes: dict[str, _NodeData] = {}
        self.controllers: dict[str, _Controller] = {}
        self.visual_scenes: dict[str, list[_NodeData]] = {}
        self.cameras = _by_id(_first_library(root, "library_cameras", "camera"))
        self.lights = _by_id(_first_library(root, "library_lights", "light"))
        self.materials = _by_id(_first_library(root, "library_materials", "material"))
        self.effects = _by_id(_first_library(root, "library_effects", "effect"))
        self._default_ids = 0

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def load(self) -> _TypeGeometry | None:
        self._read_asset()
        for el in _first_library(self.root, "library_controllers", "controller"):
            self._read_controller(el)
        for el in _first_library(self.root, "library_geometries", "geometry"):
            self._read_geometry(el)
        for el in _first_library(self.root, "library_nodes", "node"):
            self._read_node(el)
        for el in _first_library(self.root, "library_visual_scenes", "visual_scene"):
            self._read_visual_scene(el)

        # Like ColladaLoader, build every library entry, used or not; any of
        # them can make the whole load fail.
        self._check_libraries()
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
            axis = _text(axes[0])
            if axis != "Y_UP":
                self.notes.append(
                    f"<up_axis>{axis}</up_axis> ignored, as Meshcat does not apply it"
                )

    def _read_controller(self, el: ET.Element) -> None:
        controller = _Controller(geometry_id=None, skin=None)
        for child in el:
            if child.tag in ("skin", "morph"):
                controller.geometry_id = _url_id(child.get("source"))
            if child.tag == "skin":
                controller.skin = child
        self.controllers[_key(el.get("id"))] = controller

    def _read_geometry(self, el: ET.Element) -> None:
        meshes = _children(el, "mesh")
        if not meshes:
            return
        data = _GeometryData()
        for child in meshes[0]:
            if child.tag == "source":
                data.sources[_key(child.get("id"))] = _read_source(child)
            elif child.tag == "vertices":
                data.vertices = {
                    _key(inp.get("semantic")): _url_id(inp.get("source"))
                    for inp in child
                }
            elif child.tag in ("triangles", "polylist", "lines", "linestrips"):
                data.primitives.append(_read_primitive(child))
            elif child.tag in ("polygons", "tristrips", "trifans"):
                self.warn(f"<{child.tag}> skipped; three.js's ColladaLoader rejects it")
        self.geometries[_key(el.get("id"))] = data

    def _read_node(self, el: ET.Element) -> _NodeData:
        data = _NodeData(id=_key(el.get("id")), matrix=np.eye(4))
        for child in el:
            tag = child.tag
            if tag == "node":
                data.nodes.append(_key(child.get("id")))
                self._read_node(child)
            elif tag == "instance_camera":
                data.cameras.append(_url_id(child.get("url")))
            elif tag == "instance_controller":
                data.controllers.append(_read_instance(child))
            elif tag == "instance_light":
                data.lights.append(_url_id(child.get("url")))
            elif tag == "instance_geometry":
                data.geometries.append(_read_instance(child))
            elif tag == "instance_node":
                data.instance_nodes.append(_url_id(child.get("url")))
            elif tag in ("matrix", "translate", "rotate", "scale"):
                data.matrix = data.matrix @ _transform(tag, _floats(_text(child)))
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
        self.visual_scenes[_key(el.get("id"))] = [
            self._read_node(node) for node in _children(el, "node")
        ]

    # Building

    def _check_libraries(self) -> None:
        """Raise where ColladaLoader fails to build an image, camera, light or
        material. None of them change what Meshcat draws."""
        for image in _first_library(self.root, "library_images", "image"):
            if not _children(image, "init_from"):
                raise _MeshcatFails(f"image {image.get('id')!r} has no <init_from>")
        for camera_id, camera in self.cameras.items():
            if not _children(camera, "optics"):
                raise _MeshcatFails(f"camera {camera_id!r} has no <optics>")
        for light_id, light in self.lights.items():
            techniques = _children(light, "technique_common")
            kinds = ("directional", "point", "spot", "ambient")
            if not techniques or not any(c.tag in kinds for c in techniques[-1]):
                raise _MeshcatFails(f"light {light_id!r} has no known type")
        for material_id, material in self.materials.items():
            self._check_material(material_id, material)

    def _check_material(self, material_id: str, material: ET.Element) -> None:
        """Raise where ColladaLoader's buildMaterial would throw."""
        instances = _children(material, "instance_effect")
        effect_id = _url_id(instances[-1].get("url")) if instances else "undefined"
        effect = self.effects.get(effect_id)
        profiles = _children(effect, "profile_COMMON") if effect is not None else []
        techniques = _children(profiles[-1], "technique") if profiles else []
        shaders = [c for c in techniques[-1] if c.tag in _SHADERS] if techniques else []
        if not shaders:
            raise _MeshcatFails(f"material {material_id!r} has no usable effect")
        profile, technique = profiles[-1], techniques[-1]

        # A texture whose sampler names no surface makes three.js throw.
        surfaces = set()
        samplers = {}
        for newparam in _children(profile, "newparam"):
            sid = _key(newparam.get("sid"))
            for child in newparam:
                if child.tag == "surface":
                    surfaces.add(sid)
                elif child.tag == "sampler2D":
                    sources = _children(child, "source")
                    samplers[sid] = _text(sources[-1]) if sources else "undefined"

        def check_texture(texture: ET.Element) -> None:
            sampler = _key(texture.get("texture"))
            if sampler in samplers and samplers[sampler] not in surfaces:
                raise _MeshcatFails(f"sampler {sampler!r} has no surface")

        parameters = {child.tag: child for child in shaders[-1]}
        for name in _TEXTURED_PARAMETERS:
            textures = (
                _children(parameters[name], "texture") if name in parameters else []
            )
            if textures:
                check_texture(textures[-1])

        # Opacity is read from the <transparent> color, which must then exist.
        transparent = parameters.get("transparent")
        if (
            transparent is not None
            and not _children(transparent, "texture")
            and not _children(transparent, "color")
            and transparent.get("opaque", "A_ONE") in _OPAQUE_MODES
        ):
            raise _MeshcatFails(f"material {material_id!r} has an empty <transparent>")

        # So does a <bump> without a <texture> in the technique's <extra>.
        extras = _children(technique, "extra")
        extra_techniques = _children(extras[-1], "technique") if extras else []
        bumps = _children(extra_techniques[-1], "bump") if extra_techniques else []
        if bumps:
            textures = _children(bumps[-1], "texture")
            if not textures:
                raise _MeshcatFails(f"material {material_id!r} has an empty <bump>")
            check_texture(textures[-1])

    def _build_controller(self, controller: _Controller) -> None:
        if controller.skin is None:
            return
        geometry = self.geometries.get(controller.geometry_id)
        if geometry is None:
            raise _MeshcatFails("a skin controller's source geometry is missing")
        _check_skin(controller.skin)
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
            if prim.type == "polylist" and prim.vcount is None and prim.count >= 1:
                raise _MeshcatFails("<polylist> has no <vcount>")
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
        geometry.material_keys = [prim.material for prim in primitives if prim.material]
        geometry.skinned = skin_count > 0
        return geometry

    def _objects(self, instance: _Instance, data: _GeometryData) -> list[_Object3D]:
        """buildObjects: one new object per primitive type, sharing geometry."""
        objects = []
        for geometry in self._build_geometry(data):
            for key in geometry.material_keys:
                material_id = instance.materials.get(key)
                if material_id is not None and material_id not in self.materials:
                    raise _MeshcatFails(f"material {material_id!r} not found")
            if geometry.type in ("lines", "linestrips"):
                objects.append(_Object3D("line", geometry))
            elif geometry.skinned:
                objects.append(_Object3D("skinned", geometry))
            else:
                objects.append(_Object3D("mesh", geometry))
        return objects

    def _node(self, node_id: str) -> _Object3D:
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
        for instance in data.controllers:
            controller = self.controllers.get(instance.id)
            if controller is None:
                raise _MeshcatFails(f"controller {instance.id!r} not found")
            geometry = self.geometries.get(controller.geometry_id)
            if geometry is None:
                raise _MeshcatFails(f"controller {instance.id!r} has no geometry")
            objects += self._objects(instance, geometry)
            if controller.skin is None:
                raise _MeshcatFails("an instanced <morph> controller")
        objects += [_Object3D("other") for light in data.lights if light in self.lights]
        for instance in data.geometries:
            geometry = self.geometries.get(instance.id)
            if geometry is None:
                raise _MeshcatFails(f"geometry {instance.id!r} not found")
            objects += self._objects(instance, geometry)
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
    source = _Source(array=np.zeros(0), stride=3.0)
    for child in el:
        if child.tag in ("float_array", "Name_array"):
            source.array = _floats(_text(child))
        elif child.tag == "technique_common":
            accessors = _children(child, "accessor")
            if accessors:
                source.stride = _js_int(accessors[0].get("stride"))
    return source


def _read_primitive(el: ET.Element) -> _Primitive:
    prim = _Primitive(
        type=el.tag, material=el.get("material"), count=_js_int(el.get("count"))
    )
    for child in el:
        if child.tag == "input":
            semantic = child.get("semantic") or "null"
            offset = _js_int(child.get("offset"))
            set_index = _js_int(child.get("set"))
            key = f"{semantic}{int(set_index)}" if set_index > 0 else semantic
            prim.inputs[key] = (_url_id(child.get("source")), offset)
            prim.stride = _js_max(prim.stride, offset + 1)
            prim.has_uv |= semantic == "TEXCOORD"
        elif child.tag == "vcount":
            prim.vcount = _ints(_text(child))
        elif child.tag == "p":
            prim.p = _ints(_text(child))
    return prim


def _read_instance(el: ET.Element) -> _Instance:
    # ColladaLoader reads every <instance_material> inside each <bind_material>.
    materials = {
        _key(binding.get("symbol")): _url_id(binding.get("target"))
        for bind_material in _children(el, "bind_material")
        for binding in bind_material.iter("instance_material")
    }
    return _Instance(id=_url_id(el.get("url")), materials=materials)


def _check_skin(skin: ET.Element) -> None:
    """Raise where ColladaLoader's skin build would throw."""
    sources = _by_id(_children(skin, "source"))
    joints = _children(skin, "joints")
    weights = _children(skin, "vertex_weights")
    if not joints or not weights:
        raise _MeshcatFails("a <skin> lacks <joints> or <vertex_weights>")
    joint_inputs = {
        _key(inp.get("semantic")): _url_id(inp.get("source"))
        for inp in _children(joints[-1], "input")
    }
    weight_inputs = {
        _key(inp.get("semantic")): _url_id(inp.get("source"))
        for inp in _children(weights[-1], "input")
    }
    vcounts = _children(weights[-1], "vcount")
    if (
        "JOINT" not in weight_inputs
        or weight_inputs.get("WEIGHT") not in sources
        or joint_inputs.get("JOINT") not in sources
        or not vcounts
    ):
        raise _MeshcatFails("a <skin> is incomplete")
    if not _children(weights[-1], "v") and (_ints(_text(vcounts[-1])) > 0).any():
        raise _MeshcatFails("a <skin> has <vcount> but no <v>")
    joint_arrays = [
        child
        for child in sources[joint_inputs["JOINT"]]
        if child.tag in ("float_array", "Name_array")
    ]
    has_joints = bool(joint_arrays) and bool(_tokens(_text(joint_arrays[-1])))
    if has_joints and joint_inputs.get("INV_BIND_MATRIX") not in sources:
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
    if math.isfinite(angle):
        c = math.cos(angle)
        s = math.sin(angle)
    else:
        c = s = math.nan  # Math.cos(Infinity) is NaN in JavaScript
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
    if prim.starts is None:
        prim.starts = _compute_corner_starts(prim)
    return prim.starts


def _compute_corner_starts(prim: _Primitive) -> np.ndarray:
    stride = prim.stride
    if prim.p is None:
        raise _MeshcatFails(f"<{prim.type}> has no <p>")
    if prim.vcount is None:
        if math.isnan(stride):
            return np.zeros(1) if len(prim.p) else np.zeros(0)
        if stride <= 0:
            raise _MeshcatFails(f"<{prim.type}> has a zero stride")
        return np.arange(0, len(prim.p), stride, dtype=np.float64)

    sides = prim.vcount
    triangles = np.where(
        sides == 3, 1, np.where(sides == 4, 2, np.where(sides > 4, sides - 2, 0))
    )
    if 3 * triangles.sum() > _MAX_VALUES:
        raise _MeshcatFails("<polylist> is too large to load")
    triangles = triangles.astype(np.int64)
    bases = np.r_[0.0, np.cumsum(stride * sides)[:-1]]

    polygon = np.repeat(np.arange(len(sides)), triangles)
    k = np.arange(triangles.sum()) - np.repeat(
        np.cumsum(triangles) - triangles, triangles
    )
    quad = sides[polygon] == 4
    first = np.where(quad & (k == 1), 1, 0)
    second = np.where(quad, np.where(k == 0, 1, 2), k + 1)
    third = np.where(quad, 3, k + 2)
    base = bases[polygon]
    corners = np.stack([first, second, third], axis=1) * stride + base[:, None]
    return corners.ravel()


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
    """Values ColladaLoader pushes for one input: ``stride`` per valid corner.

    Values past either end of the source array are NaN (undefined in JS).
    """
    entries = _p_entries(prim, offset)
    entries = entries[np.isfinite(entries)]
    stride = source.stride
    if math.isnan(stride) or stride <= 0 or len(entries) == 0:
        return np.zeros(0)
    if stride * len(entries) > _MAX_VALUES:
        raise _MeshcatFails("an input is too large to load")
    stride = int(stride)
    starts = entries * stride
    values = np.full((len(entries), stride), np.nan)
    overlaps = (starts > -stride) & (starts < len(source.array))
    index = starts[overlaps].astype(np.int64)[:, None] + np.arange(stride)
    inside = (index >= 0) & (index < len(source.array))
    rows = np.full(index.shape, np.nan)
    rows[inside] = source.array[index[inside]]
    values[overlaps] = rows
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

    # three.js looks for a document child named "COLLADA". It finds a
    # <!DOCTYPE COLLADA> first, and misses a namespace-prefixed root.
    root_name = _ROOT_NAME.match(data)
    if root_name is not None:
        if re.search(rb"<!DOCTYPE\s+COLLADA\b", data[: root_name.start(1)]):
            return _empty_mesh(["<!DOCTYPE COLLADA> makes Meshcat show nothing"])
        if b":" in root_name.group(1):
            return _empty_mesh(["a prefixed root element makes Meshcat show nothing"])

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
    with np.errstate(all="ignore"):  # NaN and Inf are expected from bad files.
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
