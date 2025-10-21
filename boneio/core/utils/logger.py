import logging
import os
from logging import Formatter
from logging.handlers import RotatingFileHandler

from colorlog import ColoredFormatter

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
            logging.getLogger("hypercorn.error").setLevel(logging.DEBUG)

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


"""Shared logging configuration for BoneIO."""


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

def get_log_level(level_name: str) -> int:
    """Convert string log level to logging constant."""
    return _nameToLevel.get(level_name.upper(), logging.INFO)

def is_running_under_systemd():
    """Check if the process is running under systemd."""
    return os.getenv('JOURNAL_STREAM') is not None

def get_log_formatter(color: bool = True) -> Formatter:
    """Get log formatter with optional color support."""
    # When running under systemd, omit timestamp since journald adds it
    if is_running_under_systemd():
        log_format = "%(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    else:
        log_format = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    
    date_format = "%Y-%m-%d %H:%M:%S"
    
    if color:
        colored_format = "%(log_color)s" + log_format + "%(reset)s"
        return ColoredFormatter(
            fmt=colored_format,
            datefmt=date_format,
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red",
            },
        )
    return Formatter(log_format, datefmt=date_format)


def setup_logging(debug_level: int = 0) -> None:
    """Setup logging configuration."""
    log_format = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Set up basic configuration for console output
    logging.basicConfig(
        level=logging.INFO if debug_level == 0 else logging.DEBUG,
        format=log_format,
        datefmt=date_format
    )
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if debug_level == 0 else logging.DEBUG)
    
    # Create formatter for console handler
    console_formatter = get_log_formatter(color=True)
    console_handler.setFormatter(console_formatter)
    
    # Add console handler to root logger
    logging.getLogger().handlers[0].setFormatter(console_formatter)
    
    # If debug level > 1, also log to file with rotation
    if debug_level > 1:
        # Get the config directory path
        # config_dir = os.path.dirname(os.path.abspath(os.environ.get("BONEIO_CONFIG", "/tmp")))
        new_config_dir = "/tmp"
        log_file = os.path.join(new_config_dir, "boneio.log")
        
        # Create rotating file handler (10MB max size, keep 3 backup files)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding='utf-8'
        )
        
        # Set formatter for file handler
        formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(formatter)
        
        # Set level for file handler
        file_handler.setLevel(logging.DEBUG)
        
        # Add handler to root logger
        logging.getLogger().addHandler(file_handler)
        
        logging.info("File logging enabled at: %s", log_file)