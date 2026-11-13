"""Heat pump schemes: map role values to HA climate/water_heater semantics.

Pure logic, no I/O. ``v`` maps role -> entity value as the entity publishes it:
switch-like roles (``power``, ``dhw_enable``) are "ON"/"OFF", numeric roles are
numbers, binary-sensor roles are payload strings. A missing role or ``None`` is
unknown: it never counts as "off"/"on" and numeric outputs become ``None``.
Writes are returned in the order they must be executed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

HvacMode = Literal["off", "heat", "cool", "auto"]
DhwMode = Literal["off", "heat_pump"]


@dataclass(frozen=True)
class Write:
    role: str
    value: float | int | str


class HeatPumpScheme(Protocol):
    modes: list[HvacMode]

    def hvac_mode(self, v: Mapping[str, Any]) -> HvacMode | None: ...
    def hvac_action(self, v: Mapping[str, Any]) -> str: ...
    def target(self, v: Mapping[str, Any]) -> float | None: ...
    def target_role(self, v: Mapping[str, Any]) -> str: ...
    def current(self, v: Mapping[str, Any]) -> float | None: ...
    def dhw_mode(self, v: Mapping[str, Any]) -> DhwMode: ...
    def set_hvac_mode(self, v: Mapping[str, Any], mode: HvacMode) -> list[Write]: ...
    def set_dhw_mode(self, v: Mapping[str, Any], mode: DhwMode) -> list[Write]: ...


def _on(x: Any) -> bool:
    return x is True or str(x).strip().upper() in ("1", "ON", "TRUE")


def _power_off(v: Mapping[str, Any]) -> bool:
    return str(v.get("power")).upper() == "OFF"


def _int(x: Any) -> int | None:
    try:
        return None if x is None else int(x)
    except (TypeError, ValueError):
        return None


def _num(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


class LgTherma:
    """LG Therma V: mode 0 cool / 3 auto / 4 heat, power and DHW are coils."""

    modes: list[HvacMode] = ["off", "heat", "cool", "auto"]
    _MODE: dict[HvacMode, int] = {"heat": 4, "cool": 0, "auto": 3}
    _CURRENT_ROLE = {0: "supply", 1: "return", 2: "room"}

    def hvac_mode(self, v):
        if _power_off(v):
            return "off"
        return {4: "heat", 0: "cool", 3: "auto"}.get(_int(v.get("mode")))

    def hvac_action(self, v):
        if _power_off(v):
            return "off"
        if _on(v.get("defrost")):
            return "defrosting"
        if _on(v.get("compressor")):
            return {1: "cooling", 2: "heating"}.get(_int(v.get("outdoor_cycle")), "idle")
        return "idle"

    def target_role(self, v):
        return "heating_target"

    def target(self, v):
        return _num(v.get("heating_target"))

    def current(self, v):
        role = self._CURRENT_ROLE.get(_int(v.get("control_method")))
        return _num(v.get(role)) if role else None

    def dhw_mode(self, v):
        return "heat_pump" if _on(v.get("dhw_enable")) else "off"

    def set_hvac_mode(self, v, mode):
        if mode == "off":
            return [Write("power", "OFF")]
        return [Write("mode", self._MODE[mode]), Write("power", "ON")]

    def set_dhw_mode(self, v, mode):
        return [Write("dhw_enable", "ON" if mode == "heat_pump" else "OFF")]


class Phnix:
    """Phnix (Kaisai): one mode register mixes DHW and circuit.

    Mode: 0 DHW, 1 heat, 2 cool, 3 DHW+heat, 4 DHW+cool. Writes keep the part
    the caller did not ask to change.
    """

    modes: list[HvacMode] = ["off", "heat", "cool"]
    _DHW = (0, 3, 4)

    def _live_mode(self, v):
        # the mode register is stale while power is off: nothing is active
        return None if _power_off(v) else _int(v.get("mode"))

    def hvac_mode(self, v):
        if _power_off(v):
            return "off"
        # mode 0 is DHW only: the circuit is off
        return {0: "off", 1: "heat", 3: "heat", 2: "cool", 4: "cool"}.get(_int(v.get("mode")))

    def hvac_action(self, v):
        # operating_state: 0 cooling, 1 heating, 2 defrost, 3 disinfection, 4 hot water.
        # Disinfection and hot water serve the DHW tank, so the circuit is idle.
        # Cooling/heating need the compressor, unless it is unknown (trust the state).
        if _power_off(v):
            return "off"
        state = _int(v.get("operating_state"))
        if state == 2:
            return "defrosting"
        compressor = v.get("compressor")
        if state in (0, 1) and (compressor is None or _on(compressor)):
            return "cooling" if state == 0 else "heating"
        return "idle"

    def target_role(self, v):
        return "cooling_target" if self._live_mode(v) in (2, 4) else "heating_target"

    def target(self, v):
        return _num(v.get(self.target_role(v)))

    def current(self, v):
        return _num(v.get("supply"))

    def dhw_mode(self, v):
        if _power_off(v):
            return "off"
        return "heat_pump" if _int(v.get("mode")) in self._DHW else "off"

    def _with_power(self, v, writes):
        return writes + ([] if str(v.get("power")).upper() == "ON" else [Write("power", "ON")])

    def set_hvac_mode(self, v, mode):
        dhw = self._live_mode(v) in self._DHW
        if mode == "off":
            return [Write("mode", 0)] if dhw else [Write("power", "OFF")]
        if mode == "heat":
            return self._with_power(v, [Write("mode", 3 if dhw else 1)])
        if mode == "cool":
            return self._with_power(v, [Write("mode", 4 if dhw else 2)])
        raise ValueError(f"Phnix does not support mode {mode!r}")

    def set_dhw_mode(self, v, mode):
        m = self._live_mode(v)
        if mode == "heat_pump":
            new = {1: 3, 2: 4}.get(m, m if m in self._DHW else 0)
            return self._with_power(v, [Write("mode", new)] if new != m else [])
        if m in (3, 4):
            return [Write("mode", m - 2)]
        return [Write("power", "OFF")] if m == 0 else []


SCHEMES: dict[str, HeatPumpScheme] = {"lg_therma": LgTherma(), "phnix": Phnix()}


def state(scheme: HeatPumpScheme, v: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": scheme.hvac_mode(v),
        "action": scheme.hvac_action(v),
        "current_temperature": scheme.current(v),
        "target_temperature": scheme.target(v),
        "dhw_mode": scheme.dhw_mode(v),
        "dhw_current": _num(v.get("dhw_current")),
        "dhw_target": _num(v.get("dhw_target")),
    }
