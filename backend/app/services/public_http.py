"""Bounded public HTTP transport; DNS answers are pinned at socket connection.

HTTP Host and TLS SNI stay the original hostname. Proxy environment settings are
deliberately unused for source downloads, so a proxy cannot bypass address checks.
"""
import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from urllib.parse import urljoin

import httpcore
import httpx

from app.researchguard.source_locator import canonical_url

_DNS = ThreadPoolExecutor(max_workers=4, thread_name_prefix='source-dns')


class UnsafeSourceURL(ValueError):
    pass


def public_address(value):
    ip = ipaddress.ip_address(value.split('%')[0])
    if not ip.is_global or ip.is_multicast or ip.is_unspecified:
        return False
    for mapped in (getattr(ip, 'ipv4_mapped', None), getattr(ip, 'sixtofour', None)):
        if mapped is not None and not mapped.is_global:
            return False
    return not getattr(ip, 'teredo', None)


def resolve_public(host, port, timeout=5.0):
    future = _DNS.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
    try:
        answers = future.result(timeout=timeout)
    except (OSError, FutureTimeout) as exc:
        future.cancel()
        raise UnsafeSourceURL('SOURCE_DNS_UNAVAILABLE') from exc
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses or any(not public_address(ip) for ip in addresses):
        raise UnsafeSourceURL('SOURCE_ADDRESS_BLOCKED')
    return addresses


class PublicNetworkBackend(httpcore.SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        deadline = time.monotonic() + min(timeout or 10, 10)
        addresses = resolve_public(host, port, min(5, timeout or 5))
        last = None
        for address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                # Numeric address: no second hostname lookup can change the target.
                return super().connect_tcp(address, port, remaining, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        raise httpcore.ConnectError('SOURCE_CONNECTION_FAILED') from last


class PublicHTTPTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__(retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(network_backend=PublicNetworkBackend(),
                                             max_connections=4, max_keepalive_connections=0)


def source_client(timeout=30):
    return httpx.Client(transport=PublicHTTPTransport(), timeout=timeout,
                        follow_redirects=False, trust_env=False)


def fetch_public(client, url, *, headers, max_bytes, timeout=30, max_redirects=5):
    """Read decoded bytes incrementally; validate every redirect before contacting it.

    A caller-supplied transport is a trusted dependency for offline HTTP contracts.
    Production clients always use PublicNetworkBackend, including redirected hosts.
    """
    current = canonical_url(url)
    deadline = time.monotonic() + timeout
    for hop in range(max_redirects + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise httpx.TimeoutException('SOURCE_DOWNLOAD_TIMEOUT')
        with client.stream('GET', current, headers=headers, follow_redirects=False,
                           timeout=min(remaining, 30)) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                if hop == max_redirects or not response.headers.get('location'):
                    raise UnsafeSourceURL('SOURCE_REDIRECT_LIMIT')
                current = canonical_url(urljoin(current, response.headers['location']))
                continue
            length = response.headers.get('content-length', '')
            if length.isdecimal() and int(length) > max_bytes:
                raise UnsafeSourceURL('SOURCE_RESPONSE_TOO_LARGE')
            content = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() > deadline:
                    raise httpx.TimeoutException('SOURCE_DOWNLOAD_TIMEOUT')
                if len(content) + len(chunk) > max_bytes:
                    raise UnsafeSourceURL('SOURCE_RESPONSE_TOO_LARGE')
                content.extend(chunk)
            # Build a bounded in-memory response only after streaming validation.
            clean_headers = {k: v for k, v in response.headers.items()
                             if k.lower() not in {'content-encoding', 'content-length', 'transfer-encoding'}}
            return httpx.Response(response.status_code, headers=clean_headers,
                                  content=bytes(content), request=httpx.Request('GET', current))
    raise UnsafeSourceURL('SOURCE_REDIRECT_LIMIT')
