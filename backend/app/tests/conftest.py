"""Offline regression suite; fake providers must never use public networks."""
import ipaddress
import os
import socket

import pytest

# LiteLLM normally refreshes model prices at import. Use its bundled table in tests.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def no_public_network(monkeypatch):
    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def is_local(host):
        if host in {"localhost", None}:
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def connect(sock, address):
        if isinstance(address, tuple) and not is_local(address[0]):
            raise AssertionError("Public network is forbidden in the regression suite")
        return original_connect(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if not is_local(host):
            raise AssertionError("Public DNS is forbidden in the regression suite")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
