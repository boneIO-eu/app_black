import logging

from boneio.const import PAHO, PYMODBUS
from boneio.version import __version__

_LOGGER = logging.getLogger(__name__)
_nameToLevel = {
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.FATAL,
    "ERROR": logging.ERROR,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def configure_logger(log_config: dict, debug: int) -> None:
    """Configure logger based on config yaml."""

    def debug_logger():
        if debug == 0:
            logging.getLogger().setLevel(logging.INFO)
        if debug > 0:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger(PAHO).setLevel(logging.WARN)
            logging.getLogger(PYMODBUS).setLevel(logging.WARN)
            logging.getLogger("pymodbus.client").setLevel(logging.WARN)
            _LOGGER.info("Debug mode active")
            _LOGGER.debug(f"Lib version is {__version__}")
        if debug > 1:
            logging.getLogger(PAHO).setLevel(logging.DEBUG)
            logging.getLogger(PYMODBUS).setLevel(logging.DEBUG)
            logging.getLogger("pymodbus.client").setLevel(logging.DEBUG)

    if not log_config:
        debug_logger()
        return
    default = log_config.get("default", "").upper()
    if default in _nameToLevel:
        _LOGGER.info("Setting default log level to %s", default)
        logging.getLogger().setLevel(_nameToLevel[default])
        if debug == 0:
            debug = -1
    for k, v in log_config.get("logs", {}).items():
        logger = logging.getLogger(k)
        val = v.upper()
        if val in _nameToLevel and logger:
            _LOGGER.info("Setting %s log level to %s", k, val)
            logger.setLevel(_nameToLevel[val])
    debug_logger()
