"""Tests for telling a freshly flashed controller from one in service.

The decision gates two wizard steps, one of which replaces the whole ``event``
section. So the case that matters most here is not the happy path but the one
that was actually wrong in the field: a 1.5.x device that never had web
authentication, upgraded in place, and was shown the full wizard.
"""

from __future__ import annotations

import pytest

from boneio.core.config.provenance import looks_factory_fresh, was_configured_before

FACTORY = "mqtt: !include mqtt.yaml\noutput: !include output32x10A.yaml\nweb:\n  port: 8090\n"
OWNERS = FACTORY + "cover:\n  - id: garage\n"


@pytest.fixture
def device(tmp_path):
    """A device with its config and the templates the image left behind."""
    templates = tmp_path / "boneio_configs"
    for variant, body in (("32x10", FACTORY), ("24x16", FACTORY.replace("32x10A", "24x16A"))):
        (templates / variant).mkdir(parents=True)
        (templates / variant / "config.yaml").write_text(body)
    config = tmp_path / "config.yaml"
    config.write_text(FACTORY)
    return config, templates


def test_an_untouched_device_is_fresh(device):
    config, templates = device
    assert looks_factory_fresh(config, templates) is True


def test_any_shipped_variant_counts_as_fresh(device):
    """The image seeds 32x10, but a device can be switched to another board."""
    config, templates = device
    config.write_text(FACTORY.replace("32x10A", "24x16A"))
    assert looks_factory_fresh(config, templates) is True


def test_a_configured_device_is_not_fresh(device):
    config, templates = device
    config.write_text(OWNERS)
    assert looks_factory_fresh(config, templates) is False


def test_no_configuration_at_all_is_fresh(tmp_path):
    """Nothing to import over and nothing to lose."""
    assert looks_factory_fresh(tmp_path / "absent.yaml", tmp_path) is True


def test_missing_templates_mean_not_fresh(tmp_path):
    """Cannot tell is not the same as fresh, and the two mistakes do not cost
    the same: one loses a wizard step, the other loses a configuration."""
    config = tmp_path / "config.yaml"
    config.write_text(FACTORY)
    assert looks_factory_fresh(config, tmp_path / "nowhere") is False


def test_an_unreadable_template_does_not_pass_as_a_match(device):
    config, templates = device
    (templates / "32x10" / "config.yaml").unlink()
    (templates / "24x16" / "config.yaml").unlink()
    assert looks_factory_fresh(config, templates) is False


# ------------------------------------------------------------ the field bug


def test_an_upgraded_device_without_web_auth_is_configured(device):
    """The bug this module exists for.

    1.5.2 → 1.6.0.dev3 on a controller whose panel had no password. The old
    signal read the absent web.auth block as "fresh device" and offered the
    import and device steps — the second of which replaces every input action.
    """
    config, templates = device
    config.write_text(OWNERS)
    assert was_configured_before(config, had_legacy_auth=False, template_dir=templates) is True


def test_web_auth_alone_still_proves_it(device):
    """It proves the device is not fresh; its absence proves nothing."""
    config, templates = device
    assert was_configured_before(config, had_legacy_auth=True, template_dir=templates) is True


def test_a_fresh_device_still_gets_the_full_wizard(device):
    config, templates = device
    assert was_configured_before(config, had_legacy_auth=False, template_dir=templates) is False
