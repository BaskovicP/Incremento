import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


_BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "body",
    "div",
    "figure",
    "figcaption",
    "footer",
    "form",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_VOID_TAGS = {"br", "hr", "img", "input", "meta", "link"}
_ALWAYS_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "canvas", "iframe"}
_MAIN_SCOPE_SKIP_TAGS = {"aside", "footer", "form", "header", "nav"}
_NOISE_RE = re.compile(
    r"(cookie|banner|promo|advert|sidebar|comment|related|share|social|footer|header|menu|nav|subscribe)",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def _normalize_http_url(raw_url: str) -> str:
    raw = str(raw_url or "").strip()
    if not raw:
        raise ValueError("Missing URL.")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")
    return raw


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "_Node | None" = None

    def add_child(self, child) -> None:
        self.children.append(child)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs) -> None:
        clean_tag = str(tag or "").lower()
        node = _Node(
            clean_tag,
            {str(key or "").lower(): str(value or "") for key, value in attrs},
            parent=self._stack[-1],
        )
        self._stack[-1].add_child(node)
        if clean_tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs) -> None:
        clean_tag = str(tag or "").lower()
        node = _Node(
            clean_tag,
            {str(key or "").lower(): str(value or "") for key, value in attrs},
            parent=self._stack[-1],
        )
        self._stack[-1].add_child(node)

    def handle_endtag(self, tag) -> None:
        clean_tag = str(tag or "").lower()
        for idx in range(len(self._stack) - 1, 0, -1):
            if self._stack[idx].tag == clean_tag:
                del self._stack[idx:]
                break

    def handle_data(self, data) -> None:
        if not data:
            return
        self._stack[-1].add_child(str(data))


def _collapse_ws(value: str) -> str:
    return _WS_RE.sub(" ", str(value or "")).strip()


def _node_text(node) -> str:
    if isinstance(node, str):
        return _collapse_ws(node)
    parts = []
    for child in node.children:
        text = _node_text(child)
        if text:
            parts.append(text)
    return _collapse_ws(" ".join(parts))


def _find_first(node: _Node, predicate):
    if predicate(node):
        return node
    for child in node.children:
        if isinstance(child, _Node):
            found = _find_first(child, predicate)
            if found is not None:
                return found
    return None


def _iter_nodes(node: _Node):
    yield node
    for child in node.children:
        if isinstance(child, _Node):
            yield from _iter_nodes(child)


def _looks_hidden(node: _Node) -> bool:
    hidden = str(node.attrs.get("hidden", "")).strip()
    style = str(node.attrs.get("style", "")).lower()
    aria = str(node.attrs.get("aria-hidden", "")).lower()
    return bool(hidden) or "display:none" in style.replace(" ", "") or aria == "true"


def _is_noise_node(node: _Node, content_scope: str) -> bool:
    if node.tag in _ALWAYS_SKIP_TAGS:
        return True
    if _looks_hidden(node):
        return True
    if content_scope != "main":
        return False
    if node.tag in _MAIN_SCOPE_SKIP_TAGS:
        return True
    attrs_blob = " ".join(
        [
            node.attrs.get("id", ""),
            node.attrs.get("class", ""),
            node.attrs.get("role", ""),
            node.attrs.get("aria-label", ""),
            node.attrs.get("data-testid", ""),
        ]
    )
    return bool(_NOISE_RE.search(attrs_blob))


def _count_tag(node: _Node, tag_name: str) -> int:
    total = 1 if node.tag == tag_name else 0
    for child in node.children:
        if isinstance(child, _Node):
            total += _count_tag(child, tag_name)
    return total


def _candidate_score(node: _Node) -> int:
    text = _node_text(node)
    text_len = len(text)
    if text_len == 0:
        return 0
    paragraphs = _count_tag(node, "p")
    headings = sum(_count_tag(node, f"h{level}") for level in range(1, 7))
    list_items = _count_tag(node, "li")
    links = _count_tag(node, "a")
    return text_len + paragraphs * 120 + headings * 80 + list_items * 40 - links * 20


def _pick_content_root(root: _Node, content_scope: str) -> _Node:
    body = _find_first(root, lambda node: node.tag == "body") or root
    if content_scope == "full":
        return body

    candidates = []
    for node in _iter_nodes(body):
        if _is_noise_node(node, content_scope):
            continue
        role = str(node.attrs.get("role", "")).lower()
        if node.tag in {"article", "main"} or role == "main":
            candidates.append(node)
            continue
        if node.tag in {"section", "div"} and _candidate_score(node) >= 800:
            candidates.append(node)
    if not candidates:
        return body
    best = max(candidates, key=_candidate_score)
    if _candidate_score(best) < 320:
        return body
    return best


def _render_inline(node, base_url: str) -> str:
    if isinstance(node, str):
        return _collapse_ws(node)

    if node.tag in _ALWAYS_SKIP_TAGS:
        return ""

    if node.tag == "br":
        return "\n"
    if node.tag == "code":
        inner = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        return f"`{inner}`" if inner else ""
    if node.tag in {"strong", "b"}:
        inner = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        return f"**{inner}**" if inner else ""
    if node.tag in {"em", "i"}:
        inner = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        return f"*{inner}*" if inner else ""
    if node.tag == "a":
        href = _collapse_ws(node.attrs.get("href", ""))
        inner = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        target = urljoin(base_url, href) if href else ""
        if inner and target:
            return f"[{inner}]({target})"
        return inner or target
    if node.tag == "img":
        src = _collapse_ws(node.attrs.get("src", ""))
        if not src:
            return ""
        alt = _collapse_ws(node.attrs.get("alt", ""))
        return f"![{alt}]({urljoin(base_url, src)})"

    parts = []
    for child in node.children:
        part = _render_inline(child, base_url)
        if part:
            parts.append(part)
    return _collapse_ws(" ".join(parts))


def _render_list(node: _Node, base_url: str, ordered: bool, level: int, content_scope: str) -> str:
    lines = []
    item_index = 1
    for child in node.children:
        if not isinstance(child, _Node) or child.tag != "li":
            continue
        body_parts = []
        nested_parts = []
        for grandchild in child.children:
            if isinstance(grandchild, _Node) and grandchild.tag in {"ul", "ol"}:
                nested = _render_list(
                    grandchild,
                    base_url,
                    grandchild.tag == "ol",
                    level + 1,
                    content_scope,
                ).strip("\n")
                if nested:
                    nested_parts.append(nested)
                continue
            if isinstance(grandchild, _Node) and grandchild.tag in _BLOCK_TAGS:
                piece = _render_block(grandchild, base_url, content_scope, level + 1).strip()
            else:
                piece = _render_inline(grandchild, base_url)
            if piece:
                body_parts.append(piece)
        item_text = _collapse_ws(" ".join(body_parts))
        prefix = f"{item_index}. " if ordered else "- "
        indent = "  " * level
        if item_text:
            lines.append(f"{indent}{prefix}{item_text}")
        for nested in nested_parts:
            nested_lines = nested.splitlines()
            lines.extend(nested_lines)
        item_index += 1
    return "\n".join(lines) + ("\n\n" if lines else "")


def _render_block(node: _Node, base_url: str, content_scope: str, level: int = 0) -> str:
    if isinstance(node, str):
        text = _collapse_ws(node)
        return f"{text}\n\n" if text else ""

    if _is_noise_node(node, content_scope):
        return ""

    if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        text = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        if not text:
            return ""
        heading_level = int(node.tag[1])
        return f"{'#' * heading_level} {text}\n\n"

    if node.tag == "p":
        text = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        return f"{text}\n\n" if text else ""

    if node.tag == "blockquote":
        inner = "".join(_render_block(child, base_url, content_scope, level + 1) for child in node.children).strip()
        if not inner:
            inner = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        if not inner:
            return ""
        prefixed = "\n".join(f"> {line}" if line.strip() else ">" for line in inner.splitlines())
        return f"{prefixed}\n\n"

    if node.tag == "pre":
        raw = "".join(_node_text(child) if isinstance(child, _Node) else str(child) for child in node.children).strip("\n")
        return f"```\n{raw}\n```\n\n" if raw.strip() else ""

    if node.tag == "hr":
        return "---\n\n"

    if node.tag == "ul":
        return _render_list(node, base_url, False, level, content_scope)

    if node.tag == "ol":
        return _render_list(node, base_url, True, level, content_scope)

    if node.tag == "table":
        rows = []
        for row in node.children:
            if not isinstance(row, _Node) or row.tag not in {"tr", "thead", "tbody"}:
                continue
            row_nodes = row.children if row.tag in {"thead", "tbody"} else [row]
            for row_node in row_nodes:
                if not isinstance(row_node, _Node) or row_node.tag != "tr":
                    continue
                cols = []
                for cell in row_node.children:
                    if not isinstance(cell, _Node) or cell.tag not in {"th", "td"}:
                        continue
                    cell_text = _collapse_ws(" ".join(_render_inline(child, base_url) for child in cell.children))
                    cols.append(cell_text)
                if cols:
                    rows.append(" | ".join(cols))
        return "\n".join(rows) + ("\n\n" if rows else "")

    if node.tag == "img":
        inline = _render_inline(node, base_url)
        return f"{inline}\n\n" if inline else ""

    if node.tag == "li":
        text = _collapse_ws(" ".join(_render_inline(child, base_url) for child in node.children))
        return f"- {text}\n\n" if text else ""

    pieces = []
    inline_parts = []
    for child in node.children:
        if isinstance(child, _Node) and child.tag in _BLOCK_TAGS:
            piece = _render_block(child, base_url, content_scope, level)
            if piece:
                pieces.append(piece)
        else:
            inline = _render_inline(child, base_url)
            if inline:
                inline_parts.append(inline)
    if inline_parts:
        pieces.insert(0, _collapse_ws(" ".join(inline_parts)) + "\n\n")
    return "".join(pieces)


def _clean_markdown(text: str) -> str:
    lines = [line.rstrip() for line in str(text or "").splitlines()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_document_title(root: _Node, fallback: str = "") -> str:
    title_node = _find_first(root, lambda node: node.tag == "title")
    if title_node is not None:
        title = _node_text(title_node)
        if title:
            return title
    h1_node = _find_first(root, lambda node: node.tag == "h1")
    if h1_node is not None:
        title = _node_text(h1_node)
        if title:
            return title
    return _collapse_ws(fallback) or "Untitled"


def build_webpage_markdown_document(title: str, url: str, markdown: str) -> str:
    clean_title = _collapse_ws(title) or "Untitled"
    clean_url = _normalize_http_url(url)
    clean_markdown = _clean_markdown(markdown)
    lines = [
        f"# {clean_title}",
        "",
        f"Source: {clean_url}",
        "",
    ]
    if clean_markdown:
        lines.extend([clean_markdown, ""])
    return "\n".join(lines).rstrip() + "\n"


def convert_webpage_html_to_markdown(
    url: str,
    html: str,
    *,
    title: str = "",
    content_scope: str = "main",
) -> dict:
    clean_url = _normalize_http_url(url)
    clean_html = str(html or "").strip()
    scope = "full" if str(content_scope or "").strip().lower() == "full" else "main"
    if not clean_html:
        raise ValueError("Webpage HTML is empty.")

    parser = _TreeBuilder()
    parser.feed(clean_html)
    parser.close()

    resolved_title = _extract_document_title(parser.root, fallback=title)
    content_root = _pick_content_root(parser.root, scope)
    markdown = _clean_markdown(_render_block(content_root, clean_url, scope))
    if not markdown:
        markdown = _clean_markdown(_node_text(content_root))
    if not markdown:
        raise ValueError("Could not extract readable content from the webpage.")
    return {
        "title": resolved_title,
        "markdown": markdown,
        "markdown_document": build_webpage_markdown_document(resolved_title, clean_url, markdown),
    }


def fetch_webpage_markdown(
    url: str,
    *,
    content_scope: str = "main",
    timeout_sec: float = 20.0,
) -> dict:
    clean_url = _normalize_http_url(url)
    req = Request(
        clean_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=max(1.0, float(timeout_sec))) as resp:
        content_type = str(resp.headers.get("Content-Type") or "").lower()
        raw_bytes = resp.read()
        charset = ""
        if "charset=" in content_type:
            charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    if not raw_bytes:
        raise RuntimeError("Webpage download returned an empty response.")
    encoding = charset or "utf-8"
    try:
        html = raw_bytes.decode(encoding, errors="replace")
    except LookupError:
        html = raw_bytes.decode("utf-8", errors="replace")
    result = convert_webpage_html_to_markdown(
        clean_url,
        html,
        content_scope=content_scope,
    )
    result["url"] = clean_url
    return result
