"""Explicit, bounded snapshot-to-TeX recognition using personal SimpleTex apps.

Protocol: https://doc.simpletex.cn/en/api/ (APP signing) and
https://doc.simpletex.cn/en/api/api_formula_recognition.html.
No collection, filesystem, credential persistence, or logging side effects.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import struct
import time
from urllib.error import HTTPError
from urllib.request import Request

try:
    from .network_safety import open_public_http, read_response_limited
except ImportError:
    from network_safety import open_public_http, read_response_limited


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_TEX_CHARS = 32768
_ENDPOINT = "https://server.simpletex.net/api/latex_ocr"


class MathRecognitionError(ValueError):
    """A fixed code suitable for translating without exposing provider data."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def normalize_latex(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEX_CHARS:
        raise MathRecognitionError("response")
    clean = value.strip()
    if not clean or clean in {"[EMPTY]", "[DOCIMG]"}:
        raise MathRecognitionError("empty")
    if any(ord(char) < 32 and char not in "\r\n\t" for char in clean):
        raise MathRecognitionError("response")
    for left, right in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
        if clean.startswith(left) and clean.endswith(right):
            clean = clean[len(left):-len(right)].strip()
            break
    if not clean:
        raise MathRecognitionError("empty")
    return clean


def format_math_copy(value: str, mode: str) -> str:
    clean = normalize_latex(value)
    if mode == "latex":
        return clean
    # Anki treats paragraph breaks inside MathJax as separate blocks. Preserve
    # TeX's explicit \\ line breaks while flattening source-code newlines.
    clean = " ".join(clean.splitlines())
    if mode == "inline":
        return rf"\({clean}\)"
    if mode == "display":
        return rf"\[{clean}\]"
    raise ValueError("Unknown math copy format")


def _validate_image(image: bytes) -> None:
    if (
        not isinstance(image, bytes) or not 33 <= len(image) <= MAX_IMAGE_BYTES
        or image[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    ):
        raise MathRecognitionError("image")
    width, height = struct.unpack(">II", image[16:24])
    if not width or not height or width * height > MAX_IMAGE_PIXELS:
        raise MathRecognitionError("image")


def recognize_snapshot(image: bytes, app_id: str, app_secret: str) -> str:
    """Upload one PNG crop; never follow redirects or persist credentials."""
    _validate_image(image)
    if any(
        not isinstance(value, str) or not value or len(value) > 512
        or any(not 33 <= ord(char) <= 126 for char in value)
        for value in (app_id, app_secret)
    ):
        raise MathRecognitionError("credentials")
    auth = {
        "app-id": app_id,
        "random-str": secrets.token_hex(8),
        "timestamp": str(int(time.time())),
    }
    canonical = "&".join(f"{key}={auth[key]}" for key in sorted(auth))
    # SimpleTex's APP protocol mandates MD5; this is not a password hash.
    signature = hashlib.md5(f"{canonical}&secret={app_secret}".encode()).hexdigest()
    boundary = "incremento-" + secrets.token_hex(16)
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="snapshot.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
    request = Request(_ENDPOINT, data=body, headers={
        **auth, "sign": signature, "Content-Type": f"multipart/form-data; boundary={boundary}",
    }, method="POST")
    try:
        with open_public_http(request, timeout=30.0, allow_redirects=False) as response:
            raw = read_response_limited(response, max_bytes=128 * 1024)
    except HTTPError as exc:
        exc.close()
        raise MathRecognitionError({401: "auth", 402: "quota", 429: "busy"}.get(exc.code, "network")) from None
    except OSError:
        raise MathRecognitionError("network") from None
    except ValueError:
        raise MathRecognitionError("response") from None
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("status") is not True:
            raise MathRecognitionError("response")
        result = payload.get("res")
        if not isinstance(result, dict):
            raise MathRecognitionError("response")
        return normalize_latex(result.get("latex"))
    except (ValueError, TypeError) as exc:
        if isinstance(exc, MathRecognitionError):
            raise
        raise MathRecognitionError("response") from None
