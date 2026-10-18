"""Bounded, in-memory handoff from a waiting Anki dialog to its browser tab."""
import re
import secrets
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

try:
    from .content_safety import normalize_external_http_url
except ImportError:
    from content_safety import normalize_external_http_url

HANDOFF_PATH = "/incremento/webpage-pdf"
HANDOFF_RPC_PATH = "/incremento/webpage-pdf-handoff"
HANDOFF_SECONDS = 600
MAX_HTML_CHARS = 2_000_000
ARCHIVE_HOSTS = {"archive.is", "archive.ph", "archive.today", "archive.md", "archive.li", "archive.fo", "archive.vn"}


class WebpageVerificationRequired(RuntimeError):
    pass


class _ChallengeText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.text = []
        self.in_title = False
        self.ignored = 0
        self.challenge_form = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if tag == "title":
            self.in_title = True
        values = dict(attrs)
        marker = str(values.get("id", "")) + " " + str(values.get("class", ""))
        if tag == "input" and str(values.get("type", "")).lower() == "password":
            self.challenge_form = True
        if re.search(r"\b(?:captcha-form|challenge-form|sgcaptcha|cf-challenge|captcha)\b", marker, re.I):
            self.challenge_form = True

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.ignored:
            return
        self.text.append(data)
        if self.in_title:
            self.title.append(data)


def requires_verification(html: str) -> bool:
    parser = _ChallengeText()
    parser.feed(html[:MAX_HTML_CHARS])
    title = " ".join(" ".join(parser.title).lower().split())
    text = " ".join(" ".join(parser.text).lower().split())
    if re.match(r"^(?:just a moment|attention required|security check|access denied|captcha\b|verify (?:you|that)|sign in\b|log in\b|login\b)", title):
        return True
    return len(text) < 2000 and (parser.challenge_form or bool(re.search(
        r"(?:verify|confirm|checking).{0,50}(?:human|not a robot|your browser)|complete (?:the )?captcha|too many requests", text,
    )))


def same_handoff_site(original: str, current: str) -> bool:
    first, second = urlsplit(normalize_external_http_url(original)), urlsplit(normalize_external_http_url(current))
    if (first.path.rstrip("/"), first.query) != (second.path.rstrip("/"), second.query):
        return False
    if (first.scheme, first.hostname, first.port) == (second.scheme, second.hostname, second.port):
        return True
    return (first.scheme == second.scheme == "https" and first.port == second.port
            and first.hostname in ARCHIVE_HOSTS and second.hostname in ARCHIVE_HOSTS)


class BrowserPdfHandoffs:
    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._jobs = {}
        self._lock = threading.Lock()

    def _job(self, ticket):
        job = self._jobs.get(ticket) if isinstance(ticket, str) else None
        if job is None or job["expires"] <= self._clock():
            if isinstance(ticket, str):
                self._jobs.pop(ticket, None)
            raise ValueError("Browser PDF request is no longer pending.")
        return job

    def create(self, url: str, profile: str) -> str:
        url = normalize_external_http_url(url)
        with self._lock:
            self._jobs = {key: value for key, value in self._jobs.items() if value["expires"] > self._clock()}
            if len(self._jobs) >= 4:
                raise ValueError("Too many pending browser PDF requests.")
            ticket = secrets.token_hex(32)
            self._jobs[ticket] = {"url": url, "profile": profile, "expires": self._clock() + HANDOFF_SECONDS,
                                  "state": "waiting", "html": ""}
            return ticket

    def describe(self, ticket: str) -> dict:
        with self._lock:
            job = self._job(ticket)
            return {"ok": True, "url": job["url"], "remainingSeconds": max(1, int(job["expires"] - self._clock()))}

    def submit(self, ticket: str, url: str, html: str) -> None:
        if not isinstance(html, str) or not html.strip() or len(html) > MAX_HTML_CHARS:
            raise ValueError("Invalid browser HTML snapshot.")
        if requires_verification(html):
            raise ValueError("Browser verification is still required.")
        with self._lock:
            job = self._job(ticket)
            if not same_handoff_site(job["url"], url):
                raise ValueError("Browser page does not match the waiting import.")
            if job["state"] == "waiting":
                job.update(state="ready", html=html)

    def fail(self, ticket: str) -> None:
        with self._lock:
            job = self._job(ticket)
            if job["state"] == "waiting":
                job["state"] = "failed"

    def take(self, ticket: str, profile: str) -> str | None:
        with self._lock:
            job = self._job(ticket)
            if job["profile"] != profile:
                raise ValueError("Browser PDF request belongs to another profile.")
            if job["state"] == "failed":
                raise ValueError("Browser PDF capture did not finish.")
            if job["state"] != "ready":
                return None
            html = job["html"]
            job.update(state="consumed", html="")
            return html

    def cancel(self, ticket: str) -> None:
        with self._lock:
            self._jobs.pop(ticket, None)

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


browser_pdf_handoffs = BrowserPdfHandoffs()
