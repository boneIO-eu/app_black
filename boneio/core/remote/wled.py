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
        except asyncio.TimeoutError:
            _LOGGER.error("WLED request timeout for %s", self._host)
            return False
        except aiohttp.ClientError as e:
            _LOGGER.error("WLED request failed for %s: %s", self._host, e)
            return False
        except Exception as e:
            _LOGGER.error("WLED unexpected error for %s: %s", self._host, e)
            return False
    
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
    ) -> bool:
        """Control an output (segment) on the WLED device.
        
        Args:
            output_id: Segment ID as string (e.g., "0", "1", "main")
            action: Action to perform (ON, OFF, TOGGLE)
            message_bus: Not used for WLED
            
        Returns:
            True if command was sent successfully
        """
        # Parse segment_id - "main" means whole device
        segment_id = None if output_id == "main" else int(output_id)
        return await self.control_light(segment_id=segment_id, action=action)
    
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
                
        except asyncio.TimeoutError:
            _LOGGER.error("WLED discovery timeout for %s", self._host)
            return {"error": "timeout"}
        except aiohttp.ClientError as e:
            _LOGGER.error("WLED discovery failed for %s: %s", self._host, e)
            return {"error": str(e)}
        except Exception as e:
            _LOGGER.error("WLED discovery unexpected error for %s: %s", self._host, e)
            return {"error": str(e)}
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.
        
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
