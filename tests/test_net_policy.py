import pytest

from conexion_tv.core.net_policy import NonLocalNetworkError, es_host_local, exigir_host_local


def test_private_and_link_local_ok():
    assert es_host_local("192.168.1.50")
    assert es_host_local("10.42.0.1")
    assert es_host_local("127.0.0.1")
    assert es_host_local("255.255.255.255")
    assert es_host_local("239.255.255.250")


def test_public_rejected():
    assert not es_host_local("8.8.8.8")
    assert not es_host_local("1.1.1.1")
    with pytest.raises(NonLocalNetworkError):
        exigir_host_local("8.8.8.8", que="test")
