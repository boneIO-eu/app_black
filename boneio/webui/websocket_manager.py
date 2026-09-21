import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

import jwt
from jwt import PyJWTError as JWTError
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from boneio.models.events import Event

_LOGGER = logging.getLogger(__name__)

# JWT settings
JWT_ALGORITHM = "HS256"

# How long a single frame may take to reach one client before that client is
# treated as gone. A socket whose peer stopped being routable does not raise —
# the kernel buffer fills and the write waits, for as long as TCP keeps
# retrying. Every entity event on this device is dispatched by one worker task
# that awaits this broadcast, so an unbounded wait here stops inputs, outputs,
# covers and sensors until the service is restarted, while the click detector
# upstream keeps logging clicks that no longer do anything. A frame of a few
# hundred bytes reaches any working client in well under a second.
WS_SEND_TIMEOUT = 5.0


class WebSocketDisconnectWithMessage(WebSocketDisconnect):
    def __init__(self, message):
        super().__init__()
        self.message = message


class WebSocketManager:
    def __init__(
        self,
        jwt_secret: str | None = None,
        auth_required: bool | Callable[[], bool] = False,
    ):
        """Track the open sockets and decide who may open one.

        Args:
            jwt_secret: Secret the connection tokens are signed with.
            auth_required: Whether a token is needed — a callable when the
                answer can change while the process runs, which it can: a
                device boots with no account and gains one the moment somebody
                finishes the first-run wizard.
        """
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._closing = False
        self._cleanup_tasks: list[asyncio.Task] = []
        self._jwt_secret = jwt_secret
        self._auth_required = auth_required

    @property
    def auth_required(self) -> bool:
        """Whether a connection needs a token right now.

        Asked per connection rather than held from startup. Held, it made the
        socket unusable for the whole life of the process on a device that was
        claimed while running: the client learns from /api/init that auth is
        required and offers its token as a subprotocol, the server still
        believes the device is unclaimed and accepts without agreeing to one,
        and the browser fails a handshake where it offered a subprotocol and
        got none back. Every reconnect does the same, so the panel comes up
        with no entities at all until the service is restarted.

        Returns:
            True when a token is required.
        """
        value = self._auth_required
        if callable(value):
            try:
                return bool(value())
            except Exception as err:  # noqa: BLE001
                # Fail closed: a socket carries every entity on the device.
                _LOGGER.error("Could not read the auth state, requiring a token: %s", err)
                return True
        return bool(value)

    async def _verify_token(self, websocket: WebSocket) -> bool:
        """Verify WebSocket token."""
        try:
            _LOGGER.debug("Verifying WebSocket token...")
            # Get token from Sec-WebSocket-Protocol header
            protocols = websocket.headers.get("sec-websocket-protocol", "").split(", ")
            token = None
            for protocol in protocols:
                if protocol.startswith("token."):
                    token = protocol[6:]  # Remove "token." prefix
                    break

            if not token:
                _LOGGER.debug("No authentication token provided")
                return False

            # Verify the JWT token
            try:
                payload = jwt.decode(token, self._jwt_secret or "", algorithms=[JWT_ALGORITHM])
                # Check if token has expired
                exp = payload.get("exp")
                if not exp or datetime.fromtimestamp(exp, tz=UTC) < datetime.now(UTC):
                    _LOGGER.debug("Token has expired")
                    return False

                _LOGGER.debug("WebSocket token verified successfully")
                return True

            except JWTError as e:
                _LOGGER.debug(f"Invalid token: {e}")
                return False
        except Exception as e:
            _LOGGER.error(f"WebSocket authentication error: {type(e).__name__} - {e}")
            return False

    async def connect(self, websocket: WebSocket) -> bool:
        """Handle WebSocket connection with authentication."""
        if self._closing:
            return False

        try:
            if self.auth_required:
                if not await self._verify_token(websocket):
                    # Must accept before closing with custom code
                    await websocket.accept()
                    await websocket.close(code=4001, reason="Authentication failed")
                    return False
                # Accept with the token protocol as subprotocol
                protocols = websocket.headers.get("sec-websocket-protocol", "").split(", ")
                token_protocol = next((p for p in protocols if p.startswith("token.")), None)
                await websocket.accept(subprotocol=token_protocol)
            else:
                await websocket.accept()

            async with self._lock:
                self.active_connections.append(websocket)
                _LOGGER.debug("WebSocket connection accepted and added to active connections")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to establish WebSocket connection: {e}")
            with contextlib.suppress(Exception):
                await websocket.close(code=4000, reason="Connection failed")
            return False

    async def disconnect(self, websocket: WebSocket):
        """Remove a websocket from active connections and close it gracefully."""
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                if websocket.application_state == WebSocketState.CONNECTED:
                    try:
                        await websocket.close(code=1000)
                    except Exception as e:
                        _LOGGER.error(f"Error closing WebSocket: {e}")
        except ValueError:
            pass
        except Exception as e:
            _LOGGER.error(f"Error during WebSocket disconnect: {e}")

    async def close_all(self):
        """Close all active connections."""
        if self._closing:
            return

        self._closing = True
        _LOGGER.info("Closing all WebSocket connections...")

        for websocket in list(self.active_connections):
            with contextlib.suppress(Exception):
                await self.disconnect(websocket)

    async def _send_one(self, connection: WebSocket, payload: dict[str, Any], what: str) -> WebSocket | None:
        """Send one payload to one client.

        Args:
            connection: The client socket.
            payload: Already-serialisable dict.
            what: Label for the log line.

        Returns:
            The connection if it should be dropped, otherwise None.
        """
        try:
            async with asyncio.timeout(WS_SEND_TIMEOUT):
                await connection.send_json(payload)
        except WebSocketDisconnect:
            return connection
        except TimeoutError:
            # Not necessarily a slow client: a peer that stopped being routable
            # looks exactly like this, and waiting on it is what used to take
            # the whole event bus down.
            _LOGGER.warning(
                "WebSocket client took longer than %.0fs to accept a %s frame; "
                "dropping it.",
                WS_SEND_TIMEOUT,
                what,
            )
            return connection
        except asyncio.CancelledError:
            if self._closing:
                raise
            _LOGGER.warning("WebSocket send cancelled mid-frame; dropping the client.")
            return connection
        except Exception as err:  # noqa: BLE001 - one client must not stop the rest
            _LOGGER.error("Error sending %s to WebSocket: %s", what, err)
            return connection
        return None

    async def _fan_out(self, payload: dict[str, Any], what: str) -> None:
        """Send one payload to every client, bounded in time.

        Sends run concurrently, so a batch of unreachable clients costs one
        timeout rather than one each. The lock is held to take the list and
        again to clean up, never across the sends themselves — held across
        them, a single stuck client also blocked every other caller of this
        manager.

        Args:
            payload: Already-serialisable dict.
            what: Label for the log line.
        """
        async with self._lock:
            connections = self.active_connections[:]
        if not connections:
            return

        results = await asyncio.gather(
            *(self._send_one(c, payload, what) for c in connections)
        )
        dead = [c for c in results if c is not None]
        if not dead:
            return

        async with self._lock:
            for connection in dead:
                if connection in self.active_connections:
                    await self.disconnect(connection)

    async def broadcast_state(self, event: Event):
        if self._closing:
            return
        if not isinstance(event, Event):
            return

        await self._fan_out(event.model_dump(), "state")

    async def broadcast(self, data: dict[str, Any]):
        """Broadcast a raw dict message to all connected WebSocket clients.

        Args:
            data: Dictionary to send as JSON to all clients
        """
        if self._closing:
            return

        await self._fan_out(data, "broadcast")
