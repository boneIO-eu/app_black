#!/usr/bin/env python3
"""Detect redundant local imports that shadow top-level imports.

Finds cases where a module/name is imported at the top of a file AND
again inside a function or method. Only reports when the local import
is identical to the top-level one (same source module AND name).

Intentional lazy imports (names NOT imported at top level, or imported
from a different module) are ignored.

Usage:
    python scripts/check_duplicate_imports.py [path ...]
    python scripts/check_duplicate_imports.py boneio/

Exit codes:
    0 — no duplicates found
    1 — duplicates found (prints report)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _import_key(module: str | None, name: str, alias: str | None = None) -> str:
    """Build a unique key for an import binding.

    For ``import foo`` the key is ``foo``.
    For ``import foo as bar`` the key is ``foo->bar``.
    For ``from bar import baz`` the key is ``bar::baz``.

    This prevents false positives when the same *name* is imported
    from two different modules (e.g. ``INA219`` as a const string
    vs. ``INA219`` as a class), and when the same module is imported
    with different aliases (e.g. ``import time as _boot_time`` vs
    ``import time as _time``).

    Args:
        module: Source module (None for bare ``import X``).
        name: Imported symbol name.
        alias: Alias if ``as`` was used (None otherwise).

    Returns:
        Unique string identifying the import.
    """
    if module:
        return f"{module}::{alias or name}"
    if alias:
        return f"{name}->{alias}"
    return name


def _collect_top_level_imports(tree: ast.Module) -> set[str]:
    """Return set of import keys at module top level.

    Handles both ``import X`` and ``from X import Y`` forms.
    Only considers statements at module body level (not inside
    functions, classes, or conditionals).

    Args:
        tree: Parsed AST module.

    Returns:
        Set of import keys (e.g. {"json", "boneio.const::COVER"}).
    """
    keys: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                keys.add(_import_key(None, alias.name, alias.asname))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                keys.add(_import_key(node.module, alias.name, alias.asname))
    return keys


def _find_local_imports(tree: ast.Module) -> list[tuple[int, str, str]]:
    """Find all imports inside functions/methods.

    Args:
        tree: Parsed AST module.

    Returns:
        List of (line_number, import_key, human_readable_statement).
    """
    results: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    key = _import_key(None, alias.name, alias.asname)
                    stmt = f"import {alias.name}"
                    if alias.asname:
                        stmt += f" as {alias.asname}"
                    results.append((child.lineno, key, stmt))
            elif isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    key = _import_key(child.module, alias.name, alias.asname)
                    stmt = f"from {child.module} import {alias.name}"
                    if alias.asname:
                        stmt += f" as {alias.asname}"
                    results.append((child.lineno, key, stmt))

    return results


def check_file(filepath: Path) -> list[str]:
    """Check a single Python file for redundant local imports.

    Args:
        filepath: Path to the Python file.

    Returns:
        List of human-readable error messages.
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    top_level = _collect_top_level_imports(tree)
    local_imports = _find_local_imports(tree)

    errors: list[str] = []
    for lineno, key, stmt in local_imports:
        if key in top_level:
            errors.append(f"  {filepath}:{lineno}: '{stmt}' — already imported at top level")

    return errors


def main() -> int:
    """Entry point. Scans provided paths for redundant imports.

    Returns:
        0 if no issues found, 1 otherwise.
    """
    paths = sys.argv[1:] or ["boneio/"]

    py_files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == ".py":
            py_files.append(path)
        elif path.is_dir():
            py_files.extend(path.rglob("*.py"))

    all_errors: list[str] = []
    for f in sorted(py_files):
        all_errors.extend(check_file(f))

    if all_errors:
        print("❌ Redundant local imports (already imported at top level):\n")
        for err in all_errors:
            print(err)
        print(f"\n{len(all_errors)} redundant import(s) found.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
