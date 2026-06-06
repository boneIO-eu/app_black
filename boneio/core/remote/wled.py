"""WLED remote device support via HTTP JSON API.

This module provides integration with WLED LED controllers using their
native HTTP JSON API for controlling lights, segments, brightness, and colors.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import TYPE_CHECKING, Any

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

from boneio.core.remote.base import (
    RemoteDevice,
    RemoteDeviceProtocol,
    RemoteDeviceType,
)

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class WLEDRemoteDevice(RemoteDevice):
    """WLED HTTP API-based remote device.
    
    Controls WLED LED strips via native HTTP JSON API.
    Supports segments, brightness, and RGB color control.
    
    Args:
        id: Device identifier
        name: Human-readable name
        host: IP address or hostname of WLED device
        port: HTTP port (default 80)
        segments: List of segment configurations
    """
    
    def __init__(
        self,
        id: str,
        name: str,
        host: str,
        port: int = 80,
        segments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize WLED remote device.
        
        Args:
            id: Device identifier
            name: Human-readable name
            host: IP address or hostname
            port: HTTP port (default 80)
            segments: List of segment configurations
        """
        super().__init__(
            id=id,
            name=name,
            protocol=RemoteDeviceProtocol.WLED,
            device_type=RemoteDeviceType.WLED,
            config={
                "host": host,
                "port": port,
            },
        )
        
        self._host = host
        self._port = port
        self._segments: list[dict[str, Any]] = segments or []
        self._device_info: dict[str, Any] = {}
        self._session: aiohttp.ClientSession | None = None
        
        # WebSocket state tracking — real-time state cache
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_task: asyncio.Task | None = None
        self._cached_state: dict[str, Any] = {}  # {"on": bool, "bri": int, "seg": [...]}
        self._ws_connected = False
        self._state_callbacks: list[Any] = []  # Callable[[dict], None]
        # Per-output callbacks for RemoteOutputBase integration.
        # Key: output_id ("main" or segment ID str), Value: Callable(bool, brightness=int|None)
        self._output_callbacks: dict[str, Any] = {}
        
        _LOGGER.info(
            "Configured WLED remote device '%s' (host=%s:%d, segments=%d)",
            name, host, port, len(self._segments)
        )
    
    @property
    def host(self) -> str:
        """Get device host."""
        return self._host
    
    @property
    def port(self) -> int:
        """Get device port."""
        return self._port
    
    @property
    def segments(self) -> list[dict[str, Any]]:
        """Get list of segments."""
        return self._segments
    
    @property
    def base_url(self) -> str:
        """Get base URL for WLED API."""
        return f"http://{self._host}:{self._port}"
    
    def has_segment(self, segment_id: int | str) -> bool:
        """Check if device has a segment with given ID.
        
        Args:
            segment_id: Segment ID to check
            
        Returns:
            True if segment exists
        """
        seg_id = int(segment_id) if isinstance(segment_id, str) else segment_id
        return any(s.get("id") == seg_id for s in self._segments)
    
    def get_segment(self, segment_id: int | str) -> dict[str, Any] | None:
        """Get segment by ID.
        
        Args:
            segment_id: Segment ID
            
        Returns:
            Segment dict or None if not found
        """
        seg_id = int(segment_id) if isinstance(segment_id, str) else segment_id
        for seg in self._segments:
            if seg.get("id") == seg_id:
                return seg
        return None
    
    async def close(self) -> None:
        """Close WebSocket and aiohttp session."""
        # Stop WebSocket listener
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        
        # Close WebSocket
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None
            self._ws_connected = False
        
        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            _LOGGER.debug("Closed session for WLED '%s'", self._name)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def _send_state(self, state: dict[str, Any]) -> bool:
        """Send state update to WLED device.
        
        Args:
            state: State object to send
            
        Returns:
            True if successful
        """
        if not AIOHTTP_AVAILABLE:
            _LOGGER.error("aiohttp not available for WLED control")
            return False
        
        url = f"{self.base_url}/json/state"
        
        try:
            session = await self._get_session()
            async with session.post(url, json=state) as response:
                if response.status == 200:
                    _LOGGER.debug("WLED state update successful: %s", state)
                    return True
                else:
                    _LOGGER.error(
                        "WLED state update failed: %s (status=%d)",
                        await response.text(), response.status
                    )
                    return False
        except TimeoutError:
            _LOGGER.error("WLED request timeout for %s", self._host)
            return False
        except aiohttp.ClientError as e:
            _LOGGER.error("WLED request failed for %s: %s", self._host, e)
            return False
        except Exception as e:
            _LOGGER.error("WLED unexpected error for %s: %s", self._host, e)
            return False

    async def _get_current_brightness(self, segment_id: int | None = None) -> int | None:
        if not AIOHTTP_AVAILABLE:
            return None
        
        url = f"{self.base_url}/json/state"
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if segment_id is not None:
                        for seg in data.get("seg", []):
                            if seg.get("id") == segment_id:
                                return seg.get("bri")
                    return data.get("bri")
        except Exception as e:
            _LOGGER.error("WLED failed to get brightness for %s: %s", self._host, e)
        return None
    
    async def control_light(
        self,
        segment_id: int | None = None,
        action: str = "TOGGLE",
        brightness: int | None = None,
        rgb: tuple[int, int, int] | list[int] | None = None,
        transition: float = 0.0,
        effect: int | None = None,
        palette: int | None = None,
        effect_speed: int | None = None,
        effect_intensity: int | None = None,
        brightness_step: int | None = None,
    ) -> bool:
        """Control WLED light or segment.
        
        Args:
            segment_id: Segment ID (None for whole device)
            action: Action to perform (ON, OFF, TOGGLE)
            brightness: Brightness value (0-255)
            rgb: RGB color tuple or list (0-255 each)
            transition: Transition time in seconds (converted to 100ms units)
            effect: Effect ID (0 = Solid, see WLED effects list)
            palette: Color palette ID
            effect_speed: Effect speed (0-255)
            effect_intensity: Effect intensity (0-255)
            
        Returns:
            True if command was sent successfully
        """
        state: dict[str, Any] = {}
        
        # Add transition if specified (WLED uses 100ms units)
        if transition > 0:
            state["transition"] = int(transition * 10)

        # Convert percentage (1-100) to 0-255 range for WLED
        step_val = int(round((brightness_step or 10) * 2.55))
        
        if action in ("BRIGHTNESS_UP", "BRIGHTNESS_UP_CYCLE", "BRIGHTNESS_DOWN", "BRIGHTNESS_DOWN_CYCLE"):
            current_bri = await self._get_current_brightness(segment_id)
            if current_bri is not None:
                if action in ("BRIGHTNESS_UP", "BRIGHTNESS_UP_CYCLE"):
                    new_bri = current_bri + step_val
                    if new_bri > 255:
                        new_bri = 1 if action == "BRIGHTNESS_UP_CYCLE" else 255
                else: # DOWN
                    new_bri = current_bri - step_val
                    if new_bri < 1:
                        new_bri = 255 if action == "BRIGHTNESS_DOWN_CYCLE" else 1
                brightness = int(new_bri)
        
        if segment_id is not None:
            # Control specific segment
            seg_state: dict[str, Any] = {"id": segment_id}
            
            if action == "ON":
                seg_state["on"] = True
            elif action == "OFF":
                seg_state["on"] = False
            elif action == "TOGGLE":
                seg_state["on"] = "t"  # WLED toggle syntax
            
            if brightness is not None:
                seg_state["bri"] = max(0, min(255, brightness))
            
            if rgb is not None:
                # WLED expects [[R, G, B]] for primary color
                seg_state["col"] = [[rgb[0], rgb[1], rgb[2]]]
            
            if effect is not None:
                seg_state["fx"] = effect
            
            if palette is not None:
                seg_state["pal"] = palette
            
            if effect_speed is not None:
                seg_state["sx"] = max(0, min(255, effect_speed))
            
            if effect_intensity is not None:
                seg_state["ix"] = max(0, min(255, effect_intensity))
            
            state["seg"] = [seg_state]
        else:
            # Control whole device
            if action == "ON":
                state["on"] = True
            elif action == "OFF":
                state["on"] = False
            elif action == "TOGGLE":
                state["on"] = "t"
            
            if brightness is not None:
                state["bri"] = max(0, min(255, brightness))
            
            # For whole device, apply effect/color to first segment
            main_seg: dict[str, Any] = {"id": 0}
            has_seg_changes = False
            
            if rgb is not None:
                main_seg["col"] = [[rgb[0], rgb[1], rgb[2]]]
                has_seg_changes = True
            
            if effect is not None:
                main_seg["fx"] = effect
                has_seg_changes = True
            
            if palette is not None:
                main_seg["pal"] = palette
                has_seg_changes = True
            
            if effect_speed is not None:
                main_seg["sx"] = max(0, min(255, effect_speed))
                has_seg_changes = True
            
            if effect_intensity is not None:
                main_seg["ix"] = max(0, min(255, effect_intensity))
                has_seg_changes = True
            
            if has_seg_changes:
                state["seg"] = [main_seg]
        
        _LOGGER.debug(
            "Controlling WLED '%s' segment=%s action=%s brightness=%s rgb=%s effect=%s palette=%s",
            self._name, segment_id, action, brightness, rgb, effect, palette
        )
        
        return await self._send_state(state)
    
    async def control_output(
        self,
        output_id: str,
        action: str,
        message_bus: Any = None,
        brightness: int | None = None,
        **kwargs: Any,
    ) -> bool:
        """Control an output (segment) on the WLED device.
        
        Args:
            output_id: Segment ID as string (e.g., "0", "1", "main")
            action: Action to perform (ON, OFF, TOGGLE)
            message_bus: Not used for WLED
            brightness: Optional brightness value (0-255)
            
        Returns:
            True if command was sent successfully
        """
        # Parse segment_id - "main" means whole device
        segment_id = None if output_id == "main" else int(output_id)
        return await self.control_light(
            segment_id=segment_id, action=action, brightness=brightness,
        )
    
    async def control_cover(
        self,
        cover_id: str,
        action: str,
        message_bus: Any = None,
        **kwargs,
    ) -> bool:
        """WLED does not support covers.
        
        Returns:
            Always False
        """
        _LOGGER.warning("WLED device '%s' does not support covers", self._name)
        return False
    
    async def discover_info(self) -> dict[str, Any]:
        """Discover WLED device info and segments.
        
        Returns:
            Dictionary with device info and segments
        """
        if not AIOHTTP_AVAILABLE:
            _LOGGER.error("aiohttp not available for WLED discovery")
            return {"error": "aiohttp not available"}
        
        url = f"{self.base_url}/json"
        
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    return {"error": f"HTTP {response.status}"}
                
                data = await response.json()
                
                # Extract device info
                info = data.get("info", {})
                state = data.get("state", {})
                
                # Extract segments
                segments = []
                for seg in state.get("seg", []):
                    seg_info = {
                        "id": seg.get("id", 0),
                        "name": seg.get("n", f"Segment {seg.get('id', 0)}"),
                        "start": seg.get("start", 0),
                        "stop": seg.get("stop", 0),
                        "len": seg.get("len", 0),
                        "on": seg.get("on", False),
                        "bri": seg.get("bri", 255),
                        "supports_rgb": True,  # WLED always supports RGB
                    }
                    # Get current color
                    cols = seg.get("col", [])
                    if cols and len(cols) > 0:
                        seg_info["color"] = cols[0][:3] if len(cols[0]) >= 3 else [255, 255, 255]
                    segments.append(seg_info)
                
                # Extract effects list (including Solid at id=0)
                effects = []
                effects_list = data.get("effects", [])
                for idx, effect_name in enumerate(effects_list):
                    if effect_name:
                        effects.append({
                            "id": idx,
                            "name": effect_name,
                        })
                
                # Extract palettes list
                palettes = []
                palettes_list = data.get("palettes", [])
                for idx, palette_name in enumerate(palettes_list):
                    if palette_name:
                        palettes.append({
                            "id": idx,
                            "name": palette_name,
                        })
                
                self._device_info = {
                    "name": info.get("name", "WLED"),
                    "version": info.get("ver", "unknown"),
                    "mac": info.get("mac", ""),
                    "ip": info.get("ip", self._host),
                    "led_count": info.get("leds", {}).get("count", 0),
                    "rgbw": info.get("leds", {}).get("rgbw", False),
                    "segments": segments,
                    "effects": effects,
                    "palettes": palettes,
                    "on": state.get("on", False),
                    "bri": state.get("bri", 255),
                }
                
                # Update internal segments list
                self._segments = segments
                
                _LOGGER.info(
                    "Discovered WLED '%s' v%s with %d segments, %d LEDs",
                    self._device_info["name"],
                    self._device_info["version"],
                    len(segments),
                    self._device_info["led_count"]
                )
                
                return self._device_info
                
        except TimeoutError:
            _LOGGER.error("WLED discovery timeout for %s", self._host)
            return {"error": "timeout"}
        except aiohttp.ClientError as e:
            _LOGGER.error("WLED discovery failed for %s: %s", self._host, e)
            return {"error": str(e)}
        except Exception as e:
            _LOGGER.error("WLED discovery unexpected error for %s: %s", self._host, e)
            return {"error": str(e)}
    
    # ── WebSocket real-time state tracking ────────────────────────────────

    @property
    def is_on(self) -> bool:
        """Check if WLED device (main power) is ON.
        
        Returns:
            True if device is on (from cached WebSocket state).
        """
        return bool(self._cached_state.get("on", False))
    
    @property
    def brightness(self) -> int:
        """Get current brightness (0-255).
        
        Returns:
            Brightness value from cached state.
        """
        return int(self._cached_state.get("bri", 0))
    
    def segment_is_on(self, seg_id: int) -> bool:
        """Check if a specific segment is ON.
        
        Args:
            seg_id: Segment ID to check.
            
        Returns:
            True if segment is on.
        """
        for seg in self._cached_state.get("seg", []):
            if seg.get("id") == seg_id:
                return bool(seg.get("on", False))
        return False
    
    def segment_brightness(self, seg_id: int) -> int:
        """Get brightness of a specific segment.
        
        Args:
            seg_id: Segment ID.
            
        Returns:
            Segment brightness (0-255).
        """
        for seg in self._cached_state.get("seg", []):
            if seg.get("id") == seg_id:
                return int(seg.get("bri", 0))
        return 0
    
    def get_output_is_on(self, output_id: str) -> bool | None:
        """Get ON/OFF state for an output (segment or main).
        
        Used by condition evaluation system.
        
        Args:
            output_id: "main" for whole device, or segment ID as string.
            
        Returns:
            True/False if state is known, None if no cached state.
        """
        if not self._cached_state:
            return None
        if output_id == "main":
            return self.is_on
        try:
            return self.segment_is_on(int(output_id))
        except (ValueError, TypeError):
            return None
    
    def on_state_change(self, callback: Any) -> None:
        """Register a callback for state changes.
        
        Args:
            callback: Callable invoked with the new state dict on each update.
        """
        self._state_callbacks.append(callback)
    
    def register_output_callback(self, output_id: str, callback: Any) -> None:
        """Register a callback for specific output state changes.
        
        Compatible with ESPHome ``register_output_callback`` API so that
        ``RemoteOutputBase._register_state_callback`` works transparently.
        
        Args:
            output_id: Output identifier ("main" for device, or segment ID
                       as string e.g. "0", "1").
            callback: Callable(new_state: bool, brightness: int | None)
                      invoked when output state changes.
        """
        self._output_callbacks[output_id] = callback
        _LOGGER.debug(
            "Registered output callback for '%s' on WLED '%s'",
            output_id, self._name,
        )
    
    def unregister_output_callback(self, output_id: str) -> None:
        """Remove an output state callback.
        
        Args:
            output_id: Output identifier.
        """
        self._output_callbacks.pop(output_id, None)
    
    def start_ws_listener(self) -> None:
        """Start the background WebSocket listener task.
        
        Connects to ``ws://<host>/ws`` and receives real-time state pushes.
        Automatically reconnects on disconnection with exponential backoff.
        """
        if self._ws_task and not self._ws_task.done():
            _LOGGER.debug("WLED WS listener already running for '%s'", self._name)
            return
        
        self._ws_task = asyncio.create_task(
            self._ws_listen_loop(),
            name=f"wled_ws_{self._id}",
        )
        _LOGGER.info("Started WLED WebSocket listener for '%s'", self._name)
    
    async def _ws_listen_loop(self) -> None:
        """WebSocket listener loop with automatic reconnection.
        
        Connects to the WLED WebSocket endpoint, requests full state on connect,
        and processes incoming state updates. Reconnects with exponential backoff
        (5s → 10s → 20s → max 60s) on connection loss.
        """
        backoff_seconds = 5
        max_backoff = 60
        
        while True:
            try:
                session = await self._get_session()
                url = f"ws://{self._host}:{self._port}/ws"
                
                _LOGGER.debug("Connecting WLED WS: %s", url)
                self._ws = await session.ws_connect(url, heartbeat=30)
                self._ws_connected = True
                backoff_seconds = 5  # Reset on successful connect
                
                _LOGGER.info(
                    "WLED WebSocket connected to '%s' (%s)",
                    self._name, self._host,
                )
                
                # Request full state immediately
                await self._ws.send_json({"v": True})
                
                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = msg.json()
                            self._process_ws_state(data)
                        except Exception as e:
                            _LOGGER.warning(
                                "WLED WS parse error for '%s': %s",
                                self._name, e,
                            )
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        _LOGGER.warning(
                            "WLED WS error for '%s': %s",
                            self._name, self._ws.exception(),
                        )
                        break
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                    ):
                        break
                
                _LOGGER.warning("WLED WS disconnected from '%s'", self._name)
            
            except asyncio.CancelledError:
                _LOGGER.debug("WLED WS listener cancelled for '%s'", self._name)
                return
            except Exception as e:
                _LOGGER.warning(
                    "WLED WS connection failed for '%s': %s (retry in %ds)",
                    self._name, e, backoff_seconds,
                )
            finally:
                self._ws_connected = False
                self._ws = None
            
            # Reconnect with exponential backoff
            try:
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, max_backoff)
            except asyncio.CancelledError:
                return
    
    def _process_ws_state(self, data: dict[str, Any]) -> None:
        """Process incoming WebSocket state update.
        
        Updates the cached state and notifies registered callbacks.
        WLED sends partial updates — only changed fields are included.
        We merge them into the cached state.
        
        Args:
            data: JSON state object from WLED WebSocket.
        """
        state = data.get("state")
        if state is None:
            # Some messages are info-only (no state key)
            return
        
        # Merge top-level state fields
        old_on = self._cached_state.get("on")
        self._cached_state.update({
            k: v for k, v in state.items() if k != "seg"
        })
        
        # Merge segment states (by ID)
        if "seg" in state:
            existing_segs = {
                s.get("id"): s for s in self._cached_state.get("seg", [])
            }
            for seg in state["seg"]:
                seg_id = seg.get("id")
                if seg_id is not None:
                    if seg_id in existing_segs:
                        existing_segs[seg_id].update(seg)
                    else:
                        existing_segs[seg_id] = seg
            self._cached_state["seg"] = list(existing_segs.values())
        
        new_on = self._cached_state.get("on")
        if old_on != new_on:
            _LOGGER.debug(
                "WLED '%s' state: on=%s, bri=%s",
                self._name, new_on, self._cached_state.get("bri"),
            )
        
        # Notify per-output callbacks (for RemoteOutputBase integration)
        self._notify_output_callbacks(old_on, state)
        
        # Notify generic state callbacks
        for cb in self._state_callbacks:
            try:
                cb(self._cached_state)
            except Exception as e:
                _LOGGER.warning("WLED state callback error: %s", e)
    
    def _notify_output_callbacks(
        self,
        old_main_on: bool | None,
        state: dict[str, Any],
    ) -> None:
        """Notify per-output callbacks for main and segment state changes.
        
        Called by ``_process_ws_state`` after merging the new state.
        Only fires callbacks when the actual on/off state has changed.
        
        Args:
            old_main_on: Previous main power state (None if first update).
            state: The raw state update from WLED WebSocket.
        """
        # Main power callback
        new_main_on = self._cached_state.get("on", False)
        main_cb = self._output_callbacks.get("main")
        if main_cb is not None and old_main_on != new_main_on:
            try:
                main_cb(new_main_on)
            except Exception as e:
                _LOGGER.warning("WLED output callback error (main): %s", e)
        
        # Segment callbacks
        if "seg" in state:
            for seg in state["seg"]:
                seg_id = seg.get("id")
                if seg_id is None:
                    continue
                seg_cb = self._output_callbacks.get(str(seg_id))
                if seg_cb is None:
                    continue
                if "on" in seg:
                    try:
                        seg_cb(seg["on"], brightness=seg.get("bri"))
                    except Exception as e:
                        _LOGGER.warning(
                            "WLED output callback error (seg %s): %s",
                            seg_id, e,
                        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.
        
        Exposes WLED outputs as ``lights`` so the frontend
        ``RemoteOutputForm`` can list them in the output dropdown,
        identical to ESPHome devices.
        
        Returns:
            Dictionary with device information
        """
        data = super().to_dict()
        data["host"] = self._host
        data["port"] = self._port
        data["segments"] = self._segments
        data["wled"] = {
            "host": self._host,
            "port": self._port,
            "segments": self._segments,
        }
        # Expose outputs as lights for RemoteOutputForm compatibility
        lights: list[dict[str, Any]] = [
            {"id": "main", "name": f"{self._name} (Main)", "supports_brightness": True},
        ]
        for seg in self._segments:
            seg_id = str(seg.get("id", seg.get("seg_id", "")))
            seg_name = seg.get("name", f"Segment {seg_id}")
            lights.append({
                "id": seg_id,
                "name": seg_name,
                "supports_brightness": True,
            })
        data["lights"] = lights
        return data


# ==================== mDNS Discovery ====================

if ZEROCONF_AVAILABLE:
    class WLEDServiceListener(ServiceListener):
        """Listener for WLED mDNS services."""
        
        def __init__(self) -> None:
            """Initialize the listener."""
            self.devices: list[dict[str, Any]] = []
        
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            """Handle service addition."""
            info = zc.get_service_info(type_, name)
            if info:
                # Extract device name from service name
                device_name = name.replace("._wled._tcp.local.", "")
                
                # Get IP address
                ip_address = None
                if info.addresses:
                    ip_address = socket.inet_ntoa(info.addresses[0])
                
                # Get hostname - prefer server name, fallback to IP
                hostname = None
                if info.server:
                    hostname = info.server.rstrip('.')
                if not hostname:
                    hostname = ip_address
                
                self.devices.append({
                    "name": device_name,
                    "host": hostname,
                    "ip": ip_address,
                    "port": info.port or 80,
                })
                _LOGGER.debug("Found WLED device: %s at %s (IP: %s):%d", 
                             device_name, hostname, ip_address, info.port or 80)
        
        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            """Handle service removal."""
            pass
        
        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            """Handle service update."""
            pass


async def scan_wled_devices(timeout: float = 3.0) -> dict[str, Any]:
    """Scan the local network for WLED devices using mDNS.
    
    Args:
        timeout: How long to scan in seconds (default 3.0)
        
    Returns:
        Dictionary with 'devices' list containing found devices,
        each with 'name', 'host', 'ip', 'port' fields.
        May contain 'error' if scanning failed.
    """
    if not ZEROCONF_AVAILABLE:
        return {
            "devices": [],
            "error": "zeroconf not installed - mDNS discovery disabled"
        }
    
    _LOGGER.info("Scanning for WLED devices (timeout: %.1fs)...", timeout)
    
    try:
        zc = Zeroconf()
        listener = WLEDServiceListener()
        
        # Browse for WLED services
        browser = ServiceBrowser(zc, "_wled._tcp.local.", listener)
        
        # Wait for discovery
        await asyncio.sleep(timeout)
        
        # Cleanup
        browser.cancel()
        zc.close()
        
        _LOGGER.info("Found %d WLED device(s)", len(listener.devices))
        
        return {
            "devices": listener.devices,
        }
        
    except Exception as e:
        _LOGGER.error("WLED mDNS scan failed: %s", e)
        return {
            "devices": [],
            "error": str(e)
        }


async def discover_wled_info(
    host: str,
    port: int = 80,
) -> dict[str, Any]:
    """Discover WLED device info and segments.
    
    Standalone function for discovery endpoint.
    
    Args:
        host: IP address or hostname
        port: HTTP port (default 80)
        
    Returns:
        Dictionary with device info and segments
    """
    temp_device = WLEDRemoteDevice(
        id="temp_discovery",
        name="Temporary Discovery",
        host=host,
        port=port,
    )
    
    try:
        result = await temp_device.discover_info()
        return result
    finally:
        await temp_device.close()
