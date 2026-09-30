"""The built frontend's hashed assets, served for a slow CPU.

Every file under ``frontend-dist/assets`` carries a content hash in its name,
so it never changes under the same URL: it is sent with a one-year immutable
``Cache-Control`` and a browser does not ask for it again.

The build writes a gzip copy next to each file (``x.js.gz``). Sent as is, it
spares the controller from compressing a half-megabyte bundle on every page
load, which on a BeagleBone took longer than sending it uncompressed. A client
that does not accept gzip gets the plain file.

Without a service worker — the panel over plain HTTP by IP, the usual way in
on a local network — these two are the whole difference between a page that
opens and one that loads for seconds.
"""

from __future__ import annotations

import mimetypes
import os

from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

IMMUTABLE = "public, max-age=31536000, immutable"


def _accepts_gzip(scope: Scope) -> bool:
    accept = Headers(scope=scope).get("accept-encoding", "")
    return any(part.split(";")[0].strip() == "gzip" for part in accept.split(","))


class HashedAssets(StaticFiles):
    """StaticFiles for content-hashed assets: cached for good, gzip pre-built."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        if scope["method"] in ("GET", "HEAD") and _accepts_gzip(scope):
            full_path, stat_result = self.lookup_path(path + ".gz")
            if stat_result is not None and os.path.isfile(full_path):
                media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
                return FileResponse(
                    full_path,
                    stat_result=stat_result,
                    media_type=media_type,
                    headers={
                        # Set here, GZipMiddleware leaves the body alone.
                        "Content-Encoding": "gzip",
                        "Vary": "Accept-Encoding",
                        "Cache-Control": IMMUTABLE,
                    },
                )
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE
            response.headers["Vary"] = "Accept-Encoding"
        return response
