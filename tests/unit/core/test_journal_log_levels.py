"""boneIO tells journald the level of every line it logs.

journald files each line a service writes to stdout/stderr at PRIORITY=6
unless it starts with "<N>". Without the prefix, warnings, errors and
tracebacks were all "info" and never reached the serial console, which shows
warning and above.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

import pytest

from boneio.core.utils import logger as boneio_logger
from boneio.core.utils.logger import (
    JournalLevelFormatter,
    get_log_formatter,
    install_excepthooks,
    is_journal_stream,
)


@pytest.fixture
def journal_file(tmp_path, monkeypatch):
    """A file standing in for the journal socket, with JOURNAL_STREAM pointing at it."""
    with open(tmp_path / "journal", "w") as stream:
        st = os.fstat(stream.fileno())
        monkeypatch.setenv("JOURNAL_STREAM", f"{st.st_dev}:{st.st_ino}")
        yield stream


@pytest.fixture
def other_file(tmp_path):
    with open(tmp_path / "other", "w") as stream:
        yield stream


def _record(level: int, msg: str, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("boneio.test", level, __file__, 1, msg, None, exc_info)


def _traceback() -> tuple:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        return sys.exc_info()


class TestJournalStream:
    def test_matches_the_stream_systemd_named(self, journal_file):
        assert is_journal_stream(journal_file) is True

    def test_a_different_stream_is_not_the_journal(self, journal_file, other_file):
        """A child with the variable inherited but stderr piped elsewhere."""
        assert is_journal_stream(other_file) is False

    def test_no_variable_no_journal(self, other_file, monkeypatch):
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
        assert is_journal_stream(other_file) is False

    @pytest.mark.parametrize("value", ["", "garbage", "1:2:3", "a:b"])
    def test_a_malformed_variable_is_not_the_journal(self, other_file, monkeypatch, value):
        monkeypatch.setenv("JOURNAL_STREAM", value)
        assert is_journal_stream(other_file) is False

    def test_a_stream_without_a_descriptor_is_not_the_journal(self, monkeypatch):
        import io

        monkeypatch.setenv("JOURNAL_STREAM", "1:2")
        assert is_journal_stream(io.StringIO()) is False
        assert is_journal_stream(None) is False


class TestJournalFormatter:
    @pytest.mark.parametrize(
        ("level", "priority"),
        [
            (logging.DEBUG, 7),
            (logging.INFO, 6),
            (logging.WARNING, 4),
            (logging.ERROR, 3),
            (logging.CRITICAL, 2),
        ],
    )
    def test_each_level_gets_its_priority(self, journal_file, level, priority):
        formatter = get_log_formatter(color=True, stream=journal_file)
        assert formatter.format(_record(level, "hello")).startswith(f"<{priority}>")

    def test_every_line_of_a_traceback_is_prefixed(self, journal_file):
        formatter = get_log_formatter(color=True, stream=journal_file)
        text = formatter.format(_record(logging.ERROR, "it broke\nsecond line", _traceback()))
        lines = text.split("\n")
        assert len(lines) > 3
        assert all(line.startswith("<3>") for line in lines)
        assert "Traceback (most recent call last):" in text
        assert lines[-1] == "<3>RuntimeError: boom"

    def test_no_colours_and_no_timestamp_in_the_journal(self, journal_file):
        formatter = get_log_formatter(color=True, stream=journal_file)
        text = formatter.format(_record(logging.WARNING, "hello"))
        assert "\x1b" not in text
        assert text == "<4>WARNING (MainThread) [boneio.test] hello"

    def test_the_record_is_left_alone_for_other_handlers(self, journal_file):
        """The -dd log file formats the same record; it must not see prefixes."""
        record = _record(logging.ERROR, "it broke", _traceback())
        get_log_formatter(stream=journal_file).format(record)
        plain = logging.Formatter("%(message)s").format(record)
        assert "<3>" not in plain
        assert record.getMessage() == "it broke"

    def test_a_terminal_is_unchanged(self, other_file, monkeypatch):
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
        formatter = get_log_formatter(color=True, stream=other_file)
        assert not isinstance(formatter, JournalLevelFormatter)
        text = formatter.format(_record(logging.WARNING, "hello"))
        assert not text.startswith("<")
        assert "\x1b[" in text  # still coloured, as before

    def test_without_a_stream_nothing_changes(self, journal_file):
        """Callers that do not say where they write keep the old formatter."""
        assert not isinstance(get_log_formatter(color=True), JournalLevelFormatter)


class TestExceptHooks:
    @pytest.fixture(autouse=True)
    def _restore_hooks(self, monkeypatch):
        monkeypatch.setattr(sys, "excepthook", sys.excepthook)
        monkeypatch.setattr(threading, "excepthook", threading.excepthook)

    def test_an_uncaught_exception_is_logged_as_critical(self, caplog):
        install_excepthooks()
        with caplog.at_level(logging.DEBUG, logger="boneio"):
            sys.excepthook(*_traceback())
        [record] = [r for r in caplog.records if r.name == "boneio"]
        assert record.levelno == logging.CRITICAL
        assert record.exc_info[0] is RuntimeError

    def test_ctrl_c_keeps_pythons_own_output(self, caplog, monkeypatch):
        seen = []
        monkeypatch.setattr(sys, "__excepthook__", lambda *a: seen.append(a[0]))
        install_excepthooks()
        with caplog.at_level(logging.DEBUG, logger="boneio"):
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        assert seen == [KeyboardInterrupt]
        assert not [r for r in caplog.records if r.name == "boneio"]

    def test_an_exception_that_ends_a_thread_is_logged_as_error(self, caplog):
        install_excepthooks()

        def worker():
            raise RuntimeError("thread boom")

        with caplog.at_level(logging.DEBUG, logger="boneio"):
            thread = threading.Thread(target=worker, name="worker-1")
            thread.start()
            thread.join()
        [record] = [r for r in caplog.records if r.name == "boneio"]
        assert record.levelno == logging.ERROR
        assert "worker-1" in record.getMessage()
        assert record.exc_info[0] is RuntimeError

    def test_a_thread_ending_with_system_exit_stays_silent(self, caplog):
        install_excepthooks()

        def worker():
            raise SystemExit(0)

        with caplog.at_level(logging.DEBUG, logger="boneio"):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
        assert not [r for r in caplog.records if r.name == "boneio"]


def test_setup_logging_formats_for_the_journal(monkeypatch, journal_file):
    """setup_logging picks the journal formatter for basicConfig's handler."""
    root = logging.getLogger()
    handler = logging.StreamHandler(journal_file)
    monkeypatch.setattr(root, "handlers", [handler])
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    level = root.level
    try:
        boneio_logger.setup_logging(debug_level=0)
    finally:
        root.setLevel(level)
    assert isinstance(handler.formatter, JournalLevelFormatter)
    assert sys.excepthook is not sys.__excepthook__
