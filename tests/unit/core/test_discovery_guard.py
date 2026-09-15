"""Tests for the discovery SSRF guard (F-15)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from boneio.core.net.discovery_guard import (
    ESPHOME_PORTS,
    REFUSAL,
    WLED_PORTS,
    DiscoveryTargetError,
    assert_target_allowed,
)


def _check(host, port=80, ports=WLED_PORTS):
    assert_target_allowed(host, port, ports)


# ------------------------------------------------------ what must still work


@pytest.mark.parametrize(
    "host",
    ["192.168.50.10", "10.0.0.5", "172.16.3.4", "fd00::1"],
)
def test_a_device_on_the_local_network_is_reachable(host):
    """Blocking private ranges would leave nothing to discover."""
    _check(host)


@pytest.mark.parametrize("port", sorted(WLED_PORTS))
def test_the_wled_ports_are_allowed(port):
    _check("192.168.1.50", port)


def test_the_esphome_api_port_is_allowed():
    _check("192.168.1.50", 6053, ESPHOME_PORTS)


# --------------------------------------------------------- the report's proof


@pytest.mark.parametrize("port", [22, 1883, 8090, 5555])
def test_the_loopback_port_scan_is_refused(port):
    """The report walks these four ports against 127.0.0.1 and reads the
    controller's own services back out of the error."""
    with pytest.raises(DiscoveryTargetError):
        _check("127.0.0.1", port)


def test_loopback_is_refused_even_on_a_valid_port():
    with pytest.raises(DiscoveryTargetError):
        _check("127.0.0.1", 80)


def test_the_cloud_metadata_address_is_refused():
    with pytest.raises(DiscoveryTargetError):
        _check("169.254.169.254")


@pytest.mark.parametrize("host", ["8.8.8.8", "93.184.216.34"])
def test_the_public_internet_is_refused(host):
    """A light strip is not on the internet; allowing it would let the
    controller be used to reach out from its own address."""
    with pytest.raises(DiscoveryTargetError):
        _check(host)


@pytest.mark.parametrize("port", [22, 23, 1883, 5555, 9999])
def test_an_arbitrary_port_is_refused(port):
    """A free choice of port is what turns discovery into a port scanner."""
    with pytest.raises(DiscoveryTargetError):
        _check("192.168.1.50", port)


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "224.0.0.1", "ff02::1", "::1", "fe80::1"]
)
def test_addresses_that_are_not_devices_are_refused(host):
    with pytest.raises(DiscoveryTargetError):
        _check(host)


def test_ipv4_mapped_loopback_is_refused():
    """::ffff:127.0.0.1 is loopback wearing an IPv6 wrapper, and the wrapper
    itself reports neither loopback nor private."""
    with pytest.raises(DiscoveryTargetError):
        _check("::ffff:127.0.0.1")


# ------------------------------------------------------------ name resolution


def test_a_name_resolving_to_loopback_is_refused():
    """The address is what matters, not the spelling."""
    with patch(
        "boneio.core.net.discovery_guard.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
    ):
        with pytest.raises(DiscoveryTargetError):
            _check("wled.local")


def test_every_resolved_address_is_checked():
    """A name under the caller's control can resolve to one harmless address
    and one loopback address; checking only the first would wave it through."""
    with patch(
        "boneio.core.net.discovery_guard.socket.getaddrinfo",
        return_value=[
            (2, 1, 6, "", ("192.168.1.50", 0)),
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ],
    ):
        with pytest.raises(DiscoveryTargetError):
            _check("rebind.example")


def test_a_name_resolving_to_a_local_device_is_allowed():
    with patch(
        "boneio.core.net.discovery_guard.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("192.168.1.50", 0))],
    ):
        _check("wled.local")


def test_a_name_that_does_not_resolve_is_refused():
    import socket as _socket

    with patch(
        "boneio.core.net.discovery_guard.socket.getaddrinfo",
        side_effect=_socket.gaierror("no such host"),
    ):
        with pytest.raises(DiscoveryTargetError):
            _check("nie-istnieje.invalid")


# ------------------------------------------------------------- what it says


def test_every_refusal_reads_the_same():
    """Saying which rule was hit would answer questions about the network that
    the caller should be asking the network."""
    messages = set()
    for host, port in [("127.0.0.1", 80), ("8.8.8.8", 80), ("192.168.1.5", 22)]:
        with pytest.raises(DiscoveryTargetError) as caught:
            _check(host, port)
        messages.add(str(caught.value))
    assert messages == {REFUSAL}


def test_the_refusal_carries_nothing_from_the_target():
    assert "SSH" not in REFUSAL and "127.0.0.1" not in REFUSAL
