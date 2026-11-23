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
    """Sections with a field holding a secret anywhere in them.

    Read from the panel's schema, which the section models generate, so the
    models are not built for it.
    """
    import json
    from pathlib import Path

    from boneio.core.config.secret_masking import SECRET_KEYS

    keys = SECRET_KEYS | AGENT_SECRET_KEYS
    document = json.loads((Path(__file__).parents[2] / "webui" / "schema" / "config.schema.json").read_text())
    defs = document.get("$defs", {})

    def holds_secret(node: object, seen: frozenset = frozenset()) -> bool:
        if isinstance(node, list):
            return any(holds_secret(n, seen) for n in node)
        if not isinstance(node, dict):
            return False
        ref = node.get("$ref", "").removeprefix("#/$defs/")
        if ref:
            return ref not in seen and holds_secret(defs[ref], seen | {ref})
        properties = node.get("properties", {})
        return any(k.lower() in keys for k in properties) or any(
            holds_secret(node.get(k), seen) for k in ("items", "additionalProperties", "oneOf")
        ) or any(holds_secret(v, seen) for v in properties.values())

    return frozenset(name for name, rule in document["properties"].items() if holds_secret(rule))
