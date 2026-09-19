"""Which library signs the panel's tokens.

python-jose brought ecdsa, rsa, pyasn1 and six along for algorithms this panel
does not use — it signs one kind of token, HS256 with a secret it holds. ecdsa
carries an advisory with no fixed version and no prospect of one, so as a
dependency it could only be carried, never resolved.

These are cheap guards against it coming back by way of an import somebody
copies from an older file or an answer on the internet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _python_sources():
    for path in (REPO_ROOT / "boneio").rglob("*.py"):
        yield path, path.read_text(encoding="utf-8")


def test_nothing_imports_python_jose():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path, text in _python_sources()
        if re.search(r"^\s*(from jose|import jose)\b", text, re.M)
    ]
    assert not offenders, f"python-jose is back in: {offenders}"


def test_it_is_not_a_declared_dependency():
    """Looks at the requirement lines, not the comments.

    The comment above the replacement names it on purpose, so that anybody
    tempted to put it back reads why it went.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith('"') and not line.strip().startswith("#")
    ]
    offenders = [r for r in requirements if "python-jose" in r]
    assert not offenders, f"python-jose is a dependency again: {offenders}"


def test_the_unfixable_dependency_is_not_in_the_lock():
    """ecdsa's advisory has no fixed version. It came in through python-jose
    and nothing else here wants it."""
    lock = REPO_ROOT / "uv.lock"
    if not lock.exists():  # pragma: no cover - the lock is committed
        pytest.skip("no lockfile")
    assert 'name = "ecdsa"' not in lock.read_text(encoding="utf-8")


def test_tokens_still_round_trip():
    """The swap is only safe if the claims survive it."""
    from datetime import UTC, datetime, timedelta

    from boneio.webui.middleware.auth import JWT_ALGORITHM, create_token, set_jwt_secret, verify_token

    set_jwt_secret("a-secret-long-enough-not-to-warn-about-0123456789")
    token = create_token({"sub": "pawel", "role": "admin"})
    payload = verify_token(token)

    assert payload is not None
    assert payload["sub"] == "pawel"
    assert payload["role"] == "admin"
    assert JWT_ALGORITHM == "HS256"


def test_a_token_signed_with_another_secret_is_rejected():
    from boneio.webui.middleware.auth import create_token, set_jwt_secret, verify_token

    set_jwt_secret("the-first-secret-long-enough-0123456789012")
    token = create_token({"sub": "pawel", "role": "admin"})

    set_jwt_secret("a-different-secret-long-enough-0123456789")
    assert verify_token(token) is None


def test_an_expired_token_is_rejected():
    from datetime import UTC, datetime, timedelta

    import jwt

    from boneio.webui.middleware.auth import JWT_ALGORITHM, set_jwt_secret, verify_token

    secret = "a-secret-long-enough-not-to-warn-about-0123456789"
    set_jwt_secret(secret)
    stale = jwt.encode(
        {"sub": "pawel", "role": "admin", "exp": datetime.now(UTC) - timedelta(days=1)},
        secret,
        algorithm=JWT_ALGORITHM,
    )
    assert verify_token(stale) is None


def test_rubbish_is_rejected_rather_than_raised():
    from boneio.webui.middleware.auth import set_jwt_secret, verify_token

    set_jwt_secret("a-secret-long-enough-not-to-warn-about-0123456789")
    assert verify_token("not-a-token") is None
    assert verify_token("") is None
