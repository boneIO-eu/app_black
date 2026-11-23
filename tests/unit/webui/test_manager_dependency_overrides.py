"""Every route that depends on a router's placeholder get_manager gets the real one.

Routers declare a get_manager() that raises NotImplementedError and app.py
swaps it for the real one through dependency_overrides. A router missing from
that list answers every such route with a bare 500, as /api/can/nodes did.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

import boneio.webui.routes as routes_pkg
from boneio.webui.app import app


def _dependency_calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependency_calls(dep)


def test_every_placeholder_get_manager_is_overridden():
    # Walks the routers rather than app.routes: newer FastAPI keeps included
    # routers as lazy wrappers there. The dev-only router is overridden only
    # under BONEIO_DEV, together with being included.
    routers = [
        getattr(routes_pkg, name)
        for name in routes_pkg.__all__
        if name.endswith("_router") and name != "dev_fake_device_router"
    ]
    missing = set()
    for router in routers:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            for call in _dependency_calls(route.dependant):
                if (
                    getattr(call, "__name__", "") in ("get_manager", "_get_manager")
                    and call.__module__.startswith("boneio.webui.routes.")
                    and call not in app.dependency_overrides
                ):
                    missing.add(f"{call.__module__} ({route.path})")
    assert not missing, sorted(missing)
