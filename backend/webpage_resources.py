"""Bundle public webpage styles and images for an entirely offline PDF render."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import re
from threading import Lock
import time
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import Request

from bs4 import BeautifulSoup

try:
    from .network_safety import open_public_http, read_response_limited, validate_public_http_url
except ImportError:
    from network_safety import open_public_http, read_response_limited, validate_public_http_url


MAX_RESOURCE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_RESOURCE_BYTES = 32 * 1024 * 1024
MAX_RESOURCES = 256
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_HTML_BYTES = 16 * 1024 * 1024
_MAX_CSS_DEPTH = 4
_CSS_STRING = r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
_CSS_URL = rf'''url\(\s*(?:{_CSS_STRING}|[^)"']*)\s*\)'''
_CSS_RESOURCE = re.compile(
    rf'''(?P<import>@import\s+)(?P<target>{_CSS_URL}|{_CSS_STRING})|(?P<url>{_CSS_URL})''',
    re.IGNORECASE,
)
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6}\s?|\r\n|[\n\r\f]|.)", re.DOTALL)
_CSP = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline' data:; "
    "font-src data:; base-uri 'none'; form-action 'none'; frame-src 'none'"
)


def _css_target(token: str) -> str:
    if token[:4].casefold() == "url(":
        token = token[4:-1].strip()
    if token[:1] in {'"', "'"}:
        token = token[1:-1]

    def unescape(match):
        value = match.group(1)
        if value[:1] in "0123456789abcdefABCDEF":
            number = int(value.strip(), 16)
            return chr(number) if 0 < number <= 0x10FFFF else "\ufffd"
        return "" if value in {"\n", "\r", "\r\n", "\f"} else value

    return _CSS_ESCAPE.sub(unescape, token).strip()


def _binary_mime(raw: bytes) -> str:
    for signature, mime in (
        (b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
        (b"wOF2", "font/woff2"), (b"wOFF", "font/woff"),
        (b"OTTO", "font/otf"), (b"\x00\x01\x00\x00", "font/ttf"),
        (b"\x00\x00\x01\x00", "image/x-icon"),
    ):
        if raw.startswith(signature):
            return mime
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[4:8] == b"ftyp" and raw[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return ""


class _DeadlineResponse:
    def __init__(self, response, deadline: float):
        self.response = response
        self.headers = response.headers
        self.deadline = deadline

    def read(self, size: int) -> bytes:
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Webpage resource capture timed out.")
        # HTTPResponse.read1 returns available bytes rather than waiting for a
        # whole chunk, so a trickling server cannot evade the shared deadline.
        reader = getattr(self.response, "read1", self.response.read)
        return reader(size)


class _Resources:
    def __init__(self, timeout_sec: float, html_bytes: int):
        self.deadline = time.monotonic() + max(0.0, float(timeout_sec))
        self.cache: dict[str, tuple[str, bytes, str] | None] = {}
        self.lock = Lock()
        self.total = 0
        self.output_bytes = html_bytes

    def claim_output(self, size: int) -> None:
        # Charge each use, including repeated images and recursively expanded CSS,
        # before constructing base64 strings or serializing the final DOM.
        self.output_bytes += size
        if self.output_bytes > MAX_SNAPSHOT_BYTES:
            raise ValueError("Webpage snapshot exceeds the size limit.")

    @staticmethod
    def absolute(reference: str, base_url: str) -> str:
        try:
            candidate = urljoin(base_url, str(reference or "").strip())
            return candidate if urlsplit(candidate).scheme.casefold() in {"http", "https"} else ""
        except ValueError:
            return ""

    def download(self, url: str) -> tuple[str, bytes, str] | None:
        cache_key = url
        with self.lock:
            if url in self.cache:
                return self.cache[url]
            if not url or len(self.cache) >= MAX_RESOURCES or self.total >= MAX_TOTAL_RESOURCE_BYTES:
                return None
            self.cache[url] = None
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            url = urldefrag(validate_public_http_url(url))[0]
            request = Request(url, headers={"User-Agent": "Incremento/1.0", "Accept": "text/css,image/*,font/*;q=0.9"})
            with open_public_http(request, timeout=max(1.0, min(5.0, remaining))) as response:
                mime = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
                raw = read_response_limited(
                    _DeadlineResponse(response, self.deadline),
                    max_bytes=MAX_RESOURCE_BYTES, chunk_bytes=64 * 1024,
                )
                final_url = validate_public_http_url(str(response.geturl() or url))
            if mime != "text/css":
                # SVG is inert in image context; the renderer also denies scripts,
                # embedded frames, remote references, and all local file access.
                mime = "image/svg+xml" if mime == "image/svg+xml" and b"<svg" in raw[:4096].lower() else _binary_mime(raw)
            if not mime:
                return None
            with self.lock:
                if self.total + len(raw) > MAX_TOTAL_RESOURCE_BYTES:
                    return None
                self.total += len(raw)
                value = (mime, raw, final_url)
                self.cache[cache_key] = value
            return value
        except Exception:
            # An unavailable optional resource must not discard the article.
            return None

    def preload(self, references: list[str]) -> None:
        unique = list(dict.fromkeys(url for url in references if url))[:MAX_RESOURCES]
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="incremento-assets") as pool:
            list(pool.map(self.download, unique))

    def preload_css(self, styles: list[tuple[str, str]]) -> None:
        """Fetch each CSS dependency level together before expanding imports."""
        seen: set[str] = set()
        for _depth in range(_MAX_CSS_DEPTH):
            references, imports = [], []
            for text, base_url in styles:
                for match in _CSS_RESOURCE.finditer(text):
                    token = match.group("target") if match.group("import") else match.group("url")
                    url = self.absolute(_css_target(token), base_url)
                    references.append(url)
                    if match.group("import") and url and url not in seen:
                        seen.add(url)
                        imports.append(url)
            self.preload(references)
            styles = []
            for url in imports:
                value = self.cache.get(url)
                if value and value[0] == "text/css":
                    styles.append((value[1].decode("utf-8-sig", errors="replace"), value[2]))
            if not styles:
                break

    def data_url(self, reference: str, base_url: str, *, css: bool = False, chain: tuple[str, ...] = ()) -> str:
        reference = str(reference or "").strip()
        if reference.startswith("#"):
            return reference
        if reference.casefold().startswith("data:"):
            header = reference.split(",", 1)[0].casefold()
            if len(reference) <= MAX_RESOURCE_BYTES * 2 and (
                header.startswith(("data:image/", "data:font/")) or (css and header.startswith("data:text/css"))
            ):
                self.claim_output(len(reference.encode("utf-8")))
                return reference
            return ""
        url = self.absolute(reference, base_url)
        if url in chain or (css and len(chain) >= _MAX_CSS_DEPTH):
            return ""
        value = self.download(url)
        if value is None:
            return ""
        mime, raw, final_url = value
        if (mime == "text/css") != css:
            return ""
        if css:
            raw = self.css(raw.decode("utf-8-sig", errors="replace"), final_url, chain + (url,)).encode("utf-8")
        prefix = f"data:{mime};base64,"
        self.claim_output(len(prefix) + 4 * ((len(raw) + 2) // 3))
        return prefix + base64.b64encode(raw).decode("ascii")

    def css(self, text: str, base_url: str, chain: tuple[str, ...] = ()) -> str:
        self.claim_output(len(text.encode("utf-8")) + text.count("<") * 3)

        def rewrite(match):
            imported = bool(match.group("import"))
            token = match.group("target") if imported else match.group("url")
            target = self.data_url(_css_target(token), base_url, css=imported, chain=chain)
            if imported:
                return f'@import url("{target}")'
            return f'url("{target}")'

        return _CSS_RESOURCE.sub(rewrite, text).replace("<", "\\3c ")


def build_offline_webpage_html(html: str, base_url: str, *, timeout_sec: float = 30.0) -> str:
    """Capture bounded CSS, fonts, and images before an offline-only Qt render.

    Every request uses the public-network client, including CDN assets and CSS
    imports. Original site styles and print media rules remain in document order.
    """
    html_bytes = len(html.encode("utf-8"))
    if html_bytes > MAX_HTML_BYTES:
        raise ValueError("Webpage HTML exceeds the size limit.")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "iframe", "object", "embed", "base", "noscript", "template"]):
        tag.decompose()
    for meta in soup.find_all("meta"):
        if str(meta.get("http-equiv", "")).casefold() in {"refresh", "content-security-policy"} or meta.has_attr("charset"):
            meta.decompose()
    resources = _Resources(timeout_sec, html_bytes)
    stylesheets = [tag for tag in soup.find_all("link") if "stylesheet" in tag.get("rel", [])]
    images = soup.find_all("img")
    sources = {
        id(img): str(img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "")
        for img in images
    }
    resources.preload([
        resources.absolute(str(tag.get("href") or ""), base_url) for tag in stylesheets
    ])
    css_sources = [(style.get_text(), base_url) for style in soup.find_all("style")]
    css_sources.extend((str(tag["style"]), base_url) for tag in soup.find_all(style=True))
    for link in stylesheets:
        value = resources.cache.get(resources.absolute(str(link.get("href") or ""), base_url))
        if value and value[0] == "text/css":
            css_sources.append((value[1].decode("utf-8-sig", errors="replace"), value[2]))
    resources.preload_css(css_sources)
    # Rewrite existing inline CSS before inserting the captured stylesheets.
    for style in soup.find_all("style"):
        style.string = resources.css(style.get_text(), base_url)
    for link in soup.find_all("link"):
        if link not in stylesheets:
            link.decompose()
            continue
        url = resources.absolute(str(link.get("href") or ""), base_url)
        value = resources.download(url)
        if not value or value[0] != "text/css":
            link.decompose()
            continue
        style = soup.new_tag("style")
        if link.get("media"):
            style["media"] = link["media"]
        style.string = resources.css(value[1].decode("utf-8-sig", errors="replace"), value[2], (url,))
        link.replace_with(style)
    for tag in soup.find_all(style=True):
        tag["style"] = resources.css(str(tag["style"]), base_url)
    # Preserve layout and icon fonts before optional photos consume the budget.
    resources.preload([resources.absolute(sources[id(img)], base_url) for img in images])
    for img in images:
        source = resources.data_url(sources[id(img)], base_url)
        for key in ("src", "srcset", "sizes", "loading", "data-src", "data-srcset", "data-lazy-src"):
            img.attrs.pop(key, None)
        if source:
            img["src"] = source
    for source in soup.find_all("source"):
        source.decompose()  # <picture> falls back to its captured <img>.
    for tag in soup.find_all(True):
        for name in list(tag.attrs):
            if name.casefold().startswith("on") or name.casefold() in {"srcdoc", "nonce", "integrity", "autofocus"}:
                del tag.attrs[name]
        if tag.name == "a" and tag.get("href"):
            href = str(tag["href"])
            target = href if href.startswith("#") else resources.absolute(href, base_url)
            if target:
                tag["href"] = target
            else:
                del tag.attrs["href"]
    if soup.html is None:
        root = soup.new_tag("html")
        body = soup.new_tag("body")
        for element in list(soup.contents):
            body.append(element.extract())
        root.append(body)
        soup.append(root)
    if soup.head is None:
        soup.html.insert(0, soup.new_tag("head"))
    charset = soup.new_tag("meta", charset="utf-8")
    csp = soup.new_tag("meta", attrs={"http-equiv": "Content-Security-Policy", "content": _CSP})
    soup.head.insert(0, csp)
    soup.head.insert(0, charset)
    result = str(soup)
    if len(result.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Webpage snapshot exceeds the size limit.")
    return result
