"""The openssl recipe in docs/MQTT_TLS.md, run as written.

A recipe that makes certificates Home Assistant then refuses is worse than
none, because it looks like it worked. So the commands between the guide
markers are executed with a real openssl and no openssl.cnf (Windows and
macOS builds ship different ones), and what they make is tried with the
client context Home Assistant uses: Python's default, strict verification on.
"""

from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
from pathlib import Path

import pytest

from tests.tls_material import TlsServer, handshake

GUIDE = Path(__file__).resolve().parents[3] / "docs" / "MQTT_TLS.md"

pytestmark = pytest.mark.skipif(
    shutil.which("openssl") is None or shutil.which("bash") is None,
    reason="needs openssl and bash",
)


def _commands() -> list[str]:
    text = GUIDE.read_text(encoding="utf-8")
    section = text.split("<!-- openssl-guide:start -->", 1)[1].split("<!-- openssl-guide:end -->", 1)[0]
    return re.findall(r"```bash\n(.*?)```", section, re.DOTALL)


@pytest.fixture(scope="module")
def made(tmp_path_factory) -> Path:
    workdir = tmp_path_factory.mktemp("guide")
    env = {**os.environ, "OPENSSL_CONF": os.devnull}
    for block in _commands():
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", block],
            cwd=workdir, env=env, check=True, capture_output=True, timeout=60,
        )
    return workdir


def test_the_guide_has_the_four_steps():
    assert len(_commands()) == 4


def test_everything_it_makes_passes_strict_verification(made):
    # The last block is the guide's own check; it ran with check=True.
    assert (made / "broker.crt").is_file() and (made / "client.crt").is_file()


def test_home_assistant_accepts_the_broker_it_makes(made):
    context = ssl.create_default_context(cafile=str(made / "ca.crt"))
    with TlsServer(made / "broker.crt", made / "broker.key") as server:
        handshake(context, server.port, "boneio-1234.local")
        handshake(context, server.port, "192.168.1.50")
        with pytest.raises(ssl.SSLCertVerificationError):
            handshake(context, server.port, "somewhere-else.local")
    assert server.results[:2] == [True, True]


def test_a_broker_requiring_client_certificates_accepts_the_one_it_makes(made):
    context = ssl.create_default_context(cafile=str(made / "ca.crt"))
    context.load_cert_chain(str(made / "client.crt"), str(made / "client.key"))
    with TlsServer(made / "broker.crt", made / "broker.key", client_ca=made / "ca.crt") as server:
        handshake(context, server.port, "boneio-1234.local")
    assert server.results == [True]


def test_the_panel_shows_the_same_recipe():
    """The frontend builds the commands itself; the two must not drift."""
    source = (
        Path(__file__).resolve().parents[3]
        / "frontend" / "src" / "components" / "UISettings" / "mqttTls" / "openSslGuide.ts"
    ).read_text(encoding="utf-8")
    guide = "\n".join(_commands())
    for fragment in (
        "-pkeyopt ec_paramgen_curve:P-256",
        'basicConstraints=critical,CA:TRUE,pathlen:0',
        'keyUsage=critical,keyCertSign,cRLSign',
        "basicConstraints = critical, CA:FALSE",
        "keyUsage = critical, digitalSignature",
        "subjectKeyIdentifier = hash",
        "authorityKeyIdentifier = keyid",
        "-days 825",
        "-days 3650",
        "openssl verify -x509_strict -CAfile ca.crt",
    ):
        assert fragment in guide, fragment
        assert fragment in source, fragment
