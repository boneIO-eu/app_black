"""Shared fixtures for the WebUI route tests."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _fresh_system_state():
    """Start and end every test with the security module's system reads unknown.

    The SSH login and OS update states are cached per process, so one test's
    answer would otherwise be the next one's.
    """

    def forget() -> None:
        security = sys.modules.get("boneio.webui.routes.security")
        if security is not None:
            security._service_password.forget()
            security._os_update.forget()

    forget()
    yield
    forget()
