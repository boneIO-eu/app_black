#!/usr/bin/env python3
"""Generate and sign the migration plans that ship with a release.

The privileged helper must not be handed a plan by the unprivileged process it
serves — that is the escalation path behind CVE-2026-77055. So plans are frozen
and signed here, at release time, and the helper accepts nothing but a version
string and verifies the rest against a pinned public key.

Outputs, all under ``boneio/migrations/plans/``:

    <version>.json   canonical serialisation of the module's plan()
    <version>.sig    Ed25519 signature over those exact bytes
    manifest.json    {release, plans: {version: sha256}}
    manifest.sig     signature over the manifest

The manifest exists so a plan cannot be swapped for a differently-versioned one
that also carries a valid signature: the helper checks the plan's hash against
the manifest for the installed release, not just the signature.

Usage:
    generate_signed_plans.py --key <private.pem>        # generate + sign
    generate_signed_plans.py --check --key <private.pem>  # verify, write nothing
    generate_signed_plans.py --check                    # verify signatures only
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib
import json
import os
import pkgutil
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

VERSIONS_PKG = "boneio.migrations.versions"
PLANS_DIR = REPO_ROOT / "boneio" / "migrations" / "plans"
PUBKEY = REPO_ROOT / "boneio" / "migrations" / "assets" / "migrations.pem"


class NotDeterministic(Exception):
    """A plan cannot be frozen because it depends on where it was built."""


#: Migrations whose plan() probes the running system and therefore cannot be
#: frozen at release time. They are excluded from the signed set deliberately,
#: which means they will not run under the signing helper — record the reason
#: here rather than letting them be signed as whatever this build machine
#: happened to need.
NON_PORTABLE: dict[str, str] = {
    "1.5.2": (
        "plan() returns [] when the build machine already has libyaml, and "
        "otherwise embeds sys.executable, getpass.getuser() and a wheel chosen "
        "for the build interpreter. Needs the probe moved behind skip_if and "
        "the interpreter/user supplied by the helper."
    ),
    "1.5.3": (
        "same as 1.5.2 — it is the retry of that migration and shares its "
        "environment probing."
    ),
}


def _canonical(obj: object) -> bytes:
    """Serialise deterministically, so the same plan always signs identically.

    Args:
        obj: JSON-serialisable structure.

    Returns:
        UTF-8 bytes with sorted keys and no incidental whitespace.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


#: Values that betray the build environment. A plan carrying any of these would
#: be signed with CI's paths baked in and then handed to a BeagleBone, where
#: they mean nothing — sys.executable is the runner's interpreter, getuser() is
#: "runner", and a wheel chosen by _find_wheel() matches CI's Python tag.
def _environment_fingerprints() -> dict[str, str]:
    """Strings whose presence in a plan means it is not portable."""
    marks = {
        "the interpreter running this script": sys.executable,
        "the current user": getpass.getuser(),
        "this home directory": str(Path.home()),
        "this checkout": str(REPO_ROOT),
    }
    for var in ("GITHUB_WORKSPACE", "RUNNER_TEMP", "VIRTUAL_ENV", "HOSTNAME"):
        value = os.environ.get(var)
        if value:
            marks[f"${var}"] = value
    return {k: v for k, v in marks.items() if v and len(v) > 3}


def _assert_portable(version: str, payload: object) -> None:
    """Refuse a plan that carries build-environment values.

    Args:
        version: Migration version, for the error message.
        payload: The serialised plan.

    Raises:
        NotDeterministic: If the plan embeds anything local to this machine.
    """
    blob = _canonical(payload).decode("utf-8")
    for what, value in _environment_fingerprints().items():
        if value in blob:
            raise NotDeterministic(
                f"{version}: the plan embeds {what} ({value!r}).\n"
                "        A signed plan is executed on a device, not here, so it "
                "must not name\n"
                "        local paths or users. Move the lookup into the helper "
                "(which knows the\n"
                "        device's venv and service account) and keep a "
                "placeholder in the plan."
            )


def _assert_stable(version: str, module) -> object:
    """Call plan() twice and require the same answer.

    Args:
        version: Migration version, for the error message.
        module: The imported migration module.

    Returns:
        The serialised plan.

    Raises:
        NotDeterministic: If two calls disagree.
    """
    first = [a.to_dict() for a in module.plan()]
    second = [a.to_dict() for a in module.plan()]
    if _canonical(first) != _canonical(second):
        raise NotDeterministic(
            f"{version}: plan() returns something different on each call, so it "
            "cannot be frozen."
        )
    return first


def _sign(key: Path, data: bytes, out: Path) -> None:
    """Write an Ed25519 signature over ``data``.

    Args:
        key: Private key in PEM form.
        data: Exact bytes to sign.
        out: Signature destination.
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-inkey", str(key),
             "-rawin", "-in", tmp_path, "-out", str(out)],
            check=True, capture_output=True,
        )
    finally:
        os.unlink(tmp_path)


def _verify(pubkey: Path, data: bytes, sig: Path) -> bool:
    """Check a signature the way the device will.

    Args:
        pubkey: Public key in PEM form.
        data: Exact bytes that were signed.
        sig: Signature file.

    Returns:
        True when the signature is good.
    """
    if not sig.exists():
        return False
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(pubkey),
             "-sigfile", str(sig), "-rawin", "-in", tmp_path],
            capture_output=True,
        )
        return result.returncode == 0
    finally:
        os.unlink(tmp_path)


def _release_version() -> str:
    """The version of the package being released."""
    from boneio.version import __version__

    return __version__


def _discover() -> list[tuple[str, object]]:
    """Import every migration module, ordered by version.

    Returns:
        (version, module) pairs.

    Raises:
        NotDeterministic: If two modules claim the same version.
    """
    versions_path = Path(importlib.import_module(VERSIONS_PKG).__file__).parent
    found: list[tuple[str, object]] = []
    for _, name, _ in pkgutil.iter_modules([str(versions_path)]):
        mod = importlib.import_module(f"{VERSIONS_PKG}.{name}")
        version = getattr(mod, "VERSION", None)
        if not version:
            print(f"  skip {name}: no VERSION", file=sys.stderr)
            continue
        found.append((version, mod))
    seen = [v for v, _ in found]
    dupes = {v for v in seen if seen.count(v) > 1}
    if dupes:
        raise NotDeterministic(f"duplicate migration versions: {sorted(dupes)}")
    return sorted(found, key=lambda pair: [int(p) for p in re.findall(r"\d+", pair[0])])


def main() -> int:
    """Entry point.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, help="Ed25519 private key (PEM)")
    parser.add_argument(
        "--check", action="store_true",
        help="verify what is on disk and write nothing",
    )
    parser.add_argument(
        "--rotate-key", action="store_true",
        help="allow replacing the committed public key (deliberate rotation only)",
    )
    args = parser.parse_args()

    if not args.check and not args.key:
        parser.error("--key is required unless --check is given")

    PLANS_DIR.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    plans: dict[str, object] = {}
    skipped: list[str] = []

    for version, module in _discover():
        if version in NON_PORTABLE:
            skipped.append(version)
            continue
        try:
            payload = _assert_stable(version, module)
            _assert_portable(version, payload)
            # An empty plan is never legitimate: a migration that plans nothing
            # unconditionally would not exist. It means plan() looked at this
            # machine, decided the work was already done, and would freeze that
            # verdict for every device — silently turning the migration into a
            # no-op on the controllers that actually need it.
            if not payload:
                raise NotDeterministic(
                    f"{version}: plan() is empty on this machine, which means it "
                    "probes the\n        running system. Freezing that would ship "
                    "a no-op to devices that need\n        the work. Either make "
                    "plan() unconditional (and let skip_if decide at\n        "
                    "runtime) or add it to NON_PORTABLE with a reason."
                )
        except NotDeterministic as err:
            problems.append(str(err))
            continue
        plans[version] = payload

    if skipped:
        print("Deliberately unsigned (see NON_PORTABLE):", file=sys.stderr)
        for version in skipped:
            print(f"  – {version}: {NON_PORTABLE[version]}", file=sys.stderr)
        print(file=sys.stderr)

    if problems:
        print("Refusing to sign — these plans are not portable:\n", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}\n", file=sys.stderr)
        print(
            "A plan signed here is executed on a controller. Baking this "
            "machine's paths\ninto it would hand the device nonsense that the "
            "signature then blesses.",
            file=sys.stderr,
        )
        return 1

    manifest = {
        "release": _release_version(),
        "plans": {
            version: hashlib.sha256(_canonical(payload)).hexdigest()
            for version, payload in plans.items()
        },
    }

    if args.check:
        if not PUBKEY.exists():
            print(f"missing public key: {PUBKEY}", file=sys.stderr)
            return 1
        bad = []
        for version, payload in plans.items():
            data = _canonical(payload)
            plan_path = PLANS_DIR / f"{version}.json"
            if not plan_path.exists() or plan_path.read_bytes() != data:
                bad.append(f"{version}: plan on disk differs from plan() output")
            elif not _verify(PUBKEY, data, PLANS_DIR / f"{version}.sig"):
                bad.append(f"{version}: signature missing or invalid")
        manifest_data = _canonical(manifest)
        manifest_path = PLANS_DIR / "manifest.json"
        if not manifest_path.exists() or manifest_path.read_bytes() != manifest_data:
            bad.append("manifest.json is stale")
        elif not _verify(PUBKEY, manifest_data, PLANS_DIR / "manifest.sig"):
            bad.append("manifest signature missing or invalid")
        if args.key:
            derived = subprocess.run(
                ["openssl", "pkey", "-in", str(args.key), "-pubout"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            if derived != PUBKEY.read_text().strip():
                bad.append(
                    "the public key in the repo does not match the signing key"
                )
        for line in bad:
            print(f"  ✗ {line}", file=sys.stderr)
        if bad:
            return 1
        print(f"OK: {len(plans)} plans, manifest and signatures all verify.")
        return 0

    derived = subprocess.run(
        ["openssl", "pkey", "-in", str(args.key), "-pubout"],
        capture_output=True, text=True, check=True,
    ).stdout

    # The public key is the trust anchor pinned on every device. Signing with a
    # different private key than the one the repo advertises would re-pin it
    # silently — which is exactly the move an attacker with CI access would
    # make. Rotation has to be deliberate and paired with a release that
    # accepts both keys.
    if PUBKEY.exists() and PUBKEY.read_text().strip() != derived.strip():
        if not args.rotate_key:
            print(
                "The signing key does not match the public key committed in the "
                "repo.\nThat key is pinned on every device in the field. If this "
                "is a genuine\nrotation, pass --rotate-key and ship a release "
                "that accepts both keys\nfirst; otherwise the wrong key is "
                "configured.",
                file=sys.stderr,
            )
            return 1
        print("Rotating the committed public key (--rotate-key given).")
    PUBKEY.write_text(derived)

    for version, payload in plans.items():
        data = _canonical(payload)
        (PLANS_DIR / f"{version}.json").write_bytes(data)
        _sign(args.key, data, PLANS_DIR / f"{version}.sig")

    manifest_data = _canonical(manifest)
    (PLANS_DIR / "manifest.json").write_bytes(manifest_data)
    _sign(args.key, manifest_data, PLANS_DIR / "manifest.sig")

    print(f"Signed {len(plans)} plans for release {manifest['release']}:")
    for version in plans:
        print(f"  {version}")
    print(f"Manifest and public key written. Plans dir: {PLANS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
