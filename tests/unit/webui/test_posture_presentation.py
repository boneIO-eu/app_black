"""Every security check has to arrive in the panel as something readable.

Two ways that failed, both shipped: a check added under an id another check
already used, so the same finding appeared twice, and a check with no
translation, which reaches a Polish panel as English — title, description and
a remedy cut off mid-sentence.

Neither is visible from either side alone. The ids live in Python, the text
lives in JSON, and nothing connected them until this did.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boneio.core.security.posture import evaluate

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCALES = REPO_ROOT / "frontend" / "src" / "locales"

#: Every field the panel looks up per check. `ok` is the wording shown once a
#: check passes, which is a different sentence from the failure.
FIELDS = ("title", "detail", "remedy", "ok")


def _all_checks():
    """Every check the backend can produce.

    Not one evaluation: some checks only appear under a condition — dev_mode
    needs the environment variable — and a test that asked once would call
    their translations stale.
    """
    import os
    from unittest.mock import patch

    # Some wordings only appear under a setting, so an empty config is not
    # enough: a variant nobody produced here would be reported as translated
    # when nothing had looked for its text.
    configs: tuple[dict, ...] = (
        {},
        {"web": {"cloud": {"declined": True}}},
        {"web": {"cloud": {"enabled": True}}},
    )
    checks = []
    for environ in ({}, {"BONEIO_DEV": "1"}):
        with patch.dict(os.environ, environ, clear=False):
            for config in configs:
                checks.extend(
                    evaluate(
                        config,
                        is_provisioned=False,
                        anonymous_allowed=True,
                        auth_required=False,
                        cloud_active=False,
                    ).checks
                )
    return checks


def _check_ids() -> set[str]:
    """The distinct ids, for the tests that do not care about duplicates."""
    return {check.id for check in _all_checks()}


def _translations(language: str) -> dict:
    path = LOCALES / language / "common.json"
    return json.loads(path.read_text(encoding="utf-8"))["security"].get("checks", {})


def test_no_two_checks_share_an_id():
    """A repeated id is the same finding listed twice, and a fix button that
    does not obviously belong to either copy."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"BONEIO_DEV": "1"}, clear=False):
        ids = [
            check.id
            for check in evaluate(
                {},
                is_provisioned=False,
                anonymous_allowed=True,
                auth_required=False,
                cloud_active=False,
            ).checks
        ]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"more than one check uses: {sorted(duplicates)}"


@pytest.mark.parametrize("language", ["en", "pl"])
def test_every_check_is_translated(language):
    strings = _translations(language)
    missing = [check_id for check_id in sorted(_check_ids()) if check_id not in strings]
    assert not missing, (
        f"{language}: no translation for {sorted(missing)} — these reach the "
        "panel as the backend's English"
    )


@pytest.mark.parametrize("language", ["en", "pl"])
def test_every_translated_check_is_complete(language):
    strings = _translations(language)
    incomplete = [
        f"{check_id}.{field}"
        for check_id, entry in strings.items()
        for field in FIELDS
        if not str(entry.get(field, "")).strip()
    ]
    assert not incomplete, f"{language}: empty or missing {sorted(incomplete)}"


@pytest.mark.parametrize("language", ["en", "pl"])
def test_no_translation_describes_a_check_that_is_gone(language):
    """A renamed check leaves its old text behind, where it reads as current."""
    known = _check_ids()
    stale = [check_id for check_id in _translations(language) if check_id not in known]
    assert not stale, f"{language}: text for checks that no longer exist: {sorted(stale)}"


@pytest.mark.parametrize("language", ["en", "pl"])
def test_every_variant_is_translated(language):
    """A check with several wordings needs one translation per wording.

    The panel keys its text by check id, so a check whose English varies at
    runtime collapses to a single translated sentence — and not necessarily the
    right one. The certificate check had four states and one Polish remedy
    saying "enable cloud registration", shown even on a device whose owner had
    declined it. `variant` splits the key; this is what keeps the halves in
    step.
    """
    strings = _translations(language)
    missing = []
    for check in _all_checks():
        if not check.variant:
            continue
        entry = strings.get(check.id, {})
        for field in ("detail", "remedy"):
            # Only where the backend has something to say. A variant with no
            # remedy needs no translation for one.
            if not str(getattr(check, field, "")).strip():
                continue
            key = f"{field}_{check.variant}"
            if not str(entry.get(key, "")).strip():
                missing.append(f"{check.id}.{key}")
    assert not missing, (
        f"{language}: no translation for {sorted(set(missing))} — the panel "
        "falls back to the wording of the other state, which is what this "
        "variant exists to avoid"
    )
