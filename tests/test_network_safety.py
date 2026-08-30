import socket
from types import SimpleNamespace

import pytest

import network_safety


def _resolver_for(*addresses):
    return lambda *_args, **_kwargs: [
        (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in addresses
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "http://[::1]/private",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/private",
        "http://localhost/private",
    ],
)
def test_public_url_validation_rejects_local_and_private_targets(url):
    with pytest.raises(network_safety.UnsafeNetworkTargetError):
        network_safety.validate_public_http_url(url, resolver=_resolver_for("93.184.216.34"))


def test_public_url_validation_rejects_mixed_public_private_dns_answers():
    with pytest.raises(network_safety.UnsafeNetworkTargetError):
        network_safety.validate_public_http_url(
            "https://example.test/file.pdf",
            resolver=_resolver_for("93.184.216.34", "127.0.0.1"),
        )


def test_public_url_validation_accepts_public_dns_answer():
    assert network_safety.validate_public_http_url(
        "HTTPS://Example.Test/file.pdf",
        resolver=_resolver_for("93.184.216.34"),
    ) == "https://example.test/file.pdf"


def test_connection_rejects_mixed_dns_before_opening_a_socket():
    created = []

    with pytest.raises(network_safety.UnsafeNetworkTargetError):
        network_safety._create_public_connection(
            ("example.test", 443),
            resolver=_resolver_for("93.184.216.34", "127.0.0.1"),
            socket_factory=lambda *_args: created.append(object()),
        )

    assert created == []


def test_connection_uses_the_exact_validated_sockaddr():
    calls = []

    class _Socket:
        def settimeout(self, value):
            calls.append(("timeout", value))

        def bind(self, value):
            calls.append(("bind", value))

        def connect(self, value):
            calls.append(("connect", value))

        def close(self):
            calls.append(("close",))

    sock = network_safety._create_public_connection(
        ("example.test", 443),
        timeout=3.0,
        source_address=("0.0.0.0", 0),
        resolver=_resolver_for("93.184.216.34"),
        socket_factory=lambda *_args: _Socket(),
    )

    assert isinstance(sock, _Socket)
    assert ("connect", ("93.184.216.34", 443)) in calls
    assert ("timeout", 3.0) in calls


def test_http_connections_install_the_public_only_socket_factory():
    http_connection = network_safety._PublicHTTPConnection("example.test")
    https_connection = network_safety._PublicHTTPSConnection("example.test")

    assert http_connection._create_connection is network_safety._create_public_connection
    assert https_connection._create_connection is network_safety._create_public_connection


@pytest.mark.parametrize(
    "candidate",
    [
        "https://example.test/style.css",
        "https://example.test:443/image.png",
        "data:image/png;base64,AA==",
        "about:blank",
    ],
)
def test_snapshot_resources_are_limited_to_exact_source_origin(candidate):
    assert network_safety.snapshot_resource_allowed(
        "https://example.test/article",
        candidate,
    )


@pytest.mark.parametrize(
    "candidate",
    [
        "http://example.test/insecure.css",
        "https://cdn.example.test/style.css",
        "https://example.test:444/style.css",
        "http://127.0.0.1/private",
        "file:///tmp/private.txt",
        "javascript:alert(1)",
    ],
)
def test_snapshot_resources_reject_cross_origin_and_active_schemes(candidate):
    assert not network_safety.snapshot_resource_allowed(
        "https://example.test/article",
        candidate,
    )


def test_limited_response_does_not_trust_missing_content_length():
    chunks = iter([b"1234", b"5678", b""])
    response = SimpleNamespace(
        headers={},
        read=lambda _size: next(chunks),
    )
    with pytest.raises(ValueError, match="too large"):
        network_safety.read_response_limited(response, max_bytes=7)


def test_limited_response_rejects_declared_oversize_before_read():
    response = SimpleNamespace(
        headers={"Content-Length": "9"},
        read=lambda _size: (_ for _ in ()).throw(AssertionError("must not read")),
    )
    with pytest.raises(ValueError, match="too large"):
        network_safety.read_response_limited(response, max_bytes=8)
