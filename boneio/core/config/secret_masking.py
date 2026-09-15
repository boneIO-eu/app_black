"""Keep configured secrets out of API responses (F-03).

``GET /api/config`` returned the MQTT password, and any other password in the
configuration, in clear text. Masking it is only half the job: the settings
forms are populated from that same response and post the whole section back, so
a mask that is written straight through would overwrite the real password with
its own placeholder the first time anyone saved an unrelated field.

So the two halves belong together and live here: :func:`mask_secrets` replaces
secret values on the way out, and :func:`restore_secrets` puts the stored value
back whenever the client returns the placeholder untouched.

The placeholder is deliberately unmistakable rather than pretty. A row of dots
looks better, but it is something a person could plausibly type as a password,
and then their real choice would be silently discarded in favour of the old
one. Being ugly in a password field costs nothing — the browser renders it as
dots anyway.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

#: Returned in place of a configured secret, and understood on the way back in.
MASK = "__boneio_masked_secret__"

#: Key names whose values are secrets. Matched case-insensitively against the
#: whole key, so a field called "password_help" or "token_count" is left alone.
#:
#: The config schema only actually uses "password" today — for MQTT, for remote
#: ESPHome and WLED devices, and for the legacy web.auth block. The rest are
#: here so that a secret added later is masked by default rather than after
#: someone notices it in a response.
SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "privatekey",
    }
)


def is_secret_key(key: Any) -> bool:
    """Whether a mapping key names a secret.

    Args:
        key: Key from the configuration mapping.

    Returns:
        True if the value under this key must not leave the device.
    """
    return isinstance(key, str) and key.strip().lower() in SECRET_KEYS


def _walk_mask(value: Any) -> Any:
    """Recursively copy a structure, replacing secret values with the mask.

    Args:
        value: Configuration fragment.

    Returns:
        A masked copy. The input is never modified.
    """
    if isinstance(value, dict):
        masked: dict[Any, Any] = {}
        for key, item in value.items():
            if is_secret_key(key) and isinstance(item, str) and item:
                masked[key] = MASK
            else:
                masked[key] = _walk_mask(item)
        return masked

    if isinstance(value, list):
        return [_walk_mask(item) for item in value]

    return value


def mask_secrets(config: Any) -> Any:
    """Return a copy of the configuration with secrets replaced by the mask.

    Works on a copy on purpose: the parsed configuration is held in a
    process-wide cache, and masking it in place would lose the real values for
    everything else running in this process.

    An empty value is left as it is — masking "" would tell the client a secret
    is set when none is.

    Args:
        config: Parsed configuration, or any fragment of one.

    Returns:
        Masked copy.
    """
    return _walk_mask(deepcopy(config))


def restore_secrets(incoming: Any, stored: Any) -> Any:
    """Put stored secrets back wherever the client returned the mask.

    Anything else the client sends is taken at face value, including a genuinely
    new password and an explicit empty string, which is how a secret gets
    cleared.

    Args:
        incoming: Fragment as submitted by the client.
        stored: The corresponding fragment as currently configured.

    Returns:
        The incoming fragment with masked secrets resolved. The inputs are
        never modified.
    """
    if isinstance(incoming, dict):
        resolved: dict[Any, Any] = {}
        stored_map = stored if isinstance(stored, dict) else {}
        for key, item in incoming.items():
            if is_secret_key(key) and item == MASK:
                previous = stored_map.get(key)
                # If nothing is stored, drop the key rather than writing the
                # placeholder into config.yaml.
                if isinstance(previous, str) and previous:
                    resolved[key] = previous
                continue
            resolved[key] = restore_secrets(item, stored_map.get(key))
        return resolved

    if isinstance(incoming, list):
        stored_list = stored if isinstance(stored, list) else []
        return [
            restore_secrets(
                item, stored_list[index] if index < len(stored_list) else None
            )
            for index, item in enumerate(incoming)
        ]

    return incoming


def collect_secrets(config: Any) -> set[str]:
    """Every secret value configured on this device.

    Used to scrub them out of log output, where they arrive as free text rather
    than as structured fields.

    Args:
        config: Parsed configuration.

    Returns:
        The set of non-empty secret values.
    """
    found: set[str] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if is_secret_key(key) and isinstance(item, str) and item:
                    found.add(item)
                else:
                    _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(config)
    return found


def scrub_text(text: str, secrets: set[str]) -> str:
    """Replace configured secret values wherever they appear in free text.

    Log lines are not structured, so there is no key to match on — but the
    values themselves are known, which is enough. Longest first, so a secret
    that contains another one is not left half-replaced.

    Args:
        text: Text to clean, typically one log line.
        secrets: Values to remove, from :func:`collect_secrets`.

    Returns:
        The text with every occurrence replaced by the mask.
    """
    if not text or not secrets:
        return text

    cleaned = text
    for secret in sorted(secrets, key=len, reverse=True):
        # Very short secrets are skipped: replacing a two-character value would
        # mangle unrelated words and make the log unreadable without protecting
        # anything worth protecting.
        if len(secret) < 4:
            continue
        cleaned = cleaned.replace(secret, MASK)
    return cleaned
