#!/usr/bin/env python3
"""Monitor multi-click events on multiple BeagleBone Black GPIO inputs."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import gpiod
import yaml
from gpiod import LineSettings
from gpiod.line import Bias, Direction, Edge
from multiclick_detector import MultiClickDetector

CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "boneio" / "boards" / "0.8" / "input.yaml"
)
CLICK_TIMEOUT_SECONDS = float(os.getenv("BONEIO_CLICK_TIMEOUT", 0.4))
HOLD_THRESHOLD_SECONDS = float(os.getenv("BONEIO_HOLD_THRESHOLD", 1.0))
DEBOUNCE_MS = float(os.getenv("BONEIO_DEBOUNCE_MS", 7.0))
LOG_LEVEL = os.getenv("BONEIO_MULTICLICK_LOG_LEVEL", "INFO")


_LOGGER = logging.getLogger(__name__)


@dataclass
class InputDefinition:
    """Describe a single GPIO input defined in YAML configuration."""

    name: str
    pin: str
    chip: int
    line: int
    bias: Bias


_BBB_HEADER_PATTERN = re.compile(r"^(P8|P9)_(\d{1,2})$", re.IGNORECASE)


def load_input_definitions(config_path: Path) -> List[InputDefinition]:
    """Load GPIO input definitions from the provided YAML file."""

    if not config_path.exists():
        _LOGGER.error("Configuration file %s not found.", config_path)
        return []

    content = config_path.read_text(encoding="utf-8")
    if not content.strip():
        _LOGGER.error("Configuration file %s is empty.", config_path)
        return []

    data = yaml.safe_load(content) or {}
    mapping = data.get("input_mapping", {})
    if not isinstance(mapping, dict) or not mapping:
        _LOGGER.error("Configuration file %s lacks 'input_mapping' entries.", config_path)
        return []

    definitions: List[InputDefinition] = []
    for name, details in mapping.items():
        if not isinstance(details, dict):
            _LOGGER.warning("Skipping malformed entry '%s'.", name)
            continue

        pin = str(details.get("pin", "")).strip()
        if not pin:
            _LOGGER.warning("Skipping '%s' due to missing pin.", name)
            continue

        try:
            chip = int(details["gpiochip"])
            line = int(details["line"])
        except (KeyError, TypeError, ValueError) as exc:
            _LOGGER.warning(
                "Skipping '%s' due to invalid gpiochip/line data: %s",
                name,
                exc,
            )
            continue

        definitions.append(
            InputDefinition(name=name, pin=pin, chip=chip, line=line, bias=Bias.AS_IS)
        )

    return definitions


async def monitor_lines(
    definitions: Sequence[InputDefinition],
    click_timeout: float,
    hold_threshold: float,
    debounce_ms: float,
    shutdown_event: asyncio.Event,
) -> None:
    """Watch a group of GPIO inputs and detect multi-click sequences."""
    if not definitions:
        _LOGGER.error("No input definitions provided.")
        return

    loop = asyncio.get_running_loop()
    grouped_inputs: Dict[int, List[InputDefinition]] = defaultdict(list)
    for definition in definitions:
        grouped_inputs[definition.chip].append(definition)

    global_aliases: Dict[Tuple[int, int], str] = {}
    requests: Dict[int, gpiod.LineRequest] = {}
    file_descriptors: List[int] = []

    detector = MultiClickDetector(
        loop=loop,
        line_aliases=global_aliases,
        click_timeout=click_timeout,
        hold_threshold=hold_threshold,
        debounce_ms=debounce_ms,
    )

    def handle_gpiod_events(chip: int, request: gpiod.LineRequest) -> None:
        """Callback to read events from a specific chip."""
        for event in request.read_edge_events():
            key = (chip, event.line_offset)
            detector.handle_event(key, event)

    try:
        # Konfiguracja i requestowanie linii
        for chip, chip_definitions in grouped_inputs.items():
            config: dict[Iterable[int | str] | int | str, LineSettings | None] = {}
            alias_map: Dict[Tuple[int, int], str] = {}
            for definition in chip_definitions:
                settings_kwargs = {
                    "direction": Direction.INPUT,
                    "edge_detection": Edge.BOTH,
                    "bias": definition.bias,
                }
                if debounce_ms > 0:
                    settings_kwargs["debounce_period"] = timedelta(milliseconds=debounce_ms)

                config[(definition.line,)] = LineSettings(**settings_kwargs)
                alias = f"{definition.name} ({definition.pin})"
                key = (chip, definition.line)
                alias_map[key] = alias
                global_aliases[key] = alias

            consumer = f"boneio-multiclick-chip{chip}"
            request = gpiod.request_lines(
                f"/dev/gpiochip{chip}", consumer=consumer, config=config
            )
            requests[chip] = request
            
            summary = ", ".join(
                f"{alias} (line {line})" for (_, line), alias in alias_map.items()
            )
            _LOGGER.info("Monitoring /dev/gpiochip%s on: %s", chip, summary)
        
        # Rejestracja czytników w pętli asyncio
        for chip, request in requests.items():
            # <--- JEDYNA ZMIANA: Używamy .fileno()
            fd = request.fileno()
            file_descriptors.append(fd)
            loop.add_reader(fd, handle_gpiod_events, chip, request)

        _LOGGER.info("Event listeners started. Press Ctrl+C to exit.")
        await shutdown_event.wait()

    finally:
        _LOGGER.info("Cleaning up GPIO resources...")
        for fd in file_descriptors:
            loop.remove_reader(fd)
        for request in requests.values():
            request.release()

def configure_logging(log_level: str) -> None:
    """Configure the logging subsystem."""

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    """Script entry-point."""

    configure_logging(LOG_LEVEL)

    _LOGGER.info("=== Configuration ===")
    _LOGGER.info("CLICK_TIMEOUT: %.3fs", CLICK_TIMEOUT_SECONDS)
    _LOGGER.info("HOLD_THRESHOLD: %.3fs", HOLD_THRESHOLD_SECONDS)
    _LOGGER.info("DEBOUNCE: %.1fms (hardware max 7ms + software)", DEBOUNCE_MS)
    _LOGGER.info("====================")

    definitions = load_input_definitions(CONFIG_PATH)
    if not definitions:
        _LOGGER.error("No GPIO inputs loaded. Exiting.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        """Handle shutdown signals gracefully."""
        _LOGGER.info("Received shutdown signal.")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            _LOGGER.debug("Signal handler not supported for %s", sig)

    try:
        loop.run_until_complete(
            monitor_lines(
                definitions=definitions,
                click_timeout=CLICK_TIMEOUT_SECONDS,
                hold_threshold=HOLD_THRESHOLD_SECONDS,
                debounce_ms=DEBOUNCE_MS,
                shutdown_event=shutdown_event,
            )
        )
    except KeyboardInterrupt:
        _LOGGER.info("Stopping because of keyboard interrupt.")
    finally:
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    main()
