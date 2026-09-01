"""Boundaries for server-side HTTP fetches triggered by external input."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

try:
    from .content_safety import normalize_external_http_url
except ImportError:
    from content_safety import normalize_external_http_url  # type: ignore


_SOCKET_DEFAULT_TIMEOUT = getattr(socket, "_GLOBAL_DEFAULT_TIMEOUT")


class UnsafeNetworkTargetError(ValueError):
    """The requested URL resolves outside the public Internet."""


def _public_socket_addresses(
    host: str,
    port: int,
    *,
    resolver: Callable = socket.getaddrinfo,
) -> list[tuple]:
    try:
        results = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeNetworkTargetError("Could not resolve the remote host.") from exc
    usable = [result for result in results if len(result) >= 5 and result[4]]
    if not usable:
        raise UnsafeNetworkTargetError("Could not resolve the remote host.")
    if any(not _address_is_public(str(result[4][0])) for result in usable):
        raise UnsafeNetworkTargetError(
            "The remote host resolves to a private or special address."
        )
    return usable


def _create_public_connection(
    address,
    timeout=_SOCKET_DEFAULT_TIMEOUT,
    source_address=None,
    *,
    resolver: Callable = socket.getaddrinfo,
    socket_factory: Callable = socket.socket,
):
    """Resolve once, validate every answer, and connect to that exact sockaddr."""
    host, port = address
    results = _public_socket_addresses(str(host), int(port), resolver=resolver)
    last_error: OSError | None = None
    for family, socktype, proto, _canonname, sockaddr in results:
        sock = None
        try:
            sock = socket_factory(family, socktype, proto)
            if timeout is not _SOCKET_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_error = exc
            if sock is not None:
                sock.close()
    if last_error is not None:
        raise last_error
    raise UnsafeNetworkTargetError("Could not connect to the remote host.")


class _PublicConnectionMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _create_public_connection


class _PublicHTTPConnection(_PublicConnectionMixin, HTTPConnection):
    pass


class _PublicHTTPSConnection(_PublicConnectionMixin, HTTPSConnection):
    pass


class _PublicHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(
            _PublicHTTPSConnection,
            req,
            context=getattr(self, "_context", None),
            check_hostname=getattr(self, "_check_hostname", None),
        )


def _address_is_public(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(str(address).split("%", 1)[0])
    except ValueError:
        return False
    return bool(parsed.is_global)


def validate_public_http_url(
    value: object,
    *,
    resolver: Callable = socket.getaddrinfo,
) -> str:
    """Normalize a URL and reject loopback, private, link-local, or special hosts."""
    clean_url = normalize_external_http_url(value)
    parsed = urlsplit(clean_url)
    hostname = str(parsed.hostname or "").rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeNetworkTargetError("Local network URLs are not allowed.")

    try:
        literal = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeNetworkTargetError("Private or special network addresses are not allowed.")
        return clean_url

    _public_socket_addresses(
        hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
        resolver=resolver,
    )
    return clean_url


def snapshot_resource_allowed(source_url: object, candidate_url: object) -> bool:
    """Allow inert snapshot resources only from the captured page's exact origin."""
    candidate = str(candidate_url or "").strip()
    if candidate == "about:blank" or candidate.startswith("data:"):
        return True
    try:
        source = urlsplit(normalize_external_http_url(source_url))
        target = urlsplit(normalize_external_http_url(candidate))
    except ValueError:
        return False

    def _origin(parts) -> tuple[str, str, int]:
        default_port = 443 if parts.scheme.casefold() == "https" else 80
        return (
            parts.scheme.casefold(),
            str(parts.hostname or "").rstrip(".").casefold(),
            int(parts.port or default_port),
        )

    return _origin(source) == _origin(target)


class _PublicOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        validate_public_http_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _connected_peer_address(response) -> str:
    """Best-effort extraction of urllib's connected socket peer."""
    candidates = (
        ("fp", "raw", "_sock"),
        ("fp", "raw", "_connection", "sock"),
    )
    for path in candidates:
        current = response
        try:
            for name in path:
                current = getattr(current, name)
            peer = current.getpeername()
        except (AttributeError, OSError, TypeError):
            continue
        if peer:
            return str(peer[0])
    return ""


def open_public_http(request: Request, *, timeout: float = 20.0):
    """Open a public HTTP(S) URL, validating the initial host and every redirect."""
    clean_url = validate_public_http_url(request.full_url)
    if clean_url != request.full_url:
        request = Request(
            clean_url,
            data=request.data,
            headers=dict(request.header_items()),
            method=request.get_method(),
        )
    # Ignore ambient HTTP proxy variables: a proxy would move destination
    # enforcement outside this boundary and could route a public hostname to a
    # private peer. The custom connections resolve, validate, and connect to
    # the same exact sockaddr while TLS still authenticates the URL hostname.
    response = build_opener(
        ProxyHandler({}),
        _PublicOnlyRedirectHandler(),
        _PublicHTTPHandler(),
        _PublicHTTPSHandler(),
    ).open(
        request,
        timeout=max(1.0, float(timeout)),
    )
    peer_address = _connected_peer_address(response)
    if peer_address and not _address_is_public(peer_address):
        response.close()
        raise UnsafeNetworkTargetError("The connection reached a private or special address.")
    final_url = getattr(response, "geturl", lambda: clean_url)()
    validate_public_http_url(final_url)
    return response


def response_content_length(response) -> int | None:
    raw = str(response.headers.get("Content-Length") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("Remote server returned an invalid Content-Length.") from exc
    if value < 0:
        raise ValueError("Remote server returned an invalid Content-Length.")
    return value


def read_response_limited(response, *, max_bytes: int, chunk_bytes: int = 1024 * 1024) -> bytes:
    """Read at most ``max_bytes`` without trusting Content-Length."""
    limit = max(1, int(max_bytes))
    declared = response_content_length(response)
    if declared is not None and declared > limit:
        raise ValueError("Remote response is too large.")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(max(1, int(chunk_bytes)), limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("Remote response is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


def copy_response_limited(
    response,
    destination,
    *,
    max_bytes: int,
    chunk_bytes: int = 1024 * 1024,
    sniff_bytes: int = 4096,
) -> tuple[int, bytes]:
    """Stream a bounded response to a binary file and return its size and prefix."""
    limit = max(1, int(max_bytes))
    declared = response_content_length(response)
    if declared is not None and declared > limit:
        raise ValueError("Remote response is too large.")
    total = 0
    prefix = bytearray()
    while True:
        chunk = response.read(min(max(1, int(chunk_bytes)), limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("Remote response is too large.")
        if len(prefix) < sniff_bytes:
            prefix.extend(chunk[: max(0, sniff_bytes - len(prefix))])
        destination.write(chunk)
    return total, bytes(prefix)
