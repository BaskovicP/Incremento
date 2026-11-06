"""Capture an HTML snapshot or an editable reading copy in the EPUB reader."""

from datetime import datetime, timezone
from base64 import b64decode
from pathlib import Path
import re
import time
from urllib.request import Request

from bs4 import BeautifulSoup
import markdown

try:
    from . import markdown_manager
    from .content_safety import normalize_external_http_url, external_plain_text_to_markdown
    from .network_safety import open_public_http, read_response_limited
    from .webpage_markdown import convert_webpage_html_to_markdown
    from .webpage_snapshot import fetch_webpage_html, MAX_WEBPAGE_HTML_BYTES
    from .webpage_resources import _DeadlineResponse, build_offline_webpage_html
    from .webpage_export import prepare_export_html
    from .webpage_handoff import requires_verification, WebpageVerificationRequired
except ImportError:
    import markdown_manager
    from content_safety import normalize_external_http_url, external_plain_text_to_markdown
    from network_safety import open_public_http, read_response_limited
    from webpage_markdown import convert_webpage_html_to_markdown
    from webpage_snapshot import fetch_webpage_html, MAX_WEBPAGE_HTML_BYTES
    from webpage_resources import _DeadlineResponse, build_offline_webpage_html
    from webpage_export import prepare_export_html
    from webpage_handoff import requires_verification, WebpageVerificationRequired


def prepare_webpage_document(url: str, *, html: str = "", title: str = "", content_scope: str = "main",
                             capture_format: str = "markdown", is_cancelled=lambda: False) -> markdown_manager.PreparedMarkdown:
    """No managed writes. Supplied browser HTML is never fetched again.

    All remote images use the ordinary public-network boundary. Missing images
    retain alt text; count/byte limits fail before generating a partial archive.
    """
    def check():
        if is_cancelled():
            raise InterruptedError("Webpage capture cancelled.")

    check()
    url = normalize_external_http_url(url)
    if content_scope not in {"main", "full"}:
        raise ValueError("pageContentScope must be main or full.")
    if capture_format not in {"html", "markdown"}:
        raise ValueError("documentFormat must be html or markdown.")
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_WEBPAGE_HTML_BYTES:
        raise ValueError("Webpage HTML exceeds the size limit.")
    if not html.strip():
        url, html = fetch_webpage_html(url)
    check()
    if requires_verification(html):
        raise WebpageVerificationRequired()
    snapshot_html = None
    captured_at = datetime.now(timezone.utc).isoformat()
    if capture_format == "html":
        # Capture the site itself before deriving optional Markdown/TXT exports.
        content_scope = "full"
        html = build_offline_webpage_html(prepare_export_html(html, url, style="website"), url)
        if len(html.encode("utf-8")) > markdown_manager.MAX_SNAPSHOT_HTML_BYTES:
            raise ValueError("HTML snapshot exceeds the size limit.")
        snapshot = BeautifulSoup(html, "html.parser")
        for name, value in (("incremento-source-url", url), ("incremento-captured-at", captured_at)):
            snapshot.head.append(snapshot.new_tag("meta", attrs={"name": name, "content": value}))
        snapshot_html = html = str(snapshot)
        check()
    return _prepare_captured_content(url, html, title=title, content_scope=content_scope,
        capture_format=capture_format, captured_at=captured_at, check=check, snapshot_html=snapshot_html)


def prepare_edited_webpage_snapshot(prepared, html: str, *, is_cancelled=lambda: False):
    """Rebuild preview edits without reloading the site or changing capture time.

    The rendered DOM is untrusted. Reapply the snapshot policy with network
    access disabled, and derive every export from the same cleaned content.
    The caller retains ownership of the original prepared document.
    """
    capture = dict(prepared.capture or {})
    if capture.get('format') != 'html' or not isinstance(html, str) or not html.strip():
        raise ValueError('An HTML snapshot is required.')
    if len(html.encode('utf-8')) > markdown_manager.MAX_SNAPSHOT_HTML_BYTES:
        raise ValueError('HTML snapshot exceeds the size limit.')
    def check():
        if is_cancelled():
            raise InterruptedError('Webpage capture cancelled.')
    check()
    url = normalize_external_http_url(capture['url'])
    html = build_offline_webpage_html(prepare_export_html(html, url, style='website'), url, timeout_sec=0)
    snapshot = BeautifulSoup(html, 'html.parser')
    for name, value in (('incremento-source-url', url), ('incremento-captured-at', capture['captured_at'])):
        for meta in snapshot.find_all('meta', attrs={'name':name}):
            meta.decompose()
        snapshot.head.append(snapshot.new_tag('meta', attrs={'name':name, 'content':value}))
    html = str(snapshot)
    return _prepare_captured_content(url, html, title=prepared.title, content_scope='full',
        capture_format='html', captured_at=capture['captured_at'], check=check, snapshot_html=html)


def _prepare_captured_content(url, html, *, title, content_scope, capture_format, captured_at, check, snapshot_html=None):
    result = convert_webpage_html_to_markdown(url, html, content_scope=content_scope, include_images=True)
    title = title.strip() or result["title"]
    text = result["markdown"]
    # Use the parsed Markdown, rather than page DOM, to fetch only retained images.
    soup = BeautifulSoup(markdown.markdown(text, extensions=["tables", "fenced_code"]), "html.parser")
    references = list(dict.fromkeys(str(image.get("src") or "") for image in soup.find_all("img")))
    if len(references) > markdown_manager.MAX_IMAGES:
        raise markdown_manager.MarkdownImportError("Webpage has too many images.")
    omitted = sum(not image.get("src") for image in BeautifulSoup(html, "html.parser").find_all("img")) if snapshot_html else 0
    images, assets, total = {}, {}, 0
    deadline = time.monotonic() + 30
    for reference in references:
        check()
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Image capture timed out")
            if reference.startswith("data:image/"):
                encoded = reference.split(",", 1)[1]
                if len(encoded) > 4 * ((markdown_manager.MAX_IMAGE_BYTES + 2) // 3):
                    raise ValueError("Image size limit exceeded")
                data = b64decode(encoded, validate=True)
                if len(data) > markdown_manager.MAX_IMAGE_BYTES:
                    raise ValueError("Image size limit exceeded")
            else:
                if snapshot_html is not None:
                    raise ValueError('Snapshot images must already be embedded.')
                image_url = normalize_external_http_url(reference)
                request = Request(image_url, headers={"User-Agent": "Incremento/1.0", "Accept": "image/*"})
                with open_public_http(request, timeout=max(1, min(5, remaining))) as response:
                    data = read_response_limited(_DeadlineResponse(response, deadline),
                                                 max_bytes=markdown_manager.MAX_IMAGE_BYTES)
            kind = markdown_manager._image_type(data)
            if kind is None:
                raise ValueError("Unsupported image")
        except Exception:
            # Optional images never discard a readable article. Network guards
            # reject unsafe URLs before opening a connection.
            omitted += 1
            continue
        check()
        total += len(data)
        if total > markdown_manager.MAX_TOTAL_IMAGE_BYTES:
            raise markdown_manager.MarkdownImportError("Webpage images exceed the size limit.")
        name = f"images/image-{len(images) + 1}.{kind[0]}"
        images[name] = (data, kind[1])
        assets[reference] = name
    check()
    text = re.sub(r"!\[((?:\\.|[^\]])*)\]\(<([^>\n]*)>\)",
        lambda match: f"![{match[1]}](<{assets[match[2]]}>)" if match[2] in assets else match[1], text)
    assets = {name: name for name in images}
    heading = "# " + external_plain_text_to_markdown(title)
    source = (("" if text.startswith(heading + "\n") else heading + "\n\n") + text + "\n").encode("utf-8")
    capture = {"version": 1, "url": url, "captured_at": captured_at,
               "scope": content_scope, "omitted_images": omitted, "format": capture_format}
    prepared = markdown_manager._prepare_bytes(source, Path("webpage.md"), title=title, embedded_images=images,
                                               assets=assets, original_source=source, capture=capture, snapshot_html=snapshot_html)
    try:
        prepared.preview = markdown_manager.render_markdown_text_preview(source.decode("utf-8"))
        if snapshot_html is not None:
            preview = Path(prepared.path).with_suffix(".html")
            preview.write_text(snapshot_html, encoding="utf-8")
            preview.chmod(0o600)
            prepared.preview_path = str(preview)
        return prepared
    except BaseException:
        prepared.close()
        raise
