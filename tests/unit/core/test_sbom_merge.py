"""Tests for the SBOM merge that produces one inventory per release.

An SBOM is only ever read in a hurry — something has just been published
against a library and somebody needs to know whether boneIO ships it. So what
these tests protect is not the file's shape but its usefulness: every component
survives the merge, versions and licences are not rewritten, and the dependency
graph still has one root to walk from.
"""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "merge_sbom.py"

merge_sbom = SourceFileLoader("merge_sbom", str(SCRIPT)).load_module()


def _bom(root: str, components: list[dict], dependencies: list[dict] | None = None):
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "application", "bom-ref": root, "name": root}},
        "components": components,
        "dependencies": dependencies or [],
    }


def _component(name, version, purl, **extra):
    return {
        "type": "library",
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
        **extra,
    }


@pytest.fixture
def python_bom():
    return _bom(
        "root-python",
        [
            _component("fastapi", "0.118.0", "pkg:pypi/fastapi@0.118.0",
                       licenses=[{"license": {"id": "MIT"}}]),
            _component("pyyaml", "6.0.3", "pkg:pypi/pyyaml@6.0.3"),
        ],
        [
            {"ref": "root-python", "dependsOn": ["pkg:pypi/fastapi@0.118.0"]},
            {"ref": "pkg:pypi/fastapi@0.118.0", "dependsOn": ["pkg:pypi/pyyaml@6.0.3"]},
        ],
    )


@pytest.fixture
def npm_bom():
    return _bom(
        "root-npm",
        [
            _component("react", "18.3.1", "pkg:npm/react@18.3.1"),
            _component("vite", "5.4.0", "pkg:npm/vite@5.4.0"),
        ],
        [{"ref": "root-npm", "dependsOn": ["pkg:npm/react@18.3.1"]}],
    )


def test_every_component_survives(python_bom, npm_bom):
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    names = {c["name"] for c in merged["components"]}
    assert names == {"fastapi", "pyyaml", "react", "vite"}


def test_versions_and_licences_are_not_rewritten(python_bom, npm_bom):
    """The merge is an inventory, not an opinion."""
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    fastapi = next(c for c in merged["components"] if c["name"] == "fastapi")
    assert fastapi["version"] == "0.118.0"
    assert fastapi["licenses"] == [{"license": {"id": "MIT"}}]


def test_the_product_is_the_single_root(python_bom, npm_bom):
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    assert merged["metadata"]["component"]["bom-ref"] == "boneio@1.6.0"
    assert merged["metadata"]["component"]["version"] == "1.6.0"


def test_the_inputs_roots_are_repointed_at_the_product(python_bom, npm_bom):
    """Otherwise each input's graph dangles from a ref nothing declares."""
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    refs = {d["ref"] for d in merged["dependencies"]}
    assert "root-python" not in refs
    assert "root-npm" not in refs

    product = next(d for d in merged["dependencies"] if d["ref"] == "boneio@1.6.0")
    assert "pkg:pypi/fastapi@0.118.0" in product["dependsOn"]
    assert "pkg:npm/react@18.3.1" in product["dependsOn"]


def test_the_graph_reaches_every_component(python_bom, npm_bom):
    """A component nothing points at is a component nobody will find."""
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    edges = {d["ref"]: d["dependsOn"] for d in merged["dependencies"]}

    seen, stack = set(), list(edges["boneio@1.6.0"])
    while stack:
        ref = stack.pop()
        if ref in seen:
            continue
        seen.add(ref)
        stack.extend(edges.get(ref, []))

    assert {c["bom-ref"] for c in merged["components"]} <= seen


def test_transitive_edges_are_preserved(python_bom, npm_bom):
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    edges = {d["ref"]: d["dependsOn"] for d in merged["dependencies"]}
    assert edges["pkg:pypi/fastapi@0.118.0"] == ["pkg:pypi/pyyaml@6.0.3"]


def test_a_package_in_both_inputs_appears_once(python_bom):
    """Same package, seen twice — not two packages."""
    other = _bom("root-other", [_component("pyyaml", "6.0.3", "pkg:pypi/pyyaml@6.0.3")])
    merged = merge_sbom.merge([python_bom, other], "boneio", "1.6.0")
    assert [c["name"] for c in merged["components"]].count("pyyaml") == 1


def test_a_non_cyclonedx_input_is_refused(python_bom):
    """Better to fail the release than to attach an inventory that is not one."""
    with pytest.raises(ValueError):
        merge_sbom.merge([python_bom, {"components": []}], "boneio", "1.6.0")


def test_the_document_declares_what_it_is(python_bom, npm_bom):
    merged = merge_sbom.merge([python_bom, npm_bom], "boneio", "1.6.0")
    assert merged["bomFormat"] == "CycloneDX"
    assert merged["specVersion"] == "1.6"
    assert merged["serialNumber"].startswith("urn:uuid:")
    assert merged["metadata"]["timestamp"].endswith("Z")


def test_two_merges_do_not_share_a_serial_number(python_bom):
    """The serial number identifies this document, not this product."""
    a = merge_sbom.merge([python_bom], "boneio", "1.6.0")
    b = merge_sbom.merge([python_bom], "boneio", "1.6.0")
    assert a["serialNumber"] != b["serialNumber"]


def test_the_script_runs_end_to_end(tmp_path, python_bom, npm_bom):
    """The workflow calls it as a command, so that is what is tested."""
    first = tmp_path / "python.cdx.json"
    second = tmp_path / "npm.cdx.json"
    out = tmp_path / "merged.cdx.json"
    first.write_text(json.dumps(python_bom))
    second.write_text(json.dumps(npm_bom))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(first), str(second),
         "--output", str(out), "--name", "boneio", "--version", "1.6.0",
         "--purl", "pkg:pypi/boneio@1.6.0"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    merged = json.loads(out.read_text())
    assert len(merged["components"]) == 4
    assert merged["metadata"]["component"]["purl"] == "pkg:pypi/boneio@1.6.0"


def test_a_missing_input_fails_loudly(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.json"),
         "--output", str(tmp_path / "o.json"), "--name", "b", "--version", "1"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "cannot read" in result.stderr


def test_an_input_without_a_root_component_still_merges(npm_bom):
    """What ``cyclonedx-py environment`` actually emits.

    It describes an installed environment, not a project, so it has no
    ``metadata.component`` to be the root and its refs are ``name==version``
    rather than purls. An earlier version of the merge assumed both, and
    produced a document whose components hung off nothing.
    """
    environment = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"timestamp": "2026-09-18T00:00:00Z", "tools": {"components": []}},
        "components": [
            {"type": "library", "bom-ref": "fastapi==0.118.0", "name": "fastapi",
             "version": "0.118.0", "purl": "pkg:pypi/fastapi@0.118.0"},
            {"type": "library", "bom-ref": "pyyaml==6.0.3", "name": "pyyaml",
             "version": "6.0.3", "purl": "pkg:pypi/pyyaml@6.0.3"},
        ],
        "dependencies": [
            {"ref": "fastapi==0.118.0", "dependsOn": ["pyyaml==6.0.3"]},
            {"ref": "pyyaml==6.0.3", "dependsOn": []},
        ],
    }
    merged = merge_sbom.merge([environment, npm_bom], "boneio", "1.6.0")

    edges = {d["ref"]: d["dependsOn"] for d in merged["dependencies"]}
    seen, stack = set(), list(edges["boneio@1.6.0"])
    while stack:
        ref = stack.pop()
        if ref in seen:
            continue
        seen.add(ref)
        stack.extend(edges.get(ref, []))

    assert {c["bom-ref"] for c in merged["components"]} <= seen, "orphaned components"
    assert edges["fastapi==0.118.0"] == ["pyyaml==6.0.3"]


def test_the_tool_that_generated_each_input_is_recorded(npm_bom):
    """Part of the provenance: which generator said what."""
    tooled = dict(npm_bom)
    tooled["metadata"] = {
        **npm_bom["metadata"],
        "tools": {"components": [{"type": "application", "name": "cyclonedx-npm",
                                  "version": "1.19.3"}]},
    }
    merged = merge_sbom.merge([tooled], "boneio", "1.6.0")
    assert {t["name"] for t in merged["metadata"]["tools"]["components"]} == {"cyclonedx-npm"}
