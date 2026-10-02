"""The token secret belongs to the controller it was drawn on.

SD card images were built on a controller that had already run, so every
device flashed from one shipped the same ``jwt_secret`` — and anyone with the
image could sign an administrator's token for all of them.
"""

import os
import stat

import pytest

from boneio.core.auth import jwt_secret as module
from boneio.core.auth.jwt_secret import JWT_SECRET_FILENAME, load_or_create_jwt_secret


@pytest.fixture
def machine_id(tmp_path):
    path = tmp_path / "machine-id"
    path.write_text("da3062dc0123456789abcdef01234567\n")
    return path


def _load(tmp_path, machine_id):
    return load_or_create_jwt_secret(tmp_path, machine_id_path=machine_id)


def test_a_new_secret_is_kept_across_starts(tmp_path, machine_id):
    first = _load(tmp_path, machine_id)
    assert len(first) == 64
    assert _load(tmp_path, machine_id) == first


def test_the_file_is_owner_only(tmp_path, machine_id):
    _load(tmp_path, machine_id)
    mode = stat.S_IMODE(os.stat(tmp_path / JWT_SECRET_FILENAME).st_mode)
    assert mode == 0o600


def test_machine_id_itself_is_not_stored(tmp_path, machine_id):
    _load(tmp_path, machine_id)
    content = (tmp_path / JWT_SECRET_FILENAME).read_text()
    assert "da3062dc" not in content


def test_a_secret_from_an_image_is_replaced(tmp_path, machine_id):
    # What every controller flashed from a dev27..dev29 image carried: one
    # line, no binding.
    (tmp_path / JWT_SECRET_FILENAME).write_text("b5fa9b36" * 8)
    assert _load(tmp_path, machine_id) != "b5fa9b36" * 8


def test_a_secret_drawn_on_another_machine_is_replaced(tmp_path, machine_id):
    first = _load(tmp_path, machine_id)
    machine_id.write_text("a144f26d0123456789abcdef01234567\n")
    assert _load(tmp_path, machine_id) != first


def test_without_a_machine_id_the_secret_is_kept(tmp_path):
    # An image being built has an empty machine-id. Replacing the secret on
    # every start would sign everybody out each time.
    empty = tmp_path / "machine-id"
    empty.write_text("")
    first = _load(tmp_path, empty)
    assert _load(tmp_path, empty) == first
    assert _load(tmp_path, tmp_path / "missing") == first


def test_a_secret_drawn_without_identity_is_bound_on_first_boot(tmp_path, machine_id):
    empty = tmp_path / "empty-id"
    empty.write_text("")
    at_build = _load(tmp_path, empty)
    at_first_boot = _load(tmp_path, machine_id)
    assert at_first_boot != at_build
    assert _load(tmp_path, machine_id) == at_first_boot


def test_an_unwritable_directory_still_yields_a_secret(tmp_path, machine_id, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(module, "_write_secret", refuse)
    assert len(_load(tmp_path, machine_id)) == 64
