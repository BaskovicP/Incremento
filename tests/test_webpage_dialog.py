import io
import ssl
from types import SimpleNamespace
from urllib.error import URLError

import pytest

import network_safety
import webpage_snapshot


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("about:blank", True),
        ("data:image/png;base64,AA==", True),
        ("https://example.test/image.png", False),
        ("http://127.0.0.1/private", False),
        ("file:///tmp/private", False),
        ("blob:https://example.test/id", False),
    ],
)
def test_offline_snapshot_allows_no_network_or_local_resources(url, allowed):
    assert webpage_snapshot.offline_snapshot_resource_allowed(url) is allowed


def test_fetch_webpage_html_uses_bounded_public_client(monkeypatch):
    calls = []

    class _Response:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self):
            self._chunks = iter([b"<html>safe</html>", b""])

        def read(self, _size=-1):
            return next(self._chunks)

        def geturl(self):
            return "https://example.test/final"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )
    monkeypatch.setattr(
        webpage_snapshot,
        "open_public_http",
        lambda request, *, timeout: (
            calls.append((request.full_url, timeout)) or _Response()
        ),
    )

    final_url, html = webpage_snapshot.fetch_webpage_html(
        "https://example.test/start",
        timeout_sec=7,
    )

    assert calls == [("https://example.test/start", 7.0)]
    assert final_url == "https://example.test/final"
    assert html == "<html>safe</html>"


@pytest.mark.parametrize("valid_certificate", [True, False], ids=["valid-tls", "invalid-tls"])
def test_https_webpage_fetch_preserves_tls_verification(monkeypatch, valid_certificate):
    """Exercise the real urllib handler/connection, replacing only network I/O."""
    url = "https://93.184.216.34/article"
    body = b"<html>Article for PDF conversion</html>"
    destinations = []
    tls_checks = []
    requests = []

    class _Socket:
        def setsockopt(self, *args):
            pass

        def sendall(self, data):
            requests.append(data)

        def makefile(self, mode):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            )

        def close(self):
            pass

    def connect(address, timeout, source_address):
        destinations.append((address, timeout))
        return _Socket()

    def wrap_socket(context, sock, *, server_hostname):
        tls_checks.append((context.verify_mode, context.check_hostname, server_hostname))
        if not valid_certificate:
            raise ssl.SSLCertVerificationError("Test certificate rejected")
        return sock

    monkeypatch.setattr(network_safety, "_create_public_connection", connect)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)

    if valid_certificate:
        assert webpage_snapshot.fetch_webpage_html(url, timeout_sec=7) == (
            url, body.decode("utf-8")
        )
        assert b"GET /article HTTP/1.1\r\n" in b"".join(requests)
    else:
        with pytest.raises(URLError) as exc:
            webpage_snapshot.fetch_webpage_html(url, timeout_sec=7)
        assert isinstance(exc.value.reason, ssl.SSLCertVerificationError)
        assert requests == []

    assert destinations == [(("93.184.216.34", 443), 7.0)]
    assert tls_checks == [(ssl.CERT_REQUIRED, True, "93.184.216.34")]


def test_fetch_webpage_html_rejects_non_document_content(monkeypatch):
    response = SimpleNamespace(
        headers={"Content-Type": "application/octet-stream"},
        read=lambda _size=-1: b"binary",
        geturl=lambda: "https://example.test/file",
        __enter__=lambda self: self,
        __exit__=lambda self, *_args: False,
    )

    class _ContextResponse:
        headers = response.headers

        def read(self, size=-1):
            return response.read(size)

        def geturl(self):
            return response.geturl()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )
    monkeypatch.setattr(
        webpage_snapshot,
        "open_public_http",
        lambda *_args, **_kwargs: _ContextResponse(),
    )

    with pytest.raises(ValueError, match="HTML document"):
        webpage_snapshot.fetch_webpage_html("https://example.test/file")
