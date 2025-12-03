"""Bonecli script."""

from __future__ import annotations

import logging
import os

os.environ["W1THERMSENSOR_NO_KERNEL_MODULE"] = "1"

import argparse
import asyncio
import sys

from yaml import MarkedYAMLError

from boneio.const import ACTION
from boneio.core.config import load_config_from_file
from boneio.core.events import GracefulExit
from boneio.core.utils.logger import configure_logger, setup_logging
from boneio.exceptions import (
    ConfigurationException,
    RestartRequestException,
)
# Lazy import modbus CLI to save ~0.35s on startup for 'run' command
# from boneio.modbus.cli import async_run_modbus_get, async_run_modbus_search, async_run_modbus_set
# from boneio.modbus.client import VALUE_TYPES
from boneio.runner import async_run
from boneio.version import __version__

TASK_CANCELATION_TIMEOUT = 1

_LOGGER = logging.getLogger(__name__)


def get_arguments() -> argparse.Namespace:
    """Get parsed passed in arguments."""

    parser = argparse.ArgumentParser(
        description="boneIO app for BeagleBone Black.",
    )
    subparsers = parser.add_subparsers(dest=ACTION, required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "--debug",
        "-d",
        action="count",
        help="Start boneIO in debug mode",
        default=0,
    )
    run_parser.add_argument(
        "-c",
        "--config",
        metavar="path_to_config_dir",
        default="./config.yaml",
        help="File which contains boneIO configuration",
    )
    run_parser.add_argument(
        "--mqttusername",
        help="Mqtt username to use if you don't want provide in file.",
    )
    run_parser.add_argument(
        "--mqttpassword",
        help="Mqtt password to use if you don't want provide in file.",
    )
    modbus_parser = subparsers.add_parser("modbus")
    modbus_parser.add_argument(
        "--debug",
        "-d",
        action="count",
        help="Start boneIO in debug mode",
        default=0,
    )
    modbus_parser.add_argument(
        "--uart",
        type=str,
        choices=["uart1", "uart4"],
        help="Choose UART",
        required=True,
    )
    modbus_parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),
        required=False,
        default=1,
        help="Current device address (hex or integer)",
    )
    modbus_parser.add_argument(
        "--baudrate",
        type=int,
        choices=[1200, 2400, 4800, 9600, 14400, 19200],
        required=True,
        help="Current baudrate",
    )

    modbus_parser.add_argument(
        "--bytesize",
        type=int,
        required=False,
        default=8,
        help="Bytesize",
    )

    modbus_parser.add_argument(
        "--stopbits",
        type=int,
        required=False,
        default=1,
        help="stopbits",
    )

    modbus_parser.add_argument(
        "--parity",
        type=str,
        choices=["P", "E", "N"],
        default="N",
        required=False,
        help="Parity",
    )

    modbus_sub_parser = modbus_parser.add_subparsers(
        dest="modbus_action", required=True
    )
    set_modbus_parser = modbus_sub_parser.add_parser("set")
    set_modbus_parser.add_argument(
        "--custom-value",
        type=int,
        help="Set Custom value",
    )
    set_modbus_parser.add_argument(
        "--custom-register-address",
        type=int,
        help="Register address for custom value",
    )
    set_modbus_parser.add_argument(
        "--device",
        type=str,
        choices=["cwt", "r4dcb08", "liquid-sensor", "sht20", "sht30", "custom"],
        help="Choose device to set modbus address/baudrate. For custom you must provide --custom-value and --custom-register-address",
        required=True,
    )
    set_modbus_parser_group = set_modbus_parser.add_mutually_exclusive_group()
    set_modbus_parser_group.add_argument(
        "--new-address",
        type=lambda x: int(x, 0),
        help="Set new address (hex or integer / 1 - 253/)",
    )

    set_modbus_parser_group.add_argument(
        "--new-baudrate",
        type=int,
        choices=[1200, 2400, 4800, 9600, 19200],
        help="Choose new baudrate to set. CWT doesn't work on 1200.",
    )

    get_modbus_parser = modbus_sub_parser.add_parser("get")
    register_group = get_modbus_parser.add_mutually_exclusive_group(required=True)
    register_group.add_argument(
        "--register-address",
        type=int,
        help="Single register address to read",
    )
    register_group.add_argument(
        "--register-range",
        type=str,
        help="Register address range in format 'start-stop' (e.g., '1-230')",
    )
    get_modbus_parser.add_argument(
        "--register-type",
        type=str,
        choices=["input", "holding"],
        help="Register type",
        required=True,
    )
    # Lazy import VALUE_TYPES only for modbus commands
    from boneio.modbus.client import VALUE_TYPES
    
    get_modbus_parser.add_argument(
        "--value-type",
        type=str,
        choices=VALUE_TYPES.keys(),
        help="Value types",
        required=True,
    )
    search_modbus_parser = modbus_sub_parser.add_parser(
        name="search",
        help="Search for device. Iterate over every address 1-253 with provided register address",
    )
    search_modbus_parser.add_argument(
        "--register-address",
        type=int,
        help="Register address",
        required=True,
    )
    search_modbus_parser.add_argument(
        "--register-type",
        type=str,
        choices=["input", "holding"],
        help="Register type",
        required=True,
    )
    parser.add_argument("--version", action="version", version=__version__)
    arguments = parser.parse_args()

    return arguments


def run(
    config: str, debug: int, mqttusername: str = "", mqttpassword: str = ""
) -> int:
    """Run BoneIO."""
    setup_logging(debug_level=debug)
    _LOGGER.info("BoneIO %s starting.", __version__)
    try:
        _config = load_config_from_file(config_file=config)
        if not _config:
            _LOGGER.error("Config not loaded. Exiting.")
            return 1
        configure_logger(log_config=_config.get("logger") or {}, debug=debug)
        ret = asyncio.run(
            async_run(
                config=_config,
                config_file=config,
                mqttusername=mqttusername,
                mqttpassword=mqttpassword,
                debug=debug,
            ),
        )
        _LOGGER.info("BoneIO %s exiting.", __version__)
        return ret
    except KeyboardInterrupt:
        return 0
    except GracefulExit as err:
        _LOGGER.info("Message: %s", err)
        return 0
    except (ConfigurationException, MarkedYAMLError) as err:
        _LOGGER.error("Failed to load config. %s Exiting.", err)
        return 1


def run_modbus_command(
    args: argparse.Namespace,
) -> int:
    """Run BoneIO."""
    # Lazy import modbus CLI only when needed
    from boneio.modbus.cli import (
        async_run_modbus_get,
        async_run_modbus_search,
        async_run_modbus_set,
    )
    
    setup_logging(debug_level=args.debug)
    _LOGGER.info("BoneIO %s starting.", __version__)
    try:
        configure_logger(log_config={}, debug=args.debug)
        ret = 0
        if args.modbus_action == "set":
            ret = asyncio.run(
                async_run_modbus_set(
                    device=args.device,
                    uart=args.uart,
                    address=args.address,
                    baudrate=args.baudrate,
                    parity=args.parity,
                    bytesize=args.bytesize,
                    stopbits=args.stopbits,
                    new_baudrate=args.new_baudrate,
                    new_address=args.new_address,
                    custom_address=args.custom_register_address,
                    custom_value=args.custom_value,
                ),
            )
        elif args.modbus_action == "get":
            ret = asyncio.run(
                async_run_modbus_get(
                    uart=args.uart,
                    device_address=args.address,
                    baudrate=args.baudrate,
                    register_address=args.register_address,
                    register_type=args.register_type,
                    parity=args.parity,
                    bytesize=args.bytesize,
                    stopbits=args.stopbits,
                    value_type=args.value_type,
                    register_range=args.register_range,
                ),
            )
        else:
            ret = asyncio.run(
                async_run_modbus_search(
                    uart=args.uart,
                    baudrate=args.baudrate,
                    register_address=args.register_address,
                    register_type=args.register_type,
                    stopbits=args.stopbits,
                    bytesize=args.bytesize,
                    parity=args.parity,
                ),
            )
        # Ensure we always return an int
        return ret if isinstance(ret, int) else 0
    except (RestartRequestException, GracefulExit) as err:
        _LOGGER.info(err)
        return 0
    except (ConfigurationException, MarkedYAMLError) as err:
        _LOGGER.error("Failed to load config. %s Exiting.", err)
        return 1


def main() -> int:
    """Start boneIO."""

    args = get_arguments()
    debug = args.debug

    exit_code = 0
    if args.action == "run":
        exit_code = run(
            config=args.config,
            mqttusername=args.mqttusername,
            mqttpassword=args.mqttpassword,
            debug=debug,
        )
    elif args.action == "modbus":
        _LOGGER.info("BoneIO Modbus helper %s .", __version__)
        exit_code = run_modbus_command(
            args=args,
        )

    if exit_code == 0:
        _LOGGER.info("Exiting with exit code %s", exit_code)
    else:
        _LOGGER.error("Exiting with exit code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
