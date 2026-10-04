# SPDX-License-Identifier: MIT
"""Run Collada documents through Meshcat's own JavaScript in headless Chromium.

Each document is loaded exactly as Drake sends it: a ``set_object`` command
holding a ``_meshfile_geometry`` with format "dae". The geometry Meshcat builds
is dumped from the page and returned for comparison.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

_PAGE = r"""<!DOCTYPE html><html><body>
<div id="pane" style="width:200px;height:200px"></div>
<pre id="out">PENDING</pre>
<script src="file://%JS%"></script>
<script>
const CASES = %CASES%;
const results = {};
const errors = [];
const originalError = console.error;
console.error = function (...a) {
  errors.push(a.map(String).join(" "));
  originalError.apply(console, a);
};
window.onerror = function (message) { errors.push("onerror:" + message); };
var viewer = new MeshCat.Viewer(document.getElementById("pane"));
const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
for (const [name, dae] of Object.entries(CASES)) {
  errors.length = 0;
  try {
    viewer.handle_command({type: "set_object", path: "/case/" + name, object: {
      metadata: {version: 4.5, type: "Object"},
      geometries: [{uuid: "g-" + name, type: "_meshfile_geometry", format: "dae",
                    data: dae}],
      materials: [{uuid: "m-" + name, type: "MeshPhongMaterial", color: 0xcccccc}],
      object: {uuid: "o-" + name, type: "Mesh", geometry: "g-" + name,
               material: "m-" + name, matrix: IDENTITY}}});
    results[name] = {threw: null};
  } catch (e) {
    results[name] = {threw: String(e)};
  }
  results[name].errors = errors.slice();
}
setTimeout(() => {
  for (const name of Object.keys(CASES)) {
    let found = null;
    viewer.scene.traverse(o => {
      if (o.geometry && o.geometry.uuid === "g-" + name) found = o;
    });
    const r = results[name];
    r.found = found !== null;
    if (!found) continue;
    const g = found.geometry;
    r.index = g.index ? Array.from(g.index.array) : null;
    r.attrs = {};
    for (const [n, a] of Object.entries(g.attributes)) {
      r.attrs[n] = {itemSize: a.itemSize, count: a.count, array: Array.from(a.array)};
    }
  }
  document.getElementById("out").textContent = JSON.stringify(results);
}, 500);
</script></body></html>
"""


def run_meshcat(
    cases: dict[str, str], meshcat_js: Path, chromium: str = "chromium"
) -> dict[str, dict]:
    """Load each Collada document in Meshcat and return what it built.

    Args:
        cases: Case name -> Collada document text
        meshcat_js: Path to Drake's meshcat.js
        chromium: Chromium (or Chrome) executable

    Returns:
        Case name -> {"threw", "errors", "found", "index", "attrs"}, where
        "attrs" maps attribute names to {"itemSize", "count", "array"}.
    """
    page = _PAGE.replace("%JS%", str(Path(meshcat_js).resolve())).replace(
        "%CASES%", json.dumps(cases)
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "parity.html"
        path.write_text(page)
        result = subprocess.run(
            [
                chromium,
                "--headless=new",
                "--no-sandbox",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--allow-file-access-from-files",
                "--virtual-time-budget=5000",
                "--dump-dom",
                path.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    match = re.search(r'<pre id="out">(.*?)</pre>', result.stdout, re.S)
    if match is None or match.group(1) == "PENDING":
        raise RuntimeError(f"Meshcat page did not finish:\n{result.stderr[-2000:]}")
    return json.loads(html.unescape(match.group(1)))
