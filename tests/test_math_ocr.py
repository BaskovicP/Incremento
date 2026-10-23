import hashlib
import io
import json
import struct
import zlib
from urllib.error import HTTPError

import pytest

import math_ocr


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


PNG = (b"\x89PNG\r\n\x1a\n"
       + _chunk(b"IHDR", struct.pack(">II5B", 120, 40, 8, 2, 0, 0, 0))
       + _chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff" * 360) * 40))
       + _chunk(b"IEND", b""))


class Response(io.BytesIO):
    headers = {}


def test_scan_uploads_only_the_crop_with_signed_personal_credentials(monkeypatch):
    calls = []
    monkeypatch.setattr(math_ocr.time, "time", lambda: 1700000000)
    monkeypatch.setattr(math_ocr.secrets, "token_hex", lambda _n: "abcdef0123456789")

    def send(request, **options):
        calls.append((request, options))
        return Response(json.dumps({"status": True, "res": {"latex": r"\frac{x}{2}", "conf": .95}}).encode())

    monkeypatch.setattr(math_ocr, "open_public_http", send)
    result = math_ocr.recognize_snapshot(PNG, "personal-app", "private-secret")

    assert result == r"\frac{x}{2}"
    request, options = calls[0]
    assert request.full_url == "https://server.simpletex.net/api/latex_ocr"
    assert options == {"timeout": 30.0, "allow_redirects": False}
    headers = dict(request.header_items())
    assert headers["App-id"] == "personal-app"
    expected = hashlib.md5(b"app-id=personal-app&random-str=abcdef0123456789&timestamp=1700000000&secret=private-secret").hexdigest()
    assert headers["Sign"] == expected
    assert b'filename="snapshot.png"' in request.data
    assert PNG in request.data
    assert b"private-secret" not in request.data
    assert "private-secret" not in str(headers)


@pytest.mark.parametrize("image,app,secret", [
    (PNG, "", "secret"), (PNG, "app\r\nInjected: value", "secret"),
    (PNG, "app", ""), (b"not an image", "app", "secret"),
    (PNG.replace(struct.pack(">II", 120, 40), struct.pack(">II", 100000, 100000)), "app", "secret"),
    (PNG + b"x" * (8 * 1024 * 1024), "app", "secret"),
])
def test_invalid_credentials_or_crop_never_reach_the_network(monkeypatch, image, app, secret):
    calls = []
    monkeypatch.setattr(math_ocr, "open_public_http", lambda *a, **kw: calls.append(a))
    with pytest.raises(math_ocr.MathRecognitionError):
        math_ocr.recognize_snapshot(image, app, secret)
    assert calls == []


@pytest.mark.parametrize("payload,expected", [
    ({"status": True, "res": {"latex": "[EMPTY]"}}, "empty"),
    ({"status": True, "res": {"latex": "[DOCIMG]"}}, "empty"),
    ({"status": True, "res": {"latex": ""}}, "empty"),
    ({"status": True, "res": {"latex": 23}}, "response"),
    ({"status": False, "res": {"errMsg": "private-secret"}}, "response"),
    ({"status": "true", "res": {"latex": "x"}}, "response"),
    ({"status": True, "res": []}, "response"),
    ({"status": True, "res": {"latex": "x" * 32769}}, "response"),
])
def test_invalid_provider_results_fail_without_echoing_provider_data(monkeypatch, payload, expected):
    monkeypatch.setattr(math_ocr, "open_public_http", lambda *a, **kw: Response(json.dumps(payload).encode()))
    with pytest.raises(math_ocr.MathRecognitionError) as error:
        math_ocr.recognize_snapshot(PNG, "app", "private-secret")
    assert error.value.code == expected
    assert "private-secret" not in str(error.value)


@pytest.mark.parametrize("body", [b"not JSON", b"[]", b"\xff", b"x" * (128 * 1024 + 1)],
                         ids=["invalid-json", "wrong-shape", "invalid-utf8", "oversized"])
def test_malformed_and_oversized_responses_are_controlled(monkeypatch, body):
    monkeypatch.setattr(math_ocr, "open_public_http", lambda *a, **kw: Response(body))
    with pytest.raises(math_ocr.MathRecognitionError) as error:
        math_ocr.recognize_snapshot(PNG, "app", "secret")
    assert error.value.code == "response"


@pytest.mark.parametrize("status,code", [(401, "auth"), (402, "quota"), (429, "busy"), (500, "network"), (302, "network")])
def test_http_failures_return_safe_actionable_codes(monkeypatch, status, code):
    def fail(*a, **kw):
        raise HTTPError("https://example.test/private-secret", status, "private-secret", {}, None)
    monkeypatch.setattr(math_ocr, "open_public_http", fail)
    with pytest.raises(math_ocr.MathRecognitionError) as error:
        math_ocr.recognize_snapshot(PNG, "app", "secret")
    assert error.value.code == code
    assert "private-secret" not in str(error.value)


@pytest.mark.parametrize("source", [r"x^2", r"$x^2$", r"$$x^2$$", r"\(x^2\)", r"\[x^2\]"])
def test_copy_formats_use_exact_anki_delimiters_without_double_wrapping(source):
    assert math_ocr.format_math_copy(source, "latex") == "x^2"
    assert math_ocr.format_math_copy(source, "inline") == r"\(x^2\)"
    assert math_ocr.format_math_copy(source, "display") == r"\[x^2\]"


def test_chemistry_and_aligned_equations_keep_their_tex_commands():
    chemistry = r"\ce{2H2 + O2 -> 2H2O}"
    assert math_ocr.format_math_copy(chemistry, "display") == r"\[\ce{2H2 + O2 -> 2H2O}\]"
    assert math_ocr.format_math_copy("a \\\\\nb", "inline") == "\\(a \\\\ b\\)"


@pytest.mark.parametrize("source", ["", "\x00x", "x" * 32769])
def test_copy_rejects_empty_control_and_oversized_text(source):
    with pytest.raises(math_ocr.MathRecognitionError):
        math_ocr.format_math_copy(source, "display")
