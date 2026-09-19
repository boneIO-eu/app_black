"""Every path an application serves, including the nested ones.

Two security guards enumerate routes to prove something is absent — the
interactive docs, and any endpoint that would take a sudo password. From
FastAPI 0.14x an application's ``routes`` holds ``_IncludedRouter`` objects
that have no ``path`` of their own and keep the real routes on
``original_router``, so the obvious comprehension raises.

Skipping what it cannot read would be worse than the exception: the guard
would pass while no longer looking inside the routers where the route it hunts
for would actually live. So anything unrecognised is reported rather than
ignored, and the tests fail loudly the next time this structure changes.
"""

from __future__ import annotations

from typing import Any


class UnknownRouteShape(Exception):
    """A node in the route tree this walker does not understand."""


def all_paths(app_or_router: Any) -> set[str]:
    """Collect the paths of every route, however deeply nested.

    Args:
        app_or_router: An application or a router.

    Returns:
        Every path served.

    Raises:
        UnknownRouteShape: If a node has neither a path nor routes to follow —
            which means the framework has changed and this walker is now
            looking at less than it thinks.
    """
    found: set[str] = set()
    seen: set[int] = set()
    unknown: list[str] = []

    def children(node: Any) -> list[Any]:
        for attribute in ("routes", "original_router", "router", "app"):
            child = getattr(node, attribute, None)
            if child is None or child is node:
                continue
            if isinstance(child, (list, tuple)):
                return list(child)
            if hasattr(child, "routes") or hasattr(child, "path"):
                return [child]
        return []

    def walk(node: Any) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))

        path = getattr(node, "path", None)
        kids = children(node)
        if isinstance(path, str):
            found.add(path)
        elif not kids:
            unknown.append(type(node).__name__)

        for child in kids:
            walk(child)

    walk(app_or_router)
    if unknown:
        raise UnknownRouteShape(
            "route tree holds nodes this walker cannot read, so it is checking "
            f"less than it appears to: {sorted(set(unknown))}"
        )
    return found
