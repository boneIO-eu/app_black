"""Which sections hold a secret, read off the panel's schema."""

from boneio.core.config.sections import secret_sections


def test_the_sections_holding_a_secret_are_found_in_the_schema():
    # A password, an ESPHome encryption key, an alarm code.
    assert secret_sections() == {"mqtt", "web", "remote_devices", "template"}
