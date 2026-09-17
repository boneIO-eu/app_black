"""Tests for the two code-level findings: F-09 and F-16."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from boneio.core.config.migrations import v4_wled_cache
from boneio.webui.routes import timezone_sudoers


# ------------------------------------------------- F-09: sudoers temp file


def _source() -> str:
    return inspect.getsource(timezone_sudoers)


def test_the_password_path_is_gone_entirely():
    """These two used to check how create_timedatectl_sudoers_file() installed
    the file: with `install` rather than cp+chmod, and cleaning up its temp file
    on every path. The function is gone — the sudoers fragment now arrives with
    migration 1.6.7, over a channel that needs no password at all, so there is
    no install sequence here left to harden.

    What is worth guarding is that it does not come back: an endpoint that
    collects the sudo password is a way to intercept a password shared across
    every controller.
    """
    import boneio.webui.routes.timezone_sudoers as module

    assert not hasattr(module, "create_timedatectl_sudoers_file")
    # A password piped to sudo is the shape to watch for; the module may still
    # mention the old function in a comment explaining why it went.
    source = _source()
    assert '"-S"' not in source, (
        "something in this module pipes a password to sudo again"
    )


def test_mkstemp_gives_a_private_file(tmp_path):
    """Whatever else changes, the guarantee relied on is O_EXCL at 0600."""
    import os
    import stat
    import tempfile

    fd, path = tempfile.mkstemp(dir=tmp_path)
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600
    finally:
        os.close(fd)
        os.unlink(path)


# --------------------------------------------- F-16: !secret and the migration


@pytest.fixture
def config_dir(tmp_path):
    """A config that uses !secret, exactly as the documentation advises."""
    (tmp_path / "secrets.yaml").write_text("mqtt_pw: boneio123\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        "mqtt:\n"
        "  host: localhost\n"
        "  password: !secret mqtt_pw\n"
        "remote_devices:\n"
        "  - id: wled1\n"
        "    host: 192.168.1.50\n"
        "    wled:\n"
        "      effects:\n"
        "        - id: 0\n"
        "          name: Solid\n"
        "      palettes:\n"
        "        - id: 0\n"
        "          name: Default\n",
        encoding="utf-8",
    )
    return tmp_path


def test_a_config_using_secret_still_migrates(config_dir, caplog):
    """The whole finding: using a documented security feature stopped the
    migration, for exactly the people who had followed the advice."""
    with caplog.at_level("ERROR"):
        v4_wled_cache._persist_wled_cache_strip(str(config_dir / "config.yaml"))

    assert "could not determine a constructor" not in caplog.text
    assert (config_dir / ".wled_cache.json").exists()


def test_the_extracted_cache_holds_the_wled_metadata(config_dir):
    v4_wled_cache._persist_wled_cache_strip(str(config_dir / "config.yaml"))
    cache = json.loads((config_dir / ".wled_cache.json").read_text(encoding="utf-8"))
    assert cache["wled1"]["effects"][0]["name"] == "Solid"


def test_the_secret_tag_survives_the_rewrite(config_dir):
    """The file is edited with regexes rather than re-serialised, so a tag
    the loader only stood in for is written back exactly as it was."""
    v4_wled_cache._persist_wled_cache_strip(str(config_dir / "config.yaml"))
    text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    assert "password: !secret mqtt_pw" in text


def test_an_unknown_tag_added_later_cannot_break_it(tmp_path):
    """The catch-all is what stops this recurring with the next custom tag."""
    (tmp_path / "config.yaml").write_text(
        "remote_devices:\n"
        "  - id: wled1\n"
        "    host: !something_new zzz\n"
        "    wled:\n"
        "      effects:\n"
        "        - id: 0\n"
        "          name: Solid\n",
        encoding="utf-8",
    )
    v4_wled_cache._persist_wled_cache_strip(str(tmp_path / "config.yaml"))
    assert (tmp_path / ".wled_cache.json").exists()


def test_a_config_without_custom_tags_still_works(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "remote_devices:\n"
        "  - id: wled1\n"
        "    wled:\n"
        "      effects:\n"
        "        - id: 1\n"
        "          name: Blink\n",
        encoding="utf-8",
    )
    v4_wled_cache._persist_wled_cache_strip(str(tmp_path / "config.yaml"))
    cache = json.loads((tmp_path / ".wled_cache.json").read_text(encoding="utf-8"))
    assert cache["wled1"]["effects"][0]["name"] == "Blink"
