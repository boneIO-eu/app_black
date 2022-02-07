"""Bonecli script."""
import argparse
import asyncio
import logging
import os
import sys

from colorlog import ColoredFormatter

from boneio.const import ACTION, PAHO, PYMODBUS
from boneio.helper import load_config_from_file
from boneio.runner import async_run
from boneio.version import __version__

TASK_CANCELATION_TIMEOUT = 1

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
colorfmt = f"%(log_color)s{fmt}%(reset)s"
logging.getLogger().handlers[0].setFormatter(
    ColoredFormatter(
        colorfmt,
        datefmt=datefmt,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red",
        },
    )
)


def get_arguments() -> argparse.Namespace:
    """Get parsed passed in arguments."""

    parser = argparse.ArgumentParser(
        description="boneIO app for BeagleBone Black.",
    )
    parser.add_argument(ACTION, type=str, default="run")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "-c",
        "--config",
        metavar="path_to_config_dir",
        default="./config.yaml",
        help="File which contains boneIO configuration",
    )
    parser.add_argument(
        "--debug", "-d", action="count", help="Start boneIO in debug mode", default=0
    )
    parser.add_argument(
        "--mqttusername", help="Mqtt username to use if you don't want provide in file."
    )
    parser.add_argument(
        "--mqttpassword", help="Mqtt password to use if you don't want provide in file."
    )
    arguments = parser.parse_args()

    return arguments


def run(config: str, mqttusername: str = "", mqttpassword: str = ""):
    """Run BoneIO."""
    _LOGGER.info("BoneIO starting.")
    _config = load_config_from_file(config_file=config)
    if not _config:
        return
    return asyncio.run(
        async_run(
            config=_config,
            config_path=os.path.split(config),
            mqttusername=mqttusername,
            mqttpassword=mqttpassword,
        ),
    )


def main() -> int:
    """Start boneIO."""

    args = get_arguments()
    debug = args.debug
    if debug == 0:
        logging.getLogger().setLevel(logging.INFO)
    if debug > 0:
        logging.getLogger().setLevel(logging.DEBUG)
        _LOGGER.info("Debug mode active")
        _LOGGER.debug(f"Lib version is {__version__}")
    if debug > 1:
        logging.getLogger(PAHO).setLevel(logging.DEBUG)
        logging.getLogger(PYMODBUS).setLevel(logging.DEBUG)
        logging.getLogger("pymodbus.client").setLevel(logging.DEBUG)
    else:
        logging.getLogger(PAHO).setLevel(logging.WARN)
    exit_code = 0
    if args.action == "run":
        exit_code = run(
            config=args.config,
            mqttusername=args.mqttusername,
            mqttpassword=args.mqttpassword,
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
