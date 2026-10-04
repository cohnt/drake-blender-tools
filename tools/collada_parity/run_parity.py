# SPDX-License-Identifier: MIT
"""Check that the Collada importer matches Meshcat, triangle for triangle.

Usage, from the repository root, with a Python that has numpy (plus pytest for
``--unit-tests``, and pydrake to find meshcat.js without ``--meshcat-js``):

    python tools/collada_parity/run_parity.py [--meshcat-js PATH]
        [--chromium BIN] [--dae FILE_OR_DIR ...] [--no-cases] [--unit-tests]

Exits non-zero if any document is drawn differently by Meshcat and imported
differently by ``parse_collada``, apart from the known cases listed in
``EXPECTED``.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "packages/meshcat-html-importer/src")]

from compare import compare  # noqa: E402

CASE_MODULES = [
    "basic",
    "primitives",
    "loader_quirks",
    "partial_normals",
    "exporters",
    "materials_and_malformed",
    "static_audit",
]

# Known differences, with the reason each is accepted.
EXPECTED = {
    "exporters/bom": (
        "harness artefact: the BOM reaches ColladaLoader here, but not through "
        "Drake's msgpack path, where Meshcat draws the file"
    ),
    "materials_and_malformed/animation_library_garbage": (
        "animation libraries are not reproduced (see the collada.py docstring)"
    ),
}
# Cases that are not comparable: three.js draws position data of stride 2 by
# reading past each vertex, which has no meaningful Blender equivalent.
SKIPPED = {
    "exporters/position_stride2",
    "materials_and_malformed/position_stride2_two_tris",
}

# Documents per Chromium page, and the most text per page.
BATCH = 40
BATCH_BYTES = 3_000_000


def _default_meshcat_js() -> Path | None:
    try:
        import pydrake
    except ImportError:
        return None
    path = Path(pydrake.getDrakePath()) / "geometry/meshcat.js"
    return path if path.exists() else None


def _case_documents() -> dict[str, str]:
    documents = {}
    for module_name in CASE_MODULES:
        module = importlib.import_module(f"cases.{module_name}")
        for name, document in module.cases.items():
            key = f"{module_name}/{name}"
            if key not in SKIPPED:
                documents[key] = document
    return documents


def _dae_documents(paths: list[Path]) -> dict[str, str]:
    files = []
    for path in paths:
        files += sorted(path.rglob("*.dae")) if path.is_dir() else [path]
    return {f"file:{f}": f.read_text(encoding="utf-8", errors="replace") for f in files}


def _unit_test_documents() -> dict[str, str]:
    """Every document the Collada unit tests parse."""
    sys.path.insert(0, str(REPO / "tests/test_meshcat_importer"))
    import test_collada

    documents = {}
    real_parse = test_collada.parse_collada
    current = ""

    def record(data):
        text = data.decode() if isinstance(data, bytes) else data
        if text.lstrip().startswith("<?xml") or text.lstrip().startswith("<!DOCTYPE"):
            documents[f"{current}#{sum(k.startswith(current) for k in documents)}"] = (
                text
            )
        return real_parse(data)

    test_collada.parse_collada = record
    for cls in (getattr(test_collada, n) for n in dir(test_collada)):
        if not (inspect.isclass(cls) and cls.__name__.startswith("Test")):
            continue
        for name, method in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            argsets = [()]
            for mark in getattr(method, "pytestmark", []):
                if mark.name == "parametrize":
                    argsets = [
                        a if isinstance(a, tuple) else (a,) for a in mark.args[1]
                    ]
            for i, args in enumerate(argsets):
                current = f"unit/{cls.__name__}.{name}[{i}]"
                method(cls(), *args)
    test_collada.parse_collada = real_parse
    return documents


def _batches(documents: dict[str, str]):
    """Group documents into pages that Chromium loads in reasonable time."""
    batch: dict[str, str] = {}
    size = 0
    for name, document in documents.items():
        if batch and (len(batch) == BATCH or size + len(document) > BATCH_BYTES):
            yield batch
            batch, size = {}, 0
        batch[name] = document
        size += len(document)
    if batch:
        yield batch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--meshcat-js", type=Path, default=_default_meshcat_js())
    parser.add_argument("--chromium", default="chromium")
    parser.add_argument("--dae", type=Path, nargs="*", default=[])
    parser.add_argument("--no-cases", action="store_true")
    parser.add_argument("--unit-tests", action="store_true")
    args = parser.parse_args()
    if args.meshcat_js is None:
        parser.error("pydrake not found; pass --meshcat-js (Drake's meshcat.js)")

    documents = {} if args.no_cases else _case_documents()
    documents.update(_dae_documents(args.dae))
    if args.unit_tests:
        documents.update(_unit_test_documents())

    failures = []
    for batch in _batches(documents):
        for result in compare(batch, args.meshcat_js, args.chromium):
            expected = result.name in EXPECTED
            status = "ok" if result.ok else ("expected" if expected else "MISMATCH")
            print(
                f"{status:9} {result.name}: meshcat={result.meshcat_triangles} "
                f"ours={result.our_triangles} {result.detail}"
            )
            if not result.ok and not expected:
                failures.append(result.name)

    print(f"\n{len(documents)} documents, {len(failures)} unexpected mismatches")
    for name in failures:
        print(f"  {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
