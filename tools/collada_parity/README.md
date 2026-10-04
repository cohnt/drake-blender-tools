# Collada parity check

The Meshcat HTML importer reads `.dae` meshes with its own reader
(`packages/meshcat-html-importer/src/meshcat_html_importer/scene/collada.py`),
which is meant to reproduce exactly what the Meshcat browser viewer shows. This
tool checks that claim against Meshcat itself.

For each Collada document, it loads the document in Meshcat's real JavaScript
(Drake's bundled `meshcat.js`, in headless Chromium) the way Drake sends it. It
then compares the geometry Meshcat builds with `parse_collada`, triangle by
triangle and in drawing order, normals included.

This lives on a side branch, not in the add-on, because it needs Chromium and
Drake's `meshcat.js`, neither of which CI has.

## Requirements

- Chromium or Chrome (`--chromium` to point at it)
- Drake's `meshcat.js`: found automatically when `pydrake` is importable,
  otherwise pass `--meshcat-js .../share/drake/geometry/meshcat.js`
- numpy

## Usage

From the repository root:

```bash
# All built-in cases, plus every document the unit tests use
python tools/collada_parity/run_parity.py --unit-tests

# Also check real files (directories are searched recursively)
python tools/collada_parity/run_parity.py --dae path/to/meshes other.dae
```

Each document prints as `ok`, `expected` (a known, documented difference,
listed with its reason in `EXPECTED` in `run_parity.py`) or `MISMATCH`. The
exit code is non-zero if any `MISMATCH` remains.

## Cases

`cases/` holds about 220 documents grouped by topic:

| Module | Covers |
|---|---|
| `basic` | transforms, shared geometry, `instance_node`, attribute mixes, ids |
| `primitives` | primitive types, inputs, sources, libraries |
| `loader_quirks` | skins, morphs, strides, JavaScript number parsing |
| `partial_normals` | a normal attribute shorter than the positions |
| `exporters` | documents shaped like Blender, SketchUp, SolidWorks, assimp, MeshLab, 3ds Max and Maya output |
| `materials_and_malformed` | materials, `bind_material`, effects, malformed documents |
| `static_audit` | throw paths found by reading ColladaLoader |
