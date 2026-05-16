"""Public API for the expander module.

Core boneIO files MUST import only from this module — never reach into
``yaml_util`` or ``routes`` internals directly. This is the stable contract;
internal restructuring of the module never breaks consumers.

Note on lazy loading: ``register_routes`` is imported lazily via
``__getattr__`` because it pulls in FastAPI. Pure helpers (``is_expander_output``,
``split_outputs_for_includes``, ``dedup_outputs_prefer_named``,
``filter_out_expander``, ``EXPANDER_PREFIX``) load eagerly with no heavy deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from boneio.modules.expander.yaml_util import (
    EXPANDER_PREFIX,
    dedup_outputs_prefer_named,
    filter_out_expander,
    is_expander_output,
    split_outputs_for_includes,
)

if TYPE_CHECKING:
    from boneio.modules.expander.routes import register_routes  # noqa: F401

__all__ = [
    "EXPANDER_PREFIX",
    "dedup_outputs_prefer_named",
    "filter_out_expander",
    "is_expander_output",
    "register_routes",
    "split_outputs_for_includes",
]


def __getattr__(name: str) -> Any:
    """Lazy load ``register_routes`` to keep FastAPI off the import path for pure helpers."""
    if name == "register_routes":
        from boneio.modules.expander.routes import register_routes
        return register_routes
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
