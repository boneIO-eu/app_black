"""Hashed frontend assets: cached for good, and gzip taken from the build.

Compressing a bundle per request on the controller's CPU took longer than
sending it plain, and without a Cache-Control the browser kept asking for
files whose name already guarantees they never change.
"""

from __future__ import annotations

import gzip

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.routing import Mount
from starlette.testclient import TestClient

from boneio.webui.static_assets import IMMUTABLE, HashedAssets

BODY = b"console.log('boneio');\n" * 200


@pytest.fixture
def client(tmp_path):
    (tmp_path / "index-abc.js").write_bytes(BODY)
    (tmp_path / "index-abc.js.gz").write_bytes(gzip.compress(BODY))
    (tmp_path / "plain-def.css").write_bytes(b"body{}" * 200)
    app = Starlette(
        routes=[Mount("/assets", HashedAssets(directory=str(tmp_path)))],
        middleware=[Middleware(GZipMiddleware, minimum_size=500)],
    )
    return TestClient(app)


def test_the_prebuilt_gzip_is_sent_to_a_client_that_takes_it(client):
    r = client.get("/assets/index-abc.js", headers={"Accept-Encoding": "gzip, deflate, br"})
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert "javascript" in r.headers["content-type"]
    assert r.headers["cache-control"] == IMMUTABLE
    assert r.headers["vary"] == "Accept-Encoding"
    # The client decoded it; what arrived is the original file.
    assert r.content == BODY


def test_a_client_without_gzip_gets_the_plain_file(client):
    r = client.get("/assets/index-abc.js", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.headers["cache-control"] == IMMUTABLE
    assert r.content == BODY


def test_a_file_without_a_prebuilt_copy_is_still_cached_for_good(client):
    r = client.get("/assets/plain-def.css", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == IMMUTABLE


def test_a_missing_asset_is_a_plain_404_not_cached(client):
    r = client.get("/assets/nope.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 404
    assert r.headers.get("cache-control") != IMMUTABLE


def test_only_reads_are_served(client):
    r = client.post("/assets/index-abc.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 405
