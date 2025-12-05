from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hypercorn.asyncio import serve
from hypercorn.config import Config

if TYPE_CHECKING:
    from hypercorn.typing import Framework
    from boneio.webui.app import BoneIOApp

from boneio.core.config import ConfigHelper
from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class WebServer:
    def __init__(
        self,
        config_file: str,
        config_helper: ConfigHelper,
        manager: Manager,
        port: int = 8080,
        auth: dict = {},
        logger: dict = {},
        debug_level: int = 0,
        initial_config: dict | None = None,
    ) -> None:
        """Initialize the web server.
        
        Args:
            initial_config: Pre-parsed config to populate cache (avoids slow first request)
        """
        self.config_file = config_file
        self.config_helper = config_helper
        self.manager = manager
        self.initial_config = initial_config
        self._shutdown_event = asyncio.Event()
        self._port = port

        # Get yaml config file path
        self._yaml_config_file = os.path.abspath(
            os.path.join(os.path.split(self.config_file)[0], "config.yaml")
        )

        # Set up JWT secret
        self.jwt_secret = self._get_jwt_secret_or_generate()
        self._auth_config = auth

        # Configure hypercorn with shared logging config
        self._hypercorn_config = Config()
        self._hypercorn_config.bind = [f"0.0.0.0:{port}"]
        self._hypercorn_config.use_reloader = False
        self._hypercorn_config.worker_class = "asyncio"

        # Configure Hypercorn's logging
        hypercorn_logger = logging.getLogger("hypercorn.error")
        hypercorn_logger.handlers = []  # Remove default handlers
        hypercorn_logger.propagate = True  # Use root logger's handlers

        # Configure access log
        hypercorn_access_logger = logging.getLogger("hypercorn.access")
        hypercorn_access_logger.handlers = []  # Remove default handlers
        hypercorn_access_logger.propagate = True  # Use root logger's handlers

        self._hypercorn_config.accesslog = hypercorn_access_logger
        self._hypercorn_config.errorlog = hypercorn_logger

        # Reduce timeouts for faster shutdown
        self._hypercorn_config.graceful_timeout = 2.0  # Wait max 2s for connections to close
        self._hypercorn_config.keep_alive_timeout = 2  # Keep-alive timeout
        self._hypercorn_config.websocket_ping_interval = 20  # Ping interval (default is None)
        # self._server = hypercorn.asyncio.serve(self.app, self._hypercorn_config)
        # Override the server's install_signal_handlers to prevent it from handling signals
        # self._server.install_signal_handlers = lambda: None
        self._server_running = False
        # self.manager.event_bus.add_sigterm_listener(self.stop_webserver)

    def _get_jwt_secret_or_generate(self):
        config_dir = Path(self._yaml_config_file).parent
        jwt_secret_file = config_dir / "jwt_secret"

        try:
            if jwt_secret_file.exists():
                # Read existing secret
                with open(jwt_secret_file) as f:
                    jwt_secret = f.read().strip()
                    if jwt_secret:  # Verify it's not empty
                        return jwt_secret

            # Generate new secret if file doesn't exist or is empty
            jwt_secret = secrets.token_hex(32)  # 256-bit random secret

            # Save the secret
            with open(jwt_secret_file, "w") as f:
                f.write(jwt_secret)

            # Secure the file permissions (read/write only for owner)
            os.chmod(jwt_secret_file, 0o600)

        except Exception as e:
            # If we can't persist the secret, generate a temporary one
            _LOGGER.error(f"Failed to handle JWT secret file: {e}")
            jwt_secret = secrets.token_hex(32)
        return jwt_secret

    async def start_webserver(self) -> None:
        """Start the web server."""
        _LOGGER.info("Starting HYPERCORN web server...")
        self._server_running = True

        async def shutdown_trigger() -> None:
            """Shutdown trigger for hypercorn"""
            _LOGGER.debug("Shutdown trigger waiting for event...")
            await self._shutdown_event.wait()
            _LOGGER.info("Shutdown trigger activated, Hypercorn will now shutdown gracefully")

        from boneio.webui.app import init_app

        # Initialize FastAPI app
        self.app = init_app(
            manager=self.manager,
            yaml_config_file=self._yaml_config_file,
            auth_config=self._auth_config,
            jwt_secret=self.jwt_secret,
            config_helper=self.config_helper,
            web_server=self,
            initial_config=self.initial_config,
        )

        server_task = asyncio.create_task(
            serve(app=cast("Framework", self.app), config=self._hypercorn_config, shutdown_trigger=shutdown_trigger)
        )
        self.manager.set_web_server_status(status=True, bind=self._port)
        try:
            _LOGGER.debug("Waiting for Hypercorn server to complete...")
            await server_task
            _LOGGER.info("Hypercorn server task completed")
        except asyncio.CancelledError:
            _LOGGER.info("Hypercorn server task cancelled")
            pass  # Expected due to cancellation

    async def trigger_shutdown(self) -> None:
        """Signal the web server to start its shutdown sequence."""
        _LOGGER.info("Web server shutdown triggered.")
        self._shutdown_event.set()

    async def _wait_shutdown(self):
        await self._shutdown_event.wait()
        _LOGGER.info("Shutdown signal received")

    async def stop_webserver(self) -> None:
        """Stop the web server."""
        if not self._server_running:
            return
        _LOGGER.info("Shutting down HYPERCORN web server...")
        self._server_running = False
        self._shutdown_event.set()

    async def stop_webserver2(self) -> None:
        """Stop the web server."""
        _LOGGER.info("Shutting down HYPERCORN web server...")
        self._server_running = False
        # await self.app.shutdown_handler()
