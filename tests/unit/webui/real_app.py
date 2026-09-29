"""The application init_app builds, for tests that go through all of it.

init_app configures one module-level application rather than returning a new
one, and Starlette refuses to add middleware to an application that has
already served a request. So a second test that builds it after a first one
used it would fail on that, not on anything it tests. This hands the app out
and puts it back in a state init_app can configure again.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.app import init_app


@contextlib.contextmanager
def real_app_client(
    tmp_path: Path, secret: str, accounts: dict[str, str]
) -> Iterator[TestClient]:
    """A client for the fully assembled application, on a provisioned store.

    Args:
        tmp_path: Directory for config.yaml and users.json.
        secret: JWT secret the application signs with.
        accounts: Admin accounts to create, as username → password.

    Yields:
        A TestClient for the application.
    """
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8090\n", encoding="utf-8")
    seeded = UserStore(tmp_path / USERS_FILENAME)
    seeded.load()
    for username, password in accounts.items():
        seeded.add_user(username, password, Role.ADMIN)

    app = init_app(
        manager=MagicMock(),
        yaml_config_file=str(config),
        config_helper=MagicMock(),
        auth_config={},
        jwt_secret=secret,
    )
    try:
        yield TestClient(app)
    finally:
        # Built lazily on the first request; clearing it lets the next
        # init_app add its middleware again.
        app.middleware_stack = None
