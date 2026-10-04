# SPDX-License-Identifier: MIT
"""Compare parse_collada with what Meshcat built for the same documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from meshcat_html_importer.scene.collada import parse_collada
from meshcat_runner import run_meshcat


@dataclass
class Result:
    name: str
    ok: bool
    meshcat_triangles: int
    our_triangles: int
    detail: str


def _array(attribute: dict) -> np.ndarray:
    values = [np.nan if v is None else v for v in attribute["array"]]
    return np.array(values, dtype=float).reshape(-1, attribute["itemSize"])[:, :3]


def _drawn(meshcat: dict) -> tuple[np.ndarray, np.ndarray | None]:
    """Triangles Meshcat draws (NaN and zero-area ones removed) and their normals."""
    if not meshcat.get("found") or "position" not in meshcat["attrs"]:
        return np.zeros((0, 3, 3)), None
    positions = _array(meshcat["attrs"]["position"])
    corners = len(positions) // 3 * 3
    triangles = positions[:corners].reshape(-1, 3, 3)
    normals = None
    if "normal" in meshcat["attrs"]:
        values = _array(meshcat["attrs"]["normal"])[:corners]
        # WebGL reads zeros past the end of a short attribute.
        normals = np.zeros((corners, 3))
        normals[: len(values)] = values
        normals = np.nan_to_num(normals).reshape(-1, 3, 3)
    keep = np.isfinite(triangles).all(axis=(1, 2))
    keep &= ~(
        (triangles[:, 0] == triangles[:, 1]).all(1)
        | (triangles[:, 1] == triangles[:, 2]).all(1)
        | (triangles[:, 0] == triangles[:, 2]).all(1)
    )
    return triangles[keep], normals[keep] if normals is not None else None


def compare(
    cases: dict[str, str], meshcat_js: Path, chromium: str = "chromium"
) -> list[Result]:
    """Compare triangles (in order) and normals for each case."""
    meshcat = run_meshcat(cases, meshcat_js, chromium)
    results = []
    for name, document in cases.items():
        theirs, their_normals = _drawn(meshcat[name])
        try:
            mesh = parse_collada(document)
        except Exception as exc:  # A parity failure, not a harness failure.
            results.append(Result(name, False, len(theirs), -1, f"raised {exc!r}"))
            continue
        ours = mesh.positions[mesh.triangles] if len(mesh.triangles) else theirs[:0]
        same = theirs.shape == ours.shape and np.allclose(theirs, ours, atol=1e-5)
        detail = ""
        if same and len(ours):
            our_normals = mesh.corner_normals
            if our_normals is None and their_normals is not None:
                # Meshcat computes flat normals, and so does Blender for the
                # import. Both work in float32, as three.js does here:
                # (C - B) x (A - B), normalized.
                p = ours.astype(np.float32)
                face = np.cross(p[:, 2] - p[:, 1], p[:, 0] - p[:, 1])
                length = np.linalg.norm(face, axis=1, keepdims=True)
                face /= np.where(length > 0, length, 1)
                same = np.allclose(their_normals, face[:, None, :], atol=1e-3)
            elif (our_normals is None) != (their_normals is None):
                same = False
            elif our_normals is not None:
                same = np.allclose(
                    their_normals, our_normals.reshape(-1, 3, 3), atol=1e-5
                )
            if not same:
                detail = "normals differ"
        elif not same:
            threw = meshcat[name].get("threw")
            detail = f"meshcat threw {threw}" if threw else "triangles differ"
            if mesh.warnings:
                detail += f"; ours: {mesh.warnings[-1]}"
        results.append(Result(name, same, len(theirs), len(ours), detail))
    return results
