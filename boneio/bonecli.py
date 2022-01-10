import asyncio
import logging
import os
from functools import wraps

import click
from colorlog import ColoredFormatter

from boneio.const import (
    ADC,
    ENABLED,
    HA_DISCOVERY,
    HOST,
    INPUT,
    LM75,
    MCP23017,
    MCP_TEMP_9808,
    MODBUS,
    MQTT,
    OLED,
    OUTPUT,
    PAHO,
    PASSWORD,
    PYMODBUS,
    SDM630,
    TOPIC_PREFIX,
    USERNAME,
)
from boneio.helper import CustomValidator, load_yaml_file
from boneio.manager import Manager
from boneio.mqtt_client import MQTTClient
from boneio.version import __version__

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

MAINPATH = os.path.join(os.path.dirname(__file__))


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.group(no_args_is_help=True)
@click.pass_context
@click.version_option(__version__)
@coro
async def cli(ctx):
    """A tool to run commands."""
    pass


_options = [
    click.option(
        "-d",
        "--debug",
        default=False,
        count=True,
        help="Set Debug mode. Single debug is debug of this lib. Second d is debug of aioxmpp as well.",
    ),
    click.option(
        "--config",
        "-c",
        type=str,
        default="./config.yaml",
        help="Config yaml file. Default to ./config.yaml",
    ),
    click.option(
        "--mqttpassword",
        envvar="MQTTPASS",
        type=str,
        help="Mqtt password. To use as ENV named MQTTPASS",
    ),
]


@cli.command()
@add_options(_options)
@click.pass_context
@coro
async def run(ctx, debug: int, config: str, mqttpassword: str = ""):
    """Run BoneIO."""
    _LOGGER.info("BoneIO starting.")
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
    schema = load_yaml_file(os.path.join(MAINPATH, "schema.yaml"))
    v = CustomValidator(schema, purge_unknown=True)
    config_yaml = load_yaml_file(config)
    if not config_yaml:
        _LOGGER.info("Missing file.")
        return
    _config = v.normalized(config_yaml)
    _LOGGER.info("Connecting to MQTT.")
    client = MQTTClient(
        host=_config[MQTT][HOST],
        username=_config[MQTT].get(USERNAME),
        password=_config[MQTT].get(PASSWORD, mqttpassword),
    )

    manager = Manager(
        send_message=client.send_message,
        topic_prefix=_config[MQTT][TOPIC_PREFIX],
        relay_pins=_config.get(OUTPUT, []),
        input_pins=_config.get(INPUT, []),
        ha_discovery=_config[MQTT][HA_DISCOVERY][ENABLED],
        ha_discovery_prefix=_config[MQTT][HA_DISCOVERY][TOPIC_PREFIX],
        sensors={
            LM75: _config.get(LM75),
            MCP_TEMP_9808: _config.get(MCP_TEMP_9808),
            SDM630: _config.get(SDM630),
        },
        mcp23017=_config.get(MCP23017, []),
        modbus=_config.get(MODBUS),
        oled=_config.get(OLED),
        adc_list=_config.get(ADC, []),
    )
    tasks = set()
    tasks.update(manager.get_tasks())
    tasks.add(client.start_client(manager))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(cli())
