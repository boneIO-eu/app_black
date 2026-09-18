"""The frontend only knows what /api/init tells it.

This exists because of a bug that survived two releases and looked, from the
Python side, entirely correct. ``configured_before`` was computed at startup,
returned by ``/api/onboarding/status``, and read by the first-run wizard from
the ``/api/init`` payload — which never carried it. Every test passed. The
value was right. The wizard saw ``undefined``, fell back to ``false``, and
offered to replace the input bindings of every device that had any.

Nothing in either language could catch that on its own, so this checks the
seam: what the wizard reads against what the endpoint returns.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SYSTEM_ROUTE = REPO_ROOT / "boneio" / "webui" / "routes" / "system.py"
FRONTEND = REPO_ROOT / "frontend" / "src"

#: Components that render from the /api/init payload.
READERS = (
    FRONTEND / "components" / "OnboardingWizard.tsx",
    FRONTEND / "contexts" / "AppInitContext.tsx",
)

#: `initData?.foo`, `initData.foo`, `data?.foo` — how the payload is read.
_READ = re.compile(r"\binit[Dd]ata\s*[?]?\.\s*([A-Za-z_][A-Za-z0-9_]*)")


def _init_payload_keys() -> set[str]:
    """The literal keys ``get_init`` returns.

    Returns:
        Key names from the endpoint's return dict.
    """
    tree = ast.parse(SYSTEM_ROUTE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "get_init":
            continue
        for statement in ast.walk(node):
            if isinstance(statement, ast.Return) and isinstance(
                statement.value, ast.Dict
            ):
                return {
                    key.value
                    for key in statement.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
    raise AssertionError("get_init has no literal return dict any more")


def _keys_read_by(path: Path) -> set[str]:
    """Fields a component reads off the init payload.

    Args:
        path: The component.

    Returns:
        Field names.
    """
    return set(_READ.findall(path.read_text(encoding="utf-8")))


def test_the_endpoint_still_returns_a_literal_dict():
    """If this fails the rest of the file is checking nothing."""
    assert len(_init_payload_keys()) > 5


def test_configured_before_reaches_the_wizard():
    """The specific regression.

    Without it the wizard shows the import and device steps on every device,
    including the ones whose event section it would replace.
    """
    assert "configured_before" in _init_payload_keys()


@pytest.mark.parametrize("reader", READERS, ids=lambda p: p.name)
def test_every_field_read_is_a_field_returned(reader):
    """A field the frontend reads and the endpoint does not send is not a type
    error in either language — it is ``undefined``, and it usually means the
    safe-looking default rather than a visible failure."""
    # Fields merged in conditionally rather than listed in the return dict.
    conditional = {"serial_no", "serial_override"}
    returned = _init_payload_keys() | conditional

    missing = _keys_read_by(reader) - returned
    assert not missing, (
        f"{reader.name} reads {sorted(missing)} from the init payload, "
        f"which GET /api/init does not return"
    )
