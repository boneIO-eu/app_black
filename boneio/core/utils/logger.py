import logging
import os
import sys
import threading
from logging import Formatter
from typing import IO
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


#: The one logger pymodbus 3.x writes through (its ``Log`` class).
PYMODBUS_INTERNAL_LOGGER = "pymodbus.logging"


class _PymodbusNoResponseFilter(logging.Filter):
    """Drop pymodbus's own report of a device that did not answer.

    pymodbus logs "No response received after N retries" at ERROR and then
    raises ModbusIOException, which boneio.modbus.client catches and reports
    itself — with the device and register, and rate-limited, WARNING once and
    INFO after. Without this the same timeout is logged twice per poll and the
    pymodbus copy stays at ERROR forever. Everything else pymodbus logs is
    left alone.

    pymodbus replaces the second identical message in a row with
    "Repeating....", so that is dropped too, but only straight after a dropped
    no-response line; after anything else it is the only trace of a repeat.
    """

    def __init__(self) -> None:
        """Initialize the filter."""
        super().__init__()
        self._dropped_last = False

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False for the duplicated no-response message."""
        msg = str(record.msg)
        if msg.startswith("No response received after"):
            self._dropped_last = True
            return False
        # pymodbus appends the last frames it sent to an error, so the marker
        # is a prefix, not the whole message.
        if msg.startswith("Repeating....") and self._dropped_last:
            return False
        self._dropped_last = False
        return True


_PYMODBUS_NO_RESPONSE_FILTER = _PymodbusNoResponseFilter()


def _configure_pymodbus_filter(log_config: dict, debug: int) -> None:
    """Install the no-response filter unless the operator asked for pymodbus.

    An explicit ``logger.logs`` entry for pymodbus, or ``-dd``, means somebody
    wants to see what pymodbus says, so the filter stays off. Removed first
    because this runs again on every config reload.
    """
    internal = logging.getLogger(PYMODBUS_INTERNAL_LOGGER)
    internal.removeFilter(_PYMODBUS_NO_RESPONSE_FILTER)
    configured = (log_config or {}).get("logs") or {}
    explicit = any(
        name == PYMODBUS or name.startswith(PYMODBUS + ".") for name in configured
    )
    if not explicit and debug <= 1:
        internal.addFilter(_PYMODBUS_NO_RESPONSE_FILTER)


def configure_logger(log_config: dict, debug: int) -> None:
    """Configure logger based on config yaml."""
    _configure_pymodbus_filter(log_config, debug)

    def debug_logger():
        # Always suppress hypercorn access logs (they spam INFO level)
        logging.getLogger("hypercorn.access").setLevel(logging.WARNING)
        
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

def is_journal_stream(stream: IO | None) -> bool:
    """Whether ``stream`` is the one systemd connected to the journal.

    systemd sets JOURNAL_STREAM to "device:inode" of the socket it gave the
    service as stdout/stderr (systemd.exec(5)). The variable alone is not
    enough: a child of boneIO inherits it with its stderr piped elsewhere, and
    there a level prefix would be noise in somebody else's output.
    """
    value = os.environ.get("JOURNAL_STREAM")
    if not value or stream is None:
        return False
    try:
        device, inode = (int(part) for part in value.split(":"))
        st = os.fstat(stream.fileno())
    except (ValueError, OSError, AttributeError):
        # io.UnsupportedOperation (no real fd, e.g. pytest's capture) is
        # both an OSError and a ValueError.
        return False
    return (st.st_dev, st.st_ino) == (device, inode)


def syslog_priority(levelno: int) -> int:
    """Map a logging level to the syslog priority journald files it under."""
    if levelno >= logging.CRITICAL:
        return 2
    if levelno >= logging.ERROR:
        return 3
    if levelno >= logging.WARNING:
        return 4
    if levelno >= logging.INFO:
        return 6
    return 7


class JournalLevelFormatter(Formatter):
    """Prefix every line of a record with its level for journald.

    journald reads what a service writes to stdout/stderr line by line and
    files each line at PRIORITY=6 unless it starts with "<N>" (the sd-daemon
    prefix; SyslogLevelPrefix= is on by default). boneIO wrote plain text, so
    its warnings, errors and tracebacks were all "info" to the journal - and
    never reached the serial console, which since 1.6.25 shows warning and
    above. A traceback is one record but many lines, and journald makes each
    line a separate entry, so every line gets the prefix, not just the first.
    journald strips it again; the stored message is unchanged.

    Only the formatted text is prefixed. The record, including the traceback
    text the base class caches on it, is left alone for the other handlers.
    """

    def __init__(self, inner: Formatter) -> None:
        """Wrap ``inner``, which does the actual formatting."""
        super().__init__()
        self._inner = inner

    def format(self, record: logging.LogRecord) -> str:
        """Format with the inner formatter and prefix each line."""
        prefix = f"<{syslog_priority(record.levelno)}>"
        text = self._inner.format(record)
        return "\n".join(prefix + line for line in text.split("\n"))


def get_log_formatter(color: bool = True, stream: IO | None = None) -> Formatter:
    """Get log formatter with optional color support.

    Args:
        color: Colour the output by level.
        stream: Stream the handler writes to. When it is the journal, the
            formatter tells journald each line's level and drops the colours:
            journald keeps a message with escape codes as a byte array rather
            than text, the level now travels in PRIORITY (journalctl colours
            by it), and the prefix has to be the first thing on the line.
    """
    if is_journal_stream(stream):
        return JournalLevelFormatter(
            Formatter("%(levelname)s (%(threadName)s) [%(name)s] %(message)s")
        )

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


def install_excepthooks() -> None:
    """Send exceptions nobody caught through logging instead of bare stderr.

    Python prints an uncaught exception straight to stderr, which under
    systemd means one journal entry per traceback line, all at "info" - so
    the one message that explains why boneIO died never reached the serial
    console. Through logging it gets the level prefix like everything else.
    An exception in the main thread ends the process and is CRITICAL; one
    that ends another thread is ERROR, since boneIO carries on without it.
    Ctrl+C keeps Python's usual short output, and a thread ending with
    SystemExit stays silent, as it is by default.
    """
    logger = logging.getLogger("boneio")

    def _log_uncaught(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        try:
            logger.critical(
                "Uncaught exception, boneIO is exiting",
                exc_info=(exc_type, exc_value, exc_traceback),
            )
        except Exception:  # noqa: BLE001 - the traceback must come out somehow
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _log_uncaught_in_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        try:
            logger.error(
                "Uncaught exception in thread %s",
                args.thread.name if args.thread is not None else "unknown",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        except Exception:  # noqa: BLE001
            threading.__excepthook__(args)

    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread


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
    
    # Create formatter for console handler. basicConfig's handler writes to
    # stderr; the formatter needs to know whether that is the journal.
    root_handler = logging.getLogger().handlers[0]
    console_formatter = get_log_formatter(
        color=True, stream=getattr(root_handler, "stream", None)
    )
    console_handler.setFormatter(console_formatter)
    
    # Add console handler to root logger
    root_handler.setFormatter(console_formatter)
    install_excepthooks()
    
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