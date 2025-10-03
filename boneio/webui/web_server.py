from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path

from hypercorn.asyncio import serve
from hypercorn.config import Config

from boneio.helper.config import ConfigHelper
from boneio.manager import Manager
from boneio.webui.app import BoneIOApp, init_app

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
    ) -> None:
        """Initialize the web server."""
        self.config_file = config_file
        self.config_helper = config_helper
        self.manager = manager
        self._shutdown_event = asyncio.Event()
        self._port = port

        # Get yaml config file path
        self._yaml_config_file = os.path.abspath(
            os.path.join(os.path.split(self.config_file)[0], "config.yaml")
        )

        # Set up JWT secret
        self.jwt_secret = self._get_jwt_secret_or_generate()

        # Initialize FastAPI app
        self.app: BoneIOApp = init_app(
            manager=self.manager,
            yaml_config_file=self._yaml_config_file,
            auth_config=auth,
            jwt_secret=self.jwt_secret,
            config_helper=self.config_helper,
            web_server=self,
        )

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

        self._hypercorn_config.graceful_timeout = 5.0
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
            await self._shutdown_event.wait()

        server_task = asyncio.create_task(
            serve(self.app, self._hypercorn_config, shutdown_trigger=shutdown_trigger)
        )
        self.manager.set_web_server_status(status=True, bind=self._port)
        try:
            await server_task
        except asyncio.CancelledError:
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
