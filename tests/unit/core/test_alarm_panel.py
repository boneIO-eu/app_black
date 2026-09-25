"""Unit tests for BoneIOAlarmPanel — the zone-based alarm state machine.

Unlike most suites here, these tests drive the **real** class rather than a
stub reimplementation.  ``boneio.components.template.alarm_panel`` imports only
``boneio.const`` at module scope — the GPIO layer is imported lazily inside
``_check_zones_clear`` — so there is no hardware dependency to work around and
no reason to test a copy of the logic.

Timers are exercised with sub-second durations instead of being faked, so the
real ``loop.call_later`` paths run.

A group of tests at the end pins down behaviour that is deliberately weak
today (unsalted hashes, ``TRIGGER`` without a code, no codes = no protection).  They assert
what the code *does*, not what it *should* do, and are marked as such — when
that hardening lands they are expected to fail and be rewritten.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from boneio.components.template.alarm_panel import (
    ARMED_AWAY,
    ARMED_HOME,
    ARMED_NIGHT,
    ARMING,
    CODE_INVALID,
    CODE_LOCKED,
    CODE_LOCKOUT_BASE_S,
    CODE_LOCKOUT_MAX_S,
    CODE_MAX_FAILURES,
    CODE_MISSING,
    CODE_OK,
    DISARMED,
    NORMALLY_CLOSED,
    NORMALLY_OPEN,
    PENDING,
    TRIGGERED,
    AlarmOutput,
    AlarmPinCode,
    AlarmZone,
    BoneIOAlarmPanel,
    ZoneInput,
)

PIN_OK = "1234"
PIN_BAD = "9999"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def make_output(output_id: str = "siren_1", output_type: str = "siren") -> AlarmOutput:
    """An AlarmOutput whose relay records turn_on/turn_off calls."""
    relay = MagicMock()
    relay.id = output_id
    relay.async_turn_on = AsyncMock()
    relay.async_turn_off = AsyncMock()
    return AlarmOutput(output=relay, output_type=output_type)


def make_panel(
    *,
    zones: list[AlarmZone] | None = None,
    outputs: list[AlarmOutput] | None = None,
    codes: list[AlarmPinCode] | None = None,
    code_arm_required: bool = False,
    arming_time_s: float = 0.0,
    delay_time_s: float = 0.0,
    trigger_time_s: float = 0.0,
    input_manager=None,
    state_manager=None,
) -> BoneIOAlarmPanel:
    """A panel wired to mocks.

    ``input_manager`` defaults to None, which makes ``_check_zones_clear``
    return early — arming is then never blocked and the GPIO layer is never
    touched.  Tests that care about blocking pass one explicitly.
    """
    return BoneIOAlarmPanel(
        id="alarm_test",
        name="Alarm testowy",
        message_bus=MagicMock(),
        event_bus=MagicMock(),
        topic_prefix="boneio",
        zones=zones if zones is not None else [],
        outputs=outputs if outputs is not None else [],
        input_manager=input_manager,
        codes=codes,
        code_arm_required=code_arm_required,
        arming_time_s=arming_time_s,
        delay_time_s=delay_time_s,
        trigger_time_s=trigger_time_s,
        state_manager=state_manager,
    )


def sent_payloads(panel: BoneIOAlarmPanel, topic_suffix: str) -> list:
    """Every payload published to a topic ending with ``topic_suffix``."""
    return [
        call.kwargs["payload"]
        for call in panel._message_bus.send_message.call_args_list
        if call.kwargs.get("topic", "").endswith(topic_suffix)
    ]


# ---------------------------------------------------------------------------
# ZoneInput — wiring polarity
# ---------------------------------------------------------------------------


class TestZoneInput:
    """NC and NO invert each other; getting this wrong arms a dead alarm."""

    @pytest.mark.parametrize(
        ("wiring", "gpio_state", "expected"),
        [
            # NC: closed circuit (True) is safe, open circuit (False) is alarm
            (NORMALLY_CLOSED, True, False),
            (NORMALLY_CLOSED, False, True),
            # NO: open circuit (False) is safe, closed circuit (True) is alarm
            (NORMALLY_OPEN, False, False),
            (NORMALLY_OPEN, True, True),
        ],
    )
    def test_is_triggered_respects_wiring(self, wiring, gpio_state, expected):
        assert ZoneInput("in_01", wiring=wiring).is_triggered(gpio_state) is expected

    def test_defaults_to_normally_closed_local(self):
        zi = ZoneInput("in_01")
        assert zi.wiring == NORMALLY_CLOSED
        assert zi.source == "local"
        assert zi.on_disconnect == "ignore"
        assert zi.is_remote is False

    def test_remote_source_flag(self):
        assert ZoneInput("in_01", source="remote").is_remote is True


# ---------------------------------------------------------------------------
# AlarmZone
# ---------------------------------------------------------------------------


class TestAlarmZone:
    def test_get_zone_input_by_id(self):
        a, b = ZoneInput("in_01"), ZoneInput("in_02")
        zone = AlarmZone(name="Parter", inputs=[a, b], arm_modes=[ARMED_AWAY])
        assert zone.get_zone_input("in_02") is b
        assert zone.get_zone_input("in_99") is None

    def test_input_ids_mirror_inputs(self):
        zone = AlarmZone(
            name="Parter",
            inputs=[ZoneInput("in_01"), ZoneInput("in_02")],
            arm_modes=[ARMED_AWAY],
        )
        assert zone.input_ids == ["in_01", "in_02"]

    def test_is_active_only_in_listed_modes(self):
        zone = AlarmZone(
            name="Noc",
            inputs=[],
            arm_modes=[ARMED_AWAY, ARMED_NIGHT],
        )
        assert zone.is_active_in_mode(ARMED_AWAY) is True
        assert zone.is_active_in_mode(ARMED_NIGHT) is True
        assert zone.is_active_in_mode(ARMED_HOME) is False
        assert zone.is_active_in_mode(DISARMED) is False


# ---------------------------------------------------------------------------
# AlarmPinCode
# ---------------------------------------------------------------------------


class TestAlarmPinCode:
    def test_plaintext_pin_is_hashed(self):
        code = AlarmPinCode("Paweł", PIN_OK)
        assert code.code_hash == hashlib.sha256(PIN_OK.encode()).hexdigest()
        assert code.code_hash != PIN_OK

    def test_precomputed_hash_is_kept_verbatim(self):
        digest = hashlib.sha256(PIN_OK.encode()).hexdigest()
        assert AlarmPinCode("Paweł", digest).code_hash == digest

    def test_uppercase_hash_is_recognised_as_a_hash(self):
        digest = hashlib.sha256(PIN_OK.encode()).hexdigest().upper()
        code = AlarmPinCode("Paweł", digest)
        # Stored as given — _is_sha256 lowercases only for the check.
        assert code.code_hash == digest

    def test_verify(self):
        code = AlarmPinCode("Paweł", PIN_OK)
        assert code.verify(PIN_OK) is True
        assert code.verify(PIN_BAD) is False
        assert code.verify("") is False

    def test_64_char_non_hex_is_treated_as_plaintext(self):
        not_hex = "z" * 64
        code = AlarmPinCode("Paweł", not_hex)
        assert code.code_hash == hashlib.sha256(not_hex.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Arming and disarming
# ---------------------------------------------------------------------------


class TestArmDisarm:
    async def test_starts_disarmed(self):
        assert make_panel().state == DISARMED

    @pytest.mark.parametrize(
        ("command", "expected"),
        [("ARM_AWAY", ARMED_AWAY), ("ARM_HOME", ARMED_HOME), ("ARM_NIGHT", ARMED_NIGHT)],
    )
    async def test_arms_immediately_when_arming_time_is_zero(self, command, expected):
        panel = make_panel(arming_time_s=0)
        await panel.handle_command("", command)
        assert panel.state == expected

    async def test_arming_time_holds_state_in_arming_then_arms(self):
        panel = make_panel(arming_time_s=0.05)
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMING
        await asyncio.sleep(0.12)
        assert panel.state == ARMED_AWAY

    async def test_arming_remaining_is_none_outside_arming(self):
        panel = make_panel(arming_time_s=0)
        assert panel.arming_remaining_s is None
        await panel.handle_command("", "ARM_AWAY")
        assert panel.arming_remaining_s is None

    async def test_arming_remaining_counts_down(self):
        panel = make_panel(arming_time_s=5)
        await panel.handle_command("", "ARM_AWAY")
        remaining = panel.arming_remaining_s
        assert remaining is not None
        assert 0 < remaining <= 5

    async def test_disarm_from_armed(self):
        panel = make_panel(arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        await panel.handle_command("", "DISARM")
        assert panel.state == DISARMED

    async def test_disarm_during_arming_cancels_the_timer(self):
        """A cancelled arming timer must not arm the panel behind our back."""
        panel = make_panel(arming_time_s=0.05)
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMING
        await panel.handle_command("", "DISARM")
        await asyncio.sleep(0.12)
        assert panel.state == DISARMED

    async def test_lowercase_and_padded_commands_are_accepted(self):
        panel = make_panel(arming_time_s=0)
        await panel.handle_command("", "  arm_away  ")
        assert panel.state == ARMED_AWAY

    async def test_unknown_command_is_ignored(self):
        panel = make_panel()
        await panel.handle_command("", "SELF_DESTRUCT")
        assert panel.state == DISARMED


# ---------------------------------------------------------------------------
# Arming blocked by an open zone
# ---------------------------------------------------------------------------


class TestArmingBlocked:
    def _panel_with_open_input(self, *, wiring=NORMALLY_CLOSED, gpio_raw=True):
        """Panel whose single zone input reads as open (alarm) from GPIO."""
        inp = MagicMock()
        inp._pin = "P8_11"
        inp._inverted = False
        inp._name = "Drzwi wejściowe"
        input_manager = MagicMock()
        input_manager.get_all_inputs.return_value = {"in_01": inp}

        zone = AlarmZone(
            name="Wejście",
            inputs=[ZoneInput("in_01", wiring=wiring)],
            arm_modes=[ARMED_AWAY],
        )
        panel = make_panel(zones=[zone], input_manager=input_manager, arming_time_s=0)
        gpio_manager = MagicMock()
        gpio_manager.read_value.return_value = gpio_raw
        return panel, gpio_manager

    async def test_open_nc_input_blocks_arming(self):
        # raw=True, inverted=False → gpio_state = not True = False → NC triggers
        panel, gpio_manager = self._panel_with_open_input()
        with patch("boneio.hardware.gpio.input.get_gpio_manager", return_value=gpio_manager):
            await panel.handle_command("", "ARM_AWAY")
        assert panel.state == DISARMED

    async def test_blocking_inputs_are_published_as_attributes(self):
        panel, gpio_manager = self._panel_with_open_input()
        with patch("boneio.hardware.gpio.input.get_gpio_manager", return_value=gpio_manager):
            await panel.handle_command("", "ARM_AWAY")

        attrs = [json.loads(p) for p in sent_payloads(panel, "/attributes")]
        blocking = [a for a in attrs if a.get("blocking_inputs")]
        assert blocking, "brak listy blokujących wejść w atrybutach MQTT"
        entry = blocking[-1]["blocking_inputs"][0]
        assert entry["input_id"] == "in_01"
        assert entry["input_name"] == "Drzwi wejściowe"
        assert entry["zone"] == "Wejście"
        assert entry["wiring"] == NORMALLY_CLOSED

    async def test_closed_nc_input_does_not_block(self):
        # raw=False → gpio_state = not False = True → NC is safe
        panel, gpio_manager = self._panel_with_open_input(gpio_raw=False)
        with patch("boneio.hardware.gpio.input.get_gpio_manager", return_value=gpio_manager):
            await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMED_AWAY

    async def test_zone_inactive_in_target_mode_never_blocks(self):
        panel, gpio_manager = self._panel_with_open_input()
        with patch("boneio.hardware.gpio.input.get_gpio_manager", return_value=gpio_manager):
            # zone is armed_away only
            await panel.handle_command("", "ARM_HOME")
        assert panel.state == ARMED_HOME

    async def test_missing_remote_input_blocks_only_when_on_disconnect_is_trigger(self):
        input_manager = MagicMock()
        input_manager.get_all_inputs.return_value = {}
        zone = AlarmZone(
            name="Garaż",
            inputs=[ZoneInput("remote_01", source="remote", on_disconnect="trigger")],
            arm_modes=[ARMED_AWAY],
        )
        panel = make_panel(zones=[zone], input_manager=input_manager, arming_time_s=0)
        with patch("boneio.hardware.gpio.input.get_gpio_manager", return_value=MagicMock()):
            await panel.handle_command("", "ARM_AWAY")
        assert panel.state == DISARMED

    async def test_missing_remote_input_is_skipped_when_on_disconnect_is_ignore(self):
        input_manager = MagicMock()
        input_manager.get_all_inputs.return_value = {}
        zone = AlarmZone(
            name="Garaż",
            inputs=[ZoneInput("remote_01", source="remote", on_disconnect="ignore")],
            arm_modes=[ARMED_AWAY],
        )
        panel = make_panel(zones=[zone], input_manager=input_manager, arming_time_s=0)
        with patch("boneio.hardware.gpio.input.get_gpio_manager", return_value=MagicMock()):
            await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMED_AWAY


# ---------------------------------------------------------------------------
# Triggering
# ---------------------------------------------------------------------------


def _zone(name="Salon", input_id="in_05", wiring=NORMALLY_OPEN, modes=None, entry_delay=False):
    return AlarmZone(
        name=name,
        inputs=[ZoneInput(input_id, wiring=wiring)],
        arm_modes=modes or [ARMED_AWAY],
        entry_delay=entry_delay,
    )


class TestTrigger:
    async def test_input_event_is_ignored_while_disarmed(self):
        panel = make_panel(zones=[_zone()])
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0)
        assert panel.state == DISARMED

    async def test_zone_without_entry_delay_triggers_immediately(self):
        panel = make_panel(zones=[_zone()], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED

    async def test_zone_with_entry_delay_goes_pending_then_triggers(self):
        panel = make_panel(
            zones=[_zone(entry_delay=True)],
            arming_time_s=0,
            delay_time_s=0.05,
        )
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        assert panel.state == PENDING
        await asyncio.sleep(0.12)
        assert panel.state == TRIGGERED

    async def test_disarm_during_entry_delay_prevents_the_trigger(self):
        """The whole point of an entry delay — reaching the keypad in time."""
        panel = make_panel(
            zones=[_zone(entry_delay=True)],
            arming_time_s=0,
            delay_time_s=0.05,
        )
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        assert panel.state == PENDING
        await panel.handle_command("", "DISARM")
        await asyncio.sleep(0.12)
        assert panel.state == DISARMED

    async def test_zone_inactive_in_current_mode_does_not_trigger(self):
        panel = make_panel(zones=[_zone(modes=[ARMED_AWAY])], arming_time_s=0)
        await panel.handle_command("", "ARM_HOME")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == ARMED_HOME

    async def test_unknown_input_does_not_trigger(self):
        panel = make_panel(zones=[_zone()], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_nonexistent", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == ARMED_AWAY

    async def test_nc_zone_triggers_on_release_not_press(self):
        panel = make_panel(zones=[_zone(wiring=NORMALLY_CLOSED)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")  # circuit closed = safe
        await asyncio.sleep(0.02)
        assert panel.state == ARMED_AWAY
        panel.on_input_event("in_05", "released")  # circuit open = alarm
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED

    async def test_input_event_during_arming_is_ignored(self):
        """Exit delay: walking out past your own PIR must not fire the alarm."""
        panel = make_panel(zones=[_zone()], arming_time_s=0.05)
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMING
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == ARMING

    @pytest.mark.parametrize("transient", [ARMING, PENDING, TRIGGERED])
    async def test_transient_states_never_trigger_whatever_the_zone_says(
        self,
        transient,
    ):
        """The guard in on_input_event, isolated.

        With a normal config this is belt-and-braces: a zone lists only armed_*
        modes, so is_active_in_mode() already rejects a transient state.  The
        zone here deliberately claims the transient mode so that removing the
        guard is observable — without this, dropping it passes every other test
        in the file.
        """
        zone = AlarmZone(
            name="Dziwna",
            inputs=[ZoneInput("in_05", wiring=NORMALLY_OPEN)],
            arm_modes=[transient],
        )
        panel = make_panel(zones=[zone])
        panel._state = transient
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == transient

    async def test_triggered_records_zone_and_input_in_attributes(self):
        panel = make_panel(zones=[_zone()], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        attrs = [json.loads(p) for p in sent_payloads(panel, "/attributes")]
        assert attrs[-1]["triggered_zone"] == "Salon"
        assert attrs[-1]["triggered_input"] == "in_05"

    async def test_manual_trigger_command(self):
        panel = make_panel()
        await panel.handle_command("", "TRIGGER")
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class TestOutputs:
    async def test_trigger_activates_every_output(self):
        siren, light = make_output("siren_1"), make_output("light_1", "light")
        panel = make_panel(zones=[_zone()], outputs=[siren, light], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        siren.output.async_turn_on.assert_awaited_once()
        light.output.async_turn_on.assert_awaited_once()

    async def test_disarm_deactivates_outputs(self):
        siren = make_output()
        panel = make_panel(zones=[_zone()], outputs=[siren], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        await panel.handle_command("", "DISARM")
        siren.output.async_turn_off.assert_awaited()

    async def test_auto_disarm_after_trigger_time(self):
        siren = make_output()
        panel = make_panel(
            zones=[_zone()],
            outputs=[siren],
            arming_time_s=0,
            trigger_time_s=0.05,
        )
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED
        await asyncio.sleep(0.12)
        assert panel.state == DISARMED
        siren.output.async_turn_off.assert_awaited()

    async def test_a_failing_output_does_not_break_the_others(self):
        broken, good = make_output("broken"), make_output("good")
        broken.output.async_turn_on.side_effect = RuntimeError("relay stuck")
        panel = make_panel(zones=[_zone()], outputs=[broken, good], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED
        good.output.async_turn_on.assert_awaited_once()


# ---------------------------------------------------------------------------
# PIN codes
# ---------------------------------------------------------------------------


class TestCodes:
    async def test_disarm_requires_a_code_when_codes_are_configured(self):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        await panel.handle_command("", "DISARM")  # no code
        assert panel.state == ARMED_AWAY

    async def test_disarm_with_correct_code(self):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        await panel.handle_command(
            "",
            json.dumps({"action": "DISARM", "code": PIN_OK}),
        )
        assert panel.state == DISARMED

    async def test_disarm_with_wrong_code_is_refused(self):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        await panel.handle_command(
            "",
            json.dumps({"action": "DISARM", "code": PIN_BAD}),
        )
        assert panel.state == ARMED_AWAY

    async def test_any_configured_code_works(self):
        panel = make_panel(
            codes=[AlarmPinCode("Paweł", PIN_OK), AlarmPinCode("Ala", "4321")],
            arming_time_s=0,
        )
        await panel.handle_command("", "ARM_AWAY")
        await panel.handle_command("", json.dumps({"action": "DISARM", "code": "4321"}))
        assert panel.state == DISARMED

    async def test_arming_ignores_code_unless_code_arm_required(self):
        panel = make_panel(
            codes=[AlarmPinCode("Paweł", PIN_OK)],
            code_arm_required=False,
            arming_time_s=0,
        )
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMED_AWAY

    async def test_code_arm_required_blocks_arming_without_a_code(self):
        panel = make_panel(
            codes=[AlarmPinCode("Paweł", PIN_OK)],
            code_arm_required=True,
            arming_time_s=0,
        )
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == DISARMED

    async def test_code_arm_required_accepts_a_correct_code(self):
        panel = make_panel(
            codes=[AlarmPinCode("Paweł", PIN_OK)],
            code_arm_required=True,
            arming_time_s=0,
        )
        await panel.handle_command(
            "",
            json.dumps({"action": "ARM_AWAY", "code": PIN_OK}),
        )
        assert panel.state == ARMED_AWAY

    async def test_command_key_is_accepted_as_an_alias_for_action(self):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        await panel.handle_command(
            "",
            json.dumps({"command": "DISARM", "code": PIN_OK}),
        )
        assert panel.state == DISARMED

    async def test_malformed_json_falls_back_to_a_plain_command(self):
        panel = make_panel(arming_time_s=0)
        await panel.handle_command("", "{not json")
        assert panel.state == DISARMED  # unknown command, no crash
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMED_AWAY

    async def test_json_list_payload_does_not_crash(self):
        panel = make_panel()
        await panel.handle_command("", "[1, 2, 3]")
        assert panel.state == DISARMED


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    async def test_armed_state_is_persisted(self):
        sm = MagicMock()
        sm.get.return_value = None
        panel = make_panel(arming_time_s=0, state_manager=sm)
        await panel.handle_command("", "ARM_AWAY")
        sm.save_attribute.assert_called_with(
            attr_type="alarm_control_panel",
            attribute="alarm_test",
            value=ARMED_AWAY,
        )

    async def test_transient_states_are_not_persisted(self):
        sm = MagicMock()
        sm.get.return_value = None
        panel = make_panel(zones=[_zone()], arming_time_s=0, state_manager=sm)
        await panel.handle_command("", "ARM_AWAY")
        sm.save_attribute.reset_mock()
        panel.on_input_event("in_05", "pressed")
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED
        sm.save_attribute.assert_not_called()

    async def test_state_is_restored_on_construction(self):
        sm = MagicMock()
        sm.get.return_value = ARMED_NIGHT
        assert make_panel(state_manager=sm).state == ARMED_NIGHT

    async def test_unpersistable_restored_value_is_discarded(self):
        sm = MagicMock()
        sm.get.return_value = TRIGGERED
        assert make_panel(state_manager=sm).state == DISARMED

    async def test_no_state_manager_is_harmless(self):
        panel = make_panel(arming_time_s=0, state_manager=None)
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMED_AWAY


# ---------------------------------------------------------------------------
# MQTT surface
# ---------------------------------------------------------------------------


class TestMqtt:
    async def test_state_is_published_retained(self):
        panel = make_panel(arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        calls = [
            c for c in panel._message_bus.send_message.call_args_list if c.kwargs.get("topic", "").endswith("/state")
        ]
        assert calls, "stan nie został opublikowany"
        assert calls[-1].kwargs["payload"] == ARMED_AWAY
        assert calls[-1].kwargs["retain"] is True

    async def test_topics_are_namespaced_by_prefix_and_id(self):
        panel = make_panel()
        assert panel._state_topic == "boneio/alarm/alarm_test/state"
        assert panel._cmd_topic == "boneio/cmd/alarm/alarm_test/set"
        assert panel._attributes_topic == "boneio/alarm/alarm_test/attributes"

    async def test_start_subscribes_and_publishes_initial_state(self):
        panel = make_panel()
        panel._message_bus.subscribe_and_listen = AsyncMock()
        await panel.start()
        panel._message_bus.subscribe_and_listen.assert_awaited_once()
        assert panel._message_bus.subscribe_and_listen.await_args.args[0] == panel._cmd_topic
        assert sent_payloads(panel, "/state") == [DISARMED]

    async def test_stop_unsubscribes_and_cancels_timers(self):
        panel = make_panel(arming_time_s=5)
        panel._message_bus.unsubscribe_and_stop_listen = AsyncMock()
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMING
        await panel.stop()
        panel._message_bus.unsubscribe_and_stop_listen.assert_awaited_once()
        assert panel._arming_timer is None

    async def test_stop_survives_a_broken_message_bus(self):
        panel = make_panel()
        panel._message_bus.unsubscribe_and_stop_listen = AsyncMock(side_effect=RuntimeError("broker gone"))
        await panel.stop()  # must not raise


# ---------------------------------------------------------------------------
# Wrong-code throttling (PLAN_OSDP §7.2 pt 1)
# ---------------------------------------------------------------------------


def disarm_with(code: str) -> str:
    return json.dumps({"action": "DISARM", "code": code})


class FakeClock:
    """Stands in for time.monotonic so a 30-second lockout takes no time."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr("boneio.components.template.alarm_panel.time.monotonic", fake)
    return fake


class TestCodeThrottling:
    async def armed_panel(self) -> BoneIOAlarmPanel:
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        return panel

    async def test_outcomes_are_reported(self, clock):
        panel = await self.armed_panel()
        assert await panel.handle_command("", "DISARM") == CODE_MISSING
        assert await panel.handle_command("", disarm_with(PIN_BAD)) == CODE_INVALID
        assert await panel.handle_command("", disarm_with(PIN_OK)) == CODE_OK

    async def test_locks_after_the_limit_and_refuses_even_the_right_code(self, clock):
        panel = await self.armed_panel()
        for _ in range(CODE_MAX_FAILURES - 1):
            assert await panel.handle_command("", disarm_with(PIN_BAD)) == CODE_INVALID
        assert await panel.handle_command("", disarm_with(PIN_BAD)) == CODE_LOCKED
        assert panel.code_locked_remaining_s == CODE_LOCKOUT_BASE_S
        # Unchecked while locked: the right code does not get through either.
        assert await panel.handle_command("", disarm_with(PIN_OK)) == CODE_LOCKED
        assert panel.state == ARMED_AWAY

    async def test_lock_expires_and_the_right_code_then_works(self, clock):
        panel = await self.armed_panel()
        for _ in range(CODE_MAX_FAILURES):
            await panel.handle_command("", disarm_with(PIN_BAD))
        clock.now += CODE_LOCKOUT_BASE_S + 0.1
        assert panel.code_locked_remaining_s is None
        assert await panel.handle_command("", disarm_with(PIN_OK)) == CODE_OK
        assert panel.state == DISARMED
        assert panel.code_failed_attempts == 0

    async def test_each_further_run_doubles_the_pause_up_to_the_cap(self, clock):
        panel = await self.armed_panel()
        pauses = []
        for _ in range(8):
            for _ in range(CODE_MAX_FAILURES):
                await panel.handle_command("", disarm_with(PIN_BAD))
            pauses.append(panel.code_locked_remaining_s)
            clock.now += CODE_LOCKOUT_MAX_S + 1
        assert pauses[:4] == [30.0, 60.0, 120.0, 240.0]
        assert max(pauses) == CODE_LOCKOUT_MAX_S

    async def test_the_right_code_resets_the_count(self, clock):
        panel = await self.armed_panel()
        for _ in range(CODE_MAX_FAILURES - 1):
            await panel.handle_command("", disarm_with(PIN_BAD))
        await panel.handle_command("", disarm_with(PIN_OK))
        await panel.handle_command("", "ARM_AWAY")
        # A fresh allowance: another four wrong codes do not lock.
        for _ in range(CODE_MAX_FAILURES - 1):
            assert await panel.handle_command("", disarm_with(PIN_BAD)) == CODE_INVALID

    async def test_a_missing_code_is_not_counted_as_a_guess(self, clock):
        panel = await self.armed_panel()
        for _ in range(CODE_MAX_FAILURES * 2):
            assert await panel.handle_command("", "DISARM") == CODE_MISSING
        assert panel.code_failed_attempts == 0

    async def test_lockout_is_published_for_ha(self, clock):
        panel = await self.armed_panel()
        for _ in range(CODE_MAX_FAILURES):
            await panel.handle_command("", disarm_with(PIN_BAD))
        attrs = json.loads(sent_payloads(panel, "/attributes")[-1])
        assert attrs["code_failed_attempts"] == CODE_MAX_FAILURES
        assert attrs["code_locked_s"] == CODE_LOCKOUT_BASE_S

    async def test_arming_with_code_arm_required_is_throttled_too(self, clock):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], code_arm_required=True, arming_time_s=0)
        for _ in range(CODE_MAX_FAILURES):
            await panel.handle_command("", json.dumps({"action": "ARM_AWAY", "code": PIN_BAD}))
        assert await panel.handle_command("", json.dumps({"action": "ARM_AWAY", "code": PIN_OK})) == CODE_LOCKED
        assert panel.state == DISARMED


class TestCodeLockSensor:
    """The "codes locked" binary_sensor HA automations react to."""

    async def test_lockout_turns_it_on_and_its_end_turns_it_off(self, monkeypatch):
        # Real time with a short lockout: the OFF comes from loop.call_later.
        monkeypatch.setattr("boneio.components.template.alarm_panel.CODE_LOCKOUT_BASE_S", 0.05)
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        for _ in range(CODE_MAX_FAILURES):
            await panel.handle_command("", disarm_with(PIN_BAD))
        assert sent_payloads(panel, "/code_lock") == ["ON"]
        await asyncio.sleep(0.1)
        assert sent_payloads(panel, "/code_lock") == ["ON", "OFF"]
        # And the attributes HA shows beside it no longer claim a lock.
        assert json.loads(sent_payloads(panel, "/attributes")[-1])["code_locked_s"] is None

    async def test_wrong_codes_below_the_limit_leave_it_alone(self):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        for _ in range(CODE_MAX_FAILURES - 1):
            await panel.handle_command("", disarm_with(PIN_BAD))
        assert sent_payloads(panel, "/code_lock") == []

    async def test_start_clears_a_retained_on_from_before_a_restart(self):
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)])
        panel._message_bus.subscribe_and_listen = AsyncMock()
        await panel.start()
        call = [c for c in panel._message_bus.send_message.call_args_list if c.kwargs["topic"].endswith("/code_lock")]
        assert [c.kwargs["payload"] for c in call] == ["OFF"]
        assert call[0].kwargs["retain"] is True

    async def test_a_panel_without_codes_never_publishes_it(self):
        panel = make_panel()
        panel._message_bus.subscribe_and_listen = AsyncMock()
        await panel.start()
        assert sent_payloads(panel, "/code_lock") == []

    async def test_stop_cancels_the_pending_off(self, monkeypatch):
        monkeypatch.setattr("boneio.components.template.alarm_panel.CODE_LOCKOUT_BASE_S", 0.05)
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], arming_time_s=0)
        panel._message_bus.unsubscribe_and_stop_listen = AsyncMock()
        await panel.handle_command("", "ARM_AWAY")
        for _ in range(CODE_MAX_FAILURES):
            await panel.handle_command("", disarm_with(PIN_BAD))
        await panel.stop()
        await asyncio.sleep(0.1)
        assert sent_payloads(panel, "/code_lock") == ["ON"]


def test_code_lock_discovery_message():
    from boneio.integration.homeassistant import ha_alarm_code_lock_message

    helper = MagicMock()
    helper.topic_prefix = "boneio/blk265f49"
    helper.name = "boneIO Black"
    helper.device_type = "32x10"
    helper.configuration_url = None
    helper.real_serial = "blk265f49"
    helper.serial_number = "blk265f49"
    helper.ha_child_devices = False
    msg = ha_alarm_code_lock_message(id="alarm_dom", name="Alarm Dom", config_helper=helper)
    assert msg["state_topic"] == "boneio/blk265f49/alarm/alarm_dom/code_lock"
    assert msg["json_attributes_topic"] == "boneio/blk265f49/alarm/alarm_dom/attributes"
    assert (msg["payload_on"], msg["payload_off"], msg["device_class"]) == ("ON", "OFF", "tamper")
    assert msg["default_entity_id"] == "binary_sensor.blk265f49_alarm_dom_code_lock"
    assert msg["name"] == "Alarm Dom code lockout"


# ---------------------------------------------------------------------------
# Current weaknesses — pinned deliberately
# ---------------------------------------------------------------------------


class TestKnownWeaknesses:
    """Behaviour that is weak today and expected to change.

    These assert what the code *does*, not what it *should* do.  They exist so
    the change is visible in a diff rather than silent.  See PLAN_OSDP.md §7.2:
    once a keypad hangs on an outside wall, every one of these becomes a real
    exposure and is scheduled to be fixed — at which point these tests should
    fail and be rewritten.
    """

    async def test_no_codes_configured_means_no_protection(self):
        """§7.2 pkt 5 — an empty code list authorises everyone."""
        panel = make_panel(codes=[], code_arm_required=True, arming_time_s=0)
        await panel.handle_command("", "ARM_AWAY")
        assert panel.state == ARMED_AWAY
        await panel.handle_command("", "DISARM")
        assert panel.state == DISARMED

    async def test_trigger_command_needs_no_code(self):
        """§7.2 pkt 4 — anyone on the broker can sound the siren."""
        siren = make_output()
        panel = make_panel(codes=[AlarmPinCode("Paweł", PIN_OK)], outputs=[siren])
        await panel.handle_command("", "TRIGGER")
        await asyncio.sleep(0.02)
        assert panel.state == TRIGGERED
        siren.output.async_turn_on.assert_awaited_once()

    def test_pin_hash_is_unsalted_sha256(self):
        """§7.2 pkt 2 — a 4-digit PIN falls to a rainbow table instantly."""
        a = AlarmPinCode("Paweł", PIN_OK)
        b = AlarmPinCode("Ala", PIN_OK)
        # Same PIN, different users, identical digest: no per-user salt.
        assert a.code_hash == b.code_hash
        assert a.code_hash == hashlib.sha256(PIN_OK.encode()).hexdigest()
