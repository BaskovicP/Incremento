"""Read-only OCR overrides shared with the ordinary PDF text indexer."""

import hashlib
import json
import os
from pathlib import Path
import stat
import struct

try:
    from .paths import get_mcp_library_path
except ImportError:
    from paths import get_mcp_library_path


def image_dimensions(data: bytes) -> tuple[int, int]:
    """Read bounded raster headers without loading pixels or extra packages."""
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return struct.unpack(">II", data[16:24])
        if data.startswith((b"GIF87a", b"GIF89a")):
            return struct.unpack("<HH", data[6:10])
        if data.startswith(b"BM"):
            if int.from_bytes(data[14:18], "little") == 12:
                return struct.unpack("<HH", data[18:22])
            width, height = struct.unpack("<ii", data[18:26])
            return abs(width), abs(height)
        if data.startswith(b"\xff\xd8"):
            offset = 2
            while offset + 4 <= len(data):
                if data[offset] != 255:
                    raise ValueError()
                while offset < len(data) and data[offset] == 255:
                    offset += 1
                marker = data[offset]
                offset += 1
                if marker in {0x01, *range(0xD0, 0xDA)}:
                    continue
                length = int.from_bytes(data[offset : offset + 2], "big")
                if length < 2 or offset + length > len(data):
                    raise ValueError()
                if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                    return width, height
                offset += length
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            if data[12:16] == b"VP8X":
                return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
            if data[12:16] == b"VP8L" and data[20] == 0x2F:
                packed = int.from_bytes(data[21:25], "little")
                return 1 + (packed & 0x3FFF), 1 + ((packed >> 14) & 0x3FFF)
            if data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
                width, height = struct.unpack("<HH", data[26:30])
                return width & 0x3FFF, height & 0x3FFF
        if data[:4] in (b"II*\0", b"MM\0*"):
            endian = "little" if data[:2] == b"II" else "big"
            offset = int.from_bytes(data[4:8], endian)
            count = int.from_bytes(data[offset : offset + 2], endian)
            if not 0 < count <= 4096 or offset + 2 + count * 12 > len(data):
                raise ValueError()
            values = {}
            for index in range(count):
                entry = data[offset + 2 + index * 12 : offset + 14 + index * 12]
                tag = int.from_bytes(entry[:2], endian)
                kind = int.from_bytes(entry[2:4], endian)
                if tag in (256, 257) and int.from_bytes(entry[4:8], endian) == 1 and kind in (3, 4):
                    values[tag] = int.from_bytes(entry[8 : 10 if kind == 3 else 12], endian)
            return values[256], values[257]
    except (ValueError, KeyError, IndexError, struct.error):
        pass
    raise ValueError("Unsupported or malformed raster image header.")


def load_pdf_ocr_overrides(addon_dir: str, profile: str, card_id: int, source: str) -> dict[int, str]:
    path = get_mcp_library_path(addon_dir, profile, "ocr")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Unsafe saved OCR state.")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return {}
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 12 * 1024 * 1024:
            raise ValueError("Saved OCR state exceeds its budget.")
        value = json.loads(stream.read(12 * 1024 * 1024 + 1))
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("pdfs"), dict):
        raise ValueError("Invalid saved OCR state.")
    saved = value["pdfs"].get(str(card_id))
    if not saved:
        return {}
    texts = saved.get("texts", {})
    if not isinstance(texts, dict) or len(texts) > 1000:
        raise ValueError("Invalid saved PDF OCR pages.")
    source_path = Path(source)
    if source_path.is_symlink() or source_path.stat().st_size > 128 * 1024 * 1024:
        return {}
    digest = hashlib.sha256()
    with source_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != saved.get("hash"):
        return {}
    result = {}
    for page, text in texts.items():
        if not str(page).isdigit() or not 1 <= int(page) <= 100000 or not isinstance(text, str) or len(text) > 48000:
            raise ValueError("Invalid saved PDF OCR text.")
        result[int(page)] = text
    return result
