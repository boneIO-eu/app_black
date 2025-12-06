"""Basic Output module (formerly BasicRelay)."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from boneio.const import COVER, LIGHT, NONE, OFF, ON, RELAY, STATE, SWITCH
from boneio.core.messaging import BasicMqtt
from boneio.models.events import OutputEvent
from boneio.core.events import EventBus, async_track_point_in_time, utcnow
from boneio.integration.interlock import SoftwareInterlockManager
from boneio.core.utils import callback
from boneio.core.messaging.basic import MessageBus
from boneio.models import OutputState

_LOGGER = logging.getLogger(__name__)


class VirtualEnergySensor:

    def __init__(self, message_bus: MessageBus, loop: asyncio.AbstractEventLoop, topic_prefix: str, parent: BasicOutput, virtual_power_usage: float | None = None, virtual_volume_flow_rate: float | None = None):
        self._loop = loop or asyncio.get_running_loop()
        self._message_bus = message_bus
        self._virtual_sensors_task = None
        self._parent = parent
        self._virtual_power_usage = virtual_power_usage
        self._virtual_volume_flow_rate = virtual_volume_flow_rate
        # --- Virtual energy counter ---
        self._energy_consumed_Wh = 0.0
        self._water_consumed_L = 0.0
        self._last_on_timestamp = time.time() if self._parent.state == ON else None
        self._virtual_energy_topic = f"{topic_prefix}/energy/{self._parent.id}"
        self._subscribe_restore_energy_state()

    def start_virtual_sensors_task(self):
        """Start periodic task to update and send virtual energy state every 30 seconds."""
        self._last_on_timestamp = time.time()
        if self._virtual_sensors_task is not None and not self._virtual_sensors_task.done():
            return  # Already running
        self._virtual_sensors_task = self._loop.create_task(self._virtual_sensors_loop())
        _LOGGER.info(f"Started periodic virtual sensors task for {self._parent.id}")

    def stop_virtual_sensors_task(self):
        """Stop periodic virtual energy update task."""
        self._last_on_timestamp = None
        if self._virtual_sensors_task is not None:
            self._virtual_sensors_task.cancel()
            self._virtual_sensors_task = None
            self._update_virtual_sensors()
            _LOGGER.info(f"Stopped periodic virtual sensors task for {self._parent.id}")

    @property
    def last_on_timestamp(self) -> float | None:
        return self._last_on_timestamp

    @property
    def virtual_power_usage(self) -> float | None:
        return self._virtual_power_usage

    @property
    def virtual_volume_flow_rate(self) -> float | None:
        return self._virtual_volume_flow_rate

    async def _virtual_sensors_loop(self):
        """Periodically update and send virtual energy state every 30 seconds while relay is ON."""
        try:
            while self._parent.state == ON:
                self._update_virtual_sensors()
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    def _update_virtual_sensors(self):
        """Update virtual sensors if virtual_power_usage is set."""
        if self.virtual_power_usage is not None or self.virtual_volume_flow_rate is not None:
            self._update_virtual_energy()
            self.send_virtual_energy_state()


    def _update_virtual_energy(self):
        """Update energy counter if virtual_power_usage is set."""
        now = time.time()
        if self._parent.state == ON and self._last_on_timestamp is not None:
            elapsed = now - self._last_on_timestamp
            if self.virtual_power_usage is not None:
                self._energy_consumed_Wh += (self.virtual_power_usage * elapsed) / 3600.0
                _LOGGER.debug(f"Energy updated for {self._parent.id}: {self._energy_consumed_Wh:.4f} Wh")
            if self.virtual_volume_flow_rate is not None:
                self._water_consumed_L += (self.virtual_volume_flow_rate * elapsed) / 3600.0
                _LOGGER.debug(f"Volume flow rate updated for {self._parent.id}: {self._water_consumed_L:.4f} L")
            self._last_on_timestamp = now

    def _subscribe_restore_energy_state(self):
        """
        Subscribe to the retained MQTT topic for energy and restore state if available.
        """
        async def on_energy_message(_topic, payload):
            try:
                payload = json.loads(payload)
                if isinstance(payload, dict):
                    if "energy" in payload:
                        retained_energy_wh = float(payload["energy"])
                        self._energy_consumed_Wh = retained_energy_wh
                        _LOGGER.info(f"Restored energy state for {self._parent.id} from MQTT: {self._energy_consumed_Wh:.4f} Wh")
                    if "water" in payload:
                        retained_water_consumption_L = float(payload["water"])
                        self._water_consumed_L = retained_water_consumption_L
                        _LOGGER.info(f"Restored water consumption state for {self._parent.id} from MQTT: {self._water_consumed_L:.4f} L")
                else:
                    _LOGGER.warning(f"Invalid retained payload for {self._parent.id}: {payload}")
            except Exception as e:
                _LOGGER.warning(f"Failed to restore energy state for {self._parent.id} from MQTT: {e}")
            finally:
                await self._message_bus.unsubscribe_and_stop_listen(self._virtual_energy_topic)
        # Subscribe (works for both LocalMessageBus and MQTTClient)
        if hasattr(self, '_message_bus') and self._message_bus is not None:
            asyncio.create_task(self._message_bus.subscribe_and_listen(self._virtual_energy_topic, on_energy_message))
        else:
            _LOGGER.warning(f"Message bus not available for {self._parent.id}, cannot subscribe for retained energy.")

    def get_virtual_power(self) -> float:
        """Return current virtual power usage in W."""
        return (self.virtual_power_usage or 0.0) if self._parent.state == ON else 0.0

    def get_virtual_energy(self) -> float:
        """Return current virtual energy in Wh."""
        return round(self._energy_consumed_Wh, 3)

    def get_virtual_volume_flow_rate(self) -> float:
        """Return current virtual volume flow rate in L/h."""
        return (self.virtual_volume_flow_rate or 0.0) if self._parent.state == ON else 0.0

    def get_virtual_water_consumption(self) -> float:
        """Return current virtual water consumption in L."""
        return round(self._water_consumed_L, 3)

    def send_virtual_energy_state(self):
        """Send virtual power/energy state to MQTT for Home Assistant."""
        payload = {}
        if self.virtual_power_usage is not None:
            payload["power"] = self.get_virtual_power()
            payload["energy"] = self.get_virtual_energy()
        if self.virtual_volume_flow_rate is not None:
            payload["volume_flow_rate"] = self.get_virtual_volume_flow_rate()
            payload["water"] = self.get_virtual_water_consumption()
        self._message_bus.send_message(
            topic=f"{self._virtual_energy_topic}",
            payload=payload,
            retain=True,
        )
        _LOGGER.info(f"Sent virtual energy state for {self._parent.id}: {payload}")


class BasicOutput(BasicMqtt):
    """Basic output class (relay, switch, light, PWM).
    
    Formerly known as BasicRelay. This class represents any controllable
    output device in the BoneIO system.
    """
    
    # Subclasses (e.g. MCPOutput) will override these
    _pin_id: int = -1
    _expander_id: str | None = None

    def __init__(
        self,
        # callback: Callable[[OutputState], Awaitable[None]],
        id: str,
        event_bus: EventBus,
        topic_prefix: str,
        name: str | None = None,
        output_type=SWITCH,
        restored_state: bool = False,
        topic_type: str = RELAY,
        interlock_manager: SoftwareInterlockManager | None = None,
        interlock_groups: list[str] = [],
        **kwargs,
    ) -> None:
        """Initialize Basic relay.
        Supports virtual_power_usage for energy monitoring.
        """
        self._momentary_turn_on = kwargs.pop("momentary_turn_on", None)
        self._momentary_turn_off = kwargs.pop("momentary_turn_off", None)
        virtual_power_usage = kwargs.pop("virtual_power_usage", None)
        virtual_volume_flow_rate = kwargs.pop("virtual_volume_flow_rate", None)
        # No parsing needed, Cerberus coerce handles conversion to watts.
        super().__init__(id=id, name=name or id, topic_type=topic_type, topic_prefix=topic_prefix, **kwargs)
        self._output_type: str = output_type
        self._event_bus: EventBus = event_bus
        self._interlock_manager: SoftwareInterlockManager | None = interlock_manager
        self._interlock_groups: list[str] = interlock_groups
        if output_type == COVER:
            self._momentary_turn_on = None
            self._momentary_turn_off = None
        self._state = ON if restored_state else OFF
        # self._callback = callback
        self._momentary_action = None
        self._last_timestamp = 0.0
        self._loop = asyncio.get_running_loop()
        
        # Subscribe to retained MQTT energy value
        self._virtual_energy_sensor = None
        if virtual_power_usage is not None or virtual_volume_flow_rate is not None:
            self._virtual_energy_sensor = VirtualEnergySensor(
                message_bus=self._message_bus,
                loop=self._loop,
                topic_prefix=topic_prefix,
                parent=self,
                virtual_power_usage=virtual_power_usage,
                virtual_volume_flow_rate=virtual_volume_flow_rate,
            )
            self._virtual_sensors_task = None
        
        # HA area/room assignment (set by OutputManager)
        self.area: str | None = None

    def set_interlock(self, interlock_manager: SoftwareInterlockManager, interlock_groups: list[str]):
        self._interlock_manager = interlock_manager
        self._interlock_groups = interlock_groups


    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is mcp type."""
        return False

    @property
    def is_virtual_power(self) -> bool:
        return self._virtual_energy_sensor is not None and self._virtual_energy_sensor.virtual_power_usage is not None

    @property
    def is_virtual_volume_flow_rate(self) -> bool:
        return self._virtual_energy_sensor is not None and self._virtual_energy_sensor.virtual_volume_flow_rate is not None

    @property
    def output_type(self) -> str:
        """HA type."""
        return self._output_type

    @property
    def is_light(self) -> bool:
        """Check if HA type is light"""
        return self._output_type == LIGHT

    @property
    def id(self) -> str:
        """Id of the relay.
        Has to be trimmed out of spaces because of MQTT handling in HA."""
        return self._id or str(self._pin_id) or ""

    @property
    def name(self) -> str:
        """Not trimmed id."""
        return self._name or str(self._pin_id) or ""
    
    @property
    def pin_id(self) -> str | None:
        """Pin ID as string for OutputState model."""
        return str(self._pin_id) if self._pin_id is not None else None

    @property
    def state(self) -> str:
        """Is relay active."""
        return self._state
    

    @property
    def last_timestamp(self) -> float:
        return self._last_timestamp

    def payload(self) -> dict[str, str | float | int | None]:
        """Return payload for MQTT message.
        
        Returns:
            Dictionary with state information for MQTT publishing.
        """
        return {STATE: self.state}

    async def async_send_state(self, optimized_value: str | None = None) -> None:
        """Send state to Mqtt on action asynchronously."""
        if optimized_value:
            state = optimized_value
        else:
            state = ON if self.is_active else OFF
        self._state = state
        if self.output_type not in (COVER, NONE):
            self._message_bus.send_message(
                topic=self._send_topic,
                payload={STATE: state},
                retain=True,
            )
            if self._virtual_energy_sensor and not optimized_value:
                if state == ON:
                    self._virtual_energy_sensor.start_virtual_sensors_task()
                elif self._virtual_energy_sensor.last_on_timestamp is not None:
                    self._virtual_energy_sensor.stop_virtual_sensors_task()
        if optimized_value:
            return
        self._last_timestamp = time.time()
        output_state = OutputState(
            id=self.id,
            name=self.name,
            state=state,
            type=self.output_type,
            pin=self.pin_id,
            timestamp=self.last_timestamp,
            expander_id=self.expander_id,
            area=self.area,
            interlock_groups=self._interlock_groups,
        )
        
        output_event = OutputEvent(
            entity_id=self.id,
            state=output_state,
        )
        self._event_bus.trigger_event(output_event)
        

    def check_interlock(self) -> bool:
        if self._interlock_manager is not None and self._interlock_groups:
            return self._interlock_manager.can_turn_on(self, self._interlock_groups)
        return True

    async def async_turn_on(self, timestamp=None) -> None:
        """Turn on the relay asynchronously."""
        can_turn_on = self.check_interlock()
        if can_turn_on:
            await self._loop.run_in_executor(None, self.turn_on, timestamp)
        else:
            _LOGGER.warning(f"Interlock active: cannot turn on {self.id}.")
            #Workaround for HA is sendind state ON/OFF without physically changing the relay.
            asyncio.create_task(self.async_send_state(optimized_value=ON))
            await asyncio.sleep(0.01)
        asyncio.create_task(self.async_send_state())
        

    async def async_turn_off(self, timestamp=None) -> None:
        """Turn off the relay asynchronously."""
        await self._loop.run_in_executor(None, self.turn_off, timestamp)
        await self.async_send_state()


    async def async_toggle(self, timestamp=None) -> None:
        """Toggle relay."""
        now = time.time()
        _LOGGER.debug("Toggle relay %s, state: %s, at %s.", self.name, self.state, now)
        if self.state == ON:
            await self.async_turn_off(timestamp=timestamp)
        else:
            await self.async_turn_on(timestamp=timestamp)

    def turn_on(self, timestamp=None) -> None:
        """Call turn on action."""
        raise NotImplementedError
    
    def turn_off(self, timestamp=None) -> None:
        """Call turn off action."""
        raise NotImplementedError

    def set_brightness(self, value: int) -> None:
        """Set brightness (only supported on PWM outputs like PCA9685)."""
        _LOGGER.warning("set_brightness not supported for %s output type", self.output_type)

    def _execute_momentary_turn(self, momentary_type: str) -> None:
        """Execute momentary action."""
        if self._momentary_action:
            _LOGGER.debug("Cancelling momentary action for %s", self.name)
            self._momentary_action()
        (action, delayed_action) = (
            (self.async_turn_off, self._momentary_turn_on)
            if momentary_type == ON
            else (self.async_turn_on, self._momentary_turn_off)
        )
        if delayed_action:
            _LOGGER.debug("Applying momentary action for %s in %s", self.name, delayed_action.as_timedelta)
            self._momentary_action = async_track_point_in_time(
                loop=self._loop,
                job=self._momentary_callback,
                point_in_time=utcnow() + delayed_action.as_timedelta,
                action=action,
            )

    @callback
    async def _momentary_callback(self, timestamp, action):
        _LOGGER.info("Momentary callback at %s for output %s", timestamp, self.name)
        await action(timestamp=timestamp)
        self._momentary_action = None

    @property
    def is_active(self) -> bool:
        """Is active check."""
        raise NotImplementedError

    @property
    def expander_id(self) -> str | None:
        """Retrieve parent Expander ID (set by subclasses like MCPOutput)."""
        return self._expander_id
