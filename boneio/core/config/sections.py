"""Facts about config sections that more than one part of boneIO needs."""

from __future__ import annotations

from functools import cache

#: Sections the running application reads only when it starts: saving one
#: takes effect after a restart, not a reload.
RESTART_REQUIRED_SECTIONS = frozenset({
    "boneio", "mqtt", "lox_udp", "web", "modbus",
    "mcp23017", "lm75", "ina219", "ina226", "mcp9808", "can",
})

#: Keys whose values only an administrator reads, beyond those the panel
#: masks for everyone (secret_masking.SECRET_KEYS): an ESPHome device's
#: encryption key, and alarm codes - digits, or a hash of a short PIN that
#: falls to a brute force in seconds. A read-only account and an API key get
#: the mask; what an agent reads ends up with its model's vendor.
AGENT_SECRET_KEYS = frozenset({"encryption_key", "code"})


#: Sections an API key may propose but never save: collecting how the house
#: is used is a person's decision, not an agent's.
PERSON_ONLY_SECTIONS = frozenset({"usage_history"})


@cache
def secret_sections() -> frozenset[str]:
    """Sections whose schema has a field holding a secret, anywhere in it."""
    from boneio.core.config.secret_masking import SECRET_KEYS
    from boneio.core.config.yaml_util import _get_schema

    keys = SECRET_KEYS | AGENT_SECRET_KEYS

    def holds_secret(rule: object) -> bool:
        if not isinstance(rule, dict):
            return False
        schema = rule.get("schema")
        if isinstance(schema, dict):
            if isinstance(schema.get("type"), str):  # list item rule
                return holds_secret(schema)
            return any(k.lower() in keys or holds_secret(v) for k, v in schema.items())
        return False

    return frozenset(name for name, rule in _get_schema().items() if holds_secret(rule))
