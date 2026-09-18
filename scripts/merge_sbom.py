#!/usr/bin/env python3
"""Merge component inventories into the one SBOM that describes a release.

boneIO is built from two ecosystems — the Python application and the pnpm
frontend that is served from it — and each has its own generator. What has to
exist at release time is a single answer to "what is in this version", because
the question that makes an SBOM worth having arrives in the form "there is a
vulnerability in X, are you affected", and nobody chasing that wants to be told
to look in two files and work out which one applies.

The merge is deliberately conservative. Components are carried over as their
generator emitted them, licences and hashes included; nothing is inferred or
tidied. The only thing rewritten is each input's root reference, which is
repointed at the product component so the dependency graphs join up instead of
dangling.

Usage:
    merge_sbom.py --output boneio-1.6.0.cdx.json \\
        --name boneio --version 1.6.0 \\
        python.cdx.json frontend.cdx.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SPEC_VERSION = "1.6"


def _root_ref(bom: dict[str, Any]) -> str | None:
    """Return the bom-ref of a document's own root component, if it has one.

    Args:
        bom: A parsed CycloneDX document.

    Returns:
        The root component's ``bom-ref``, or None when the document does not
        name one.
    """
    return bom.get("metadata", {}).get("component", {}).get("bom-ref")


def _component_key(component: dict[str, Any]) -> str:
    """Return a stable identity for de-duplication.

    ``bom-ref`` is authoritative where it exists. ``purl`` is the fallback,
    because two generators describing the same package agree on the purl far
    more often than they agree on anything else.

    Args:
        component: A CycloneDX component.

    Returns:
        A key that is equal for two entries describing the same package.
    """
    return (
        component.get("bom-ref")
        or component.get("purl")
        or f"{component.get('name')}@{component.get('version')}"
    )


def _remap(obj: Any, mapping: dict[str, str]) -> Any:
    """Rewrite every bom-ref in *obj* according to *mapping*.

    Args:
        obj: Any part of a CycloneDX document.
        mapping: Old ref to new ref.

    Returns:
        The same structure with references rewritten.
    """
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in ("bom-ref", "ref") and isinstance(value, str):
                out[key] = mapping.get(value, value)
            elif key == "dependsOn" and isinstance(value, list):
                out[key] = [mapping.get(v, v) for v in value]
            else:
                out[key] = _remap(value, mapping)
        return out
    if isinstance(obj, list):
        return [_remap(item, mapping) for item in obj]
    return obj


def merge(
    boms: list[dict[str, Any]],
    name: str,
    version: str,
    component_type: str = "application",
    purl: str | None = None,
) -> dict[str, Any]:
    """Combine several CycloneDX documents into one.

    Args:
        boms: Parsed CycloneDX documents, in the order they should appear.
        name: Name of the product the merged document describes.
        version: Version of that product.
        component_type: CycloneDX component type for the product.
        purl: Package URL for the product, if it has one.

    Returns:
        A CycloneDX document describing *name* at *version*.

    Raises:
        ValueError: If an input is not a CycloneDX document.
    """
    product_ref = f"{name}@{version}"
    product: dict[str, Any] = {
        "type": component_type,
        "bom-ref": product_ref,
        "name": name,
        "version": version,
    }
    if purl:
        product["purl"] = purl

    components: dict[str, dict[str, Any]] = {}
    dependencies: dict[str, set[str]] = {product_ref: set()}
    tools: list[dict[str, Any]] = []

    for bom in boms:
        if bom.get("bomFormat") != "CycloneDX":
            raise ValueError("input is not a CycloneDX document")

        mapping = {}
        source_root = _root_ref(bom)
        if source_root:
            mapping[source_root] = product_ref
        bom = _remap(bom, mapping)

        for component in bom.get("components", []):
            key = _component_key(component)
            # First writer wins. A component present in both inputs is the same
            # package seen twice, not two packages; picking the later one would
            # silently prefer whichever generator happened to run last.
            components.setdefault(key, component)

        for entry in bom.get("dependencies", []):
            ref = entry.get("ref")
            if not ref:
                continue
            dependencies.setdefault(ref, set()).update(entry.get("dependsOn", []))

        bom_tools = bom.get("metadata", {}).get("tools", {})
        for tool in (
            bom_tools.get("components", []) if isinstance(bom_tools, dict) else bom_tools
        ):
            if tool not in tools:
                tools.append(tool)

    # Anything nothing else depends on hangs off the product, so the graph has
    # a single root and a reader can walk it.
    depended_on = {d for deps in dependencies.values() for d in deps}
    for key in components:
        if key not in depended_on:
            dependencies[product_ref].add(key)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": product,
            "tools": {"components": tools} if tools else {},
        },
        "components": list(components.values()),
        "dependencies": [
            {"ref": ref, "dependsOn": sorted(deps)}
            for ref, deps in sorted(dependencies.items())
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command line arguments, or None for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="CycloneDX JSON documents")
    parser.add_argument("--output", required=True, help="where to write the merge")
    parser.add_argument("--name", required=True, help="product name")
    parser.add_argument("--version", required=True, help="product version")
    parser.add_argument("--type", default="application", help="CycloneDX component type")
    parser.add_argument("--purl", default=None, help="package URL of the product")
    args = parser.parse_args(argv)

    boms = []
    for path in args.inputs:
        try:
            boms.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"merge_sbom: cannot read {path}: {exc}", file=sys.stderr)
            return 1

    try:
        merged = merge(boms, args.name, args.version, args.type, args.purl)
    except ValueError as exc:
        print(f"merge_sbom: {exc}", file=sys.stderr)
        return 1

    Path(args.output).write_text(
        json.dumps(merged, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(
        f"merge_sbom: {len(merged['components'])} components "
        f"from {len(boms)} inputs -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
