"""Password hashing for boneIO web accounts.

Uses scrypt from the standard library, so no new dependency is pulled onto the
BeagleBone. Parameters live inside the encoded string, which means the cost can
be raised in a later release without invalidating existing accounts: verify
still reads the old parameters, and :func:`needs_rehash` tells the caller the
stored hash is below the current policy so it can be upgraded on next login.

The encoding is PHC-inspired and self-describing::

    $scrypt$n=16384,r=8,p=1$<salt-b64>$<hash-b64>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# Cost parameters. n=2**14 with r=8 needs 128 * n * r = 16 MiB of memory per
# hash. Measured at ~0.9 s per hash on a BeagleBone Black (armv7l) — slow enough
# to hurt an offline cracker, and only paid at login: a successful login issues
# a JWT good for weeks (see TOKEN_TTL_DAYS), so the cost is not on the hot path.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32

_PREFIX = "$scrypt$"


def _b64(raw: bytes) -> str:
    """Encode without padding, so the '=' never collides with the k=v syntax."""
    return base64.b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    """Decode a padding-stripped base64 string."""
    return base64.b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt.

    Args:
        password: Plain-text password.

    Returns:
        Self-describing encoded hash, safe to store as-is.

    Raises:
        ValueError: If the password is empty.
    """
    if not password:
        raise ValueError("Password must not be empty")

    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_BYTES,
        maxmem=_maxmem(_SCRYPT_N, _SCRYPT_R, _SCRYPT_P),
    )
    params = f"n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}"
    return f"{_PREFIX}{params}${_b64(salt)}${_b64(derived)}"


def _maxmem(n: int, r: int, p: int) -> int:
    """Memory ceiling for :func:`hashlib.scrypt`.

    OpenSSL defaults to a 32 MiB ceiling and refuses anything above it, so the
    limit is computed from the parameters instead of hardcoded — otherwise
    raising the cost in a later release would fail at runtime rather than in a
    test. The formula is scrypt's own footprint plus headroom for the internal
    buffers.

    Args:
        n: CPU/memory cost.
        r: Block size.
        p: Parallelisation.

    Returns:
        Byte ceiling to hand to :func:`hashlib.scrypt`.
    """
    return 128 * n * r + 128 * r * p + (1 << 20)


def _parse(encoded: str) -> tuple[dict[str, int], bytes, bytes]:
    """Split an encoded hash into its parameters, salt and digest.

    Args:
        encoded: String produced by :func:`hash_password`.

    Returns:
        Tuple of (parameters, salt, digest).

    Raises:
        ValueError: If the string is not a well-formed scrypt hash.
    """
    if not encoded.startswith(_PREFIX):
        raise ValueError("Unsupported password hash format")

    try:
        _, algo, params_text, salt_text, hash_text = encoded.split("$")
    except ValueError as err:
        raise ValueError("Malformed password hash") from err

    if algo != "scrypt":
        raise ValueError(f"Unsupported password hash algorithm: {algo}")

    params: dict[str, int] = {}
    for item in params_text.split(","):
        key, _, value = item.partition("=")
        try:
            params[key] = int(value)
        except ValueError as err:
            raise ValueError(f"Malformed hash parameter: {item}") from err

    if not {"n", "r", "p"} <= params.keys():
        raise ValueError("Password hash is missing scrypt parameters")

    return params, _unb64(salt_text), _unb64(hash_text)


def verify_password(password: str, encoded: str) -> bool:
    """Check a password against a stored hash in constant time.

    A malformed or unreadable stored hash is treated as a failed verification
    rather than an error: a corrupted ``users.json`` entry must lock that
    account out, not crash the login route for everyone.

    Args:
        password: Plain-text password supplied by the client.
        encoded: Stored hash to check against.

    Returns:
        True if the password matches.
    """
    if not password or not encoded:
        return False

    try:
        params, salt, expected = _parse(encoded)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=params["n"],
            r=params["r"],
            p=params["p"],
            dklen=len(expected),
            maxmem=_maxmem(params["n"], params["r"], params["p"]),
        )
    except (ValueError, KeyError, TypeError):
        return False

    return hmac.compare_digest(derived, expected)


def needs_rehash(encoded: str) -> bool:
    """Report whether a stored hash is weaker than the current policy.

    Args:
        encoded: Stored hash.

    Returns:
        True if the hash should be replaced next time the password is known.
    """
    try:
        params, _, _ = _parse(encoded)
    except ValueError:
        return True

    return (
        params["n"] < _SCRYPT_N
        or params["r"] < _SCRYPT_R
        or params["p"] < _SCRYPT_P
    )
