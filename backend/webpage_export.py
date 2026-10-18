"""Presentation choices for webpage PDFs, independent of the printing engine."""

from html import escape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

MAX_HTML_BYTES = 16 * 1024 * 1024
_ARTICLE_CSS = """@page { size: A4; margin: 18mm 17mm; }
html { color-scheme: light; }
body { margin: 0 auto; max-width: 760px; color: #202735; background: white;
       font: 12pt/1.65 Georgia, 'Times New Roman', serif; overflow-wrap: anywhere; }
h1,h2,h3,h4,h5,h6 { font-family: Arial, sans-serif; line-height: 1.22;
                    break-after: avoid; color: #172b45; }
h1 { font-size: 27pt; margin: 0 0 .65em; letter-spacing: -.025em; }
h2 { font-size: 19pt; margin-top: 1.5em; } h3 { font-size: 15pt; }
p { orphans: 3; widows: 3; } a { color: #175b99; text-decoration: underline; }
img,svg { max-width: 100%; height: auto; } figure { margin: 1.4em 0; }
figcaption { color: #596575; font: 10pt/1.5 Arial, sans-serif; margin-top: .5em; }
blockquote { border-left: 3px solid #b7c9dd; margin: 1.2em 0; padding: 0 1em; }
pre { white-space: pre-wrap; background: #f3f5f7; padding: 1em; font-size: 10pt; }
table { border-collapse: collapse; width: 100%; font-size: 10pt; }
th,td { border: 1px solid #d5dce4; padding: .45em; text-align: start; }
thead { display: table-header-group; } tr,figure { break-inside: avoid; }
.incremento-source { color: #596575; font: 9pt/1.5 Arial, sans-serif;
                    border-bottom: 1px solid #d5dce4; padding-bottom: 1em; margin-bottom: 2em; }
#incremento-link-list { break-before: page; font: 10pt/1.6 Arial, sans-serif; }
"""


def _target(reference: str, base_url: str) -> str:
    if reference.startswith("#"):
        return reference
    try:
        result = urljoin(base_url, reference)
        parts = urlsplit(result)
        if parts.scheme.lower() in {"http", "https"} and parts.hostname and not parts.username and not parts.password:
            return result
    except ValueError:
        pass
    return ""


def prepare_export_html(html: str, base_url: str, *, style: str, include_links: bool = False,
                        links_heading: str = "Links") -> str:
    """Keep the site's layout or put its main article in a readable print template."""
    if style not in {"print", "website", "article"}:
        raise ValueError("Unknown webpage PDF style.")
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("Webpage HTML exceeds the size limit.")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    canonical_title = soup.find("meta", attrs={"property": "og:title"})
    canonical_title = str(canonical_title.get("content") or "").strip() if canonical_title else ""
    if style == "article":
        for tag in soup.select('script,style,link,iframe,object,embed,nav,aside,form,footer,noscript,template,[hidden],[aria-hidden="true"],[role="navigation"],'
                               '#comments,.comments-area,.comment-list,.comment-respond,.comments-wrapper,.share-buttons,.social-share,.post-navigation,.related-posts,.more-wrap'):
            tag.decompose()
        candidates = soup.select("article,main,[role=main],.entry-content,.post-content,.article-content")
        def score(tag):
            return len(tag.get_text(" ", strip=True)) - sum(len(a.get_text()) for a in tag.find_all("a")) * .5
        root = max(candidates, key=score) if candidates else (soup.body or soup)
        heading = root.find("h1")
        title = canonical_title or (heading.get_text(" ", strip=True) if heading else title)
        if heading and canonical_title:
            heading.clear()
            heading.string = canonical_title
        for item in root.find_all("li"):
            if not item.get_text(strip=True) and not item.find(["img", "svg"]):
                item.decompose()
        for listing in root.find_all(["ul", "ol"]):
            if not listing.find("li"):
                listing.decompose()
        # Original classes/inline CSS can hide text or impose narrow site columns.
        for tag in [root, *root.find_all(True)]:
            for attr in ("style", "class", "width", "height"):
                tag.attrs.pop(attr, None)
            for attr in list(tag.attrs):
                if attr.lower().startswith("on"):
                    tag.attrs.pop(attr, None)
        body = str(root)
        if not heading and title:
            body = f"<h1>{escape(title)}</h1>" + body
        source = _target(base_url, "")
        source_line = f'<div class="incremento-source"><a href="{escape(source, quote=True)}">{escape(source)}</a></div>' if source else ""
        soup = BeautifulSoup(f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>'
                             f'<style>{_ARTICLE_CSS}</style></head><body>{source_line}{body}</body></html>', "html.parser")
    for details in soup.find_all("details"):
        details["open"] = ""
    links = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        target = _target(str(anchor["href"]), base_url)
        if target:
            anchor["href"] = target
            if not target.startswith("#") and target != base_url and target not in seen and len(links) < 500:
                seen.add(target)
                links.append(target)
        else:
            del anchor["href"]
    for image in soup.find_all("img"):
        reference = str(image.get("data-src") or image.get("data-lazy-src") or image.get("src") or "")
        target = reference if reference.startswith("data:image/") else _target(reference, base_url)
        if target:
            image["src"] = target
    if include_links and links:
        appendix = soup.new_tag("section", id="incremento-link-list")
        heading = soup.new_tag("h2")
        heading.string = links_heading
        appendix.append(heading)
        listing = soup.new_tag("ol")
        for target in links:
            item = soup.new_tag("li")
            anchor = soup.new_tag("a", href=target)
            anchor.string = target
            item.append(anchor)
            listing.append(item)
        appendix.append(listing)
        (soup.body or soup).append(appendix)
    return str(soup)
