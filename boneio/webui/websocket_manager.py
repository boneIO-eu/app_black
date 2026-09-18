import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

from jose import jwt
from jose.exceptions import JWTError
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from boneio.models.events import Event

_LOGGER = logging.getLogger(__name__)

# JWT settings
JWT_ALGORITHM = "HS256"


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

    async def broadcast_state(self, event: Event):
        if self._closing:
            return

        dead_connections = []
        async with self._lock:
            for connection in self.active_connections[:]:
                try:
                    if isinstance(event, Event):
                        await connection.send_json(event.model_dump())
                except WebSocketDisconnect:
                    dead_connections.append(connection)
                except Exception as e:
                    _LOGGER.error(f"Error sending message to WebSocket: {e}")
                    dead_connections.append(connection)

            # Clean up dead connections
            for dead in dead_connections:
                if dead in self.active_connections:
                    await self.disconnect(dead)

    async def broadcast(self, data: dict[str, Any]):
        """Broadcast a raw dict message to all connected WebSocket clients.

        Args:
            data: Dictionary to send as JSON to all clients
        """
        if self._closing:
            return

        dead_connections = []
        async with self._lock:
            for connection in self.active_connections[:]:
                try:
                    await connection.send_json(data)
                except WebSocketDisconnect:
                    dead_connections.append(connection)
                except Exception as e:
                    _LOGGER.error(f"Error broadcasting to WebSocket: {e}")
                    dead_connections.append(connection)

            # Clean up dead connections
            for dead in dead_connections:
                if dead in self.active_connections:
                    await self.disconnect(dead)
