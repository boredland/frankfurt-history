"""Initiative scraper for frankfurt.de (Stadt Frankfurt am Main).

The official Stadtportrait pages live under
``frankfurt.de/frankfurt-entdecken-und-erleben/stadtportrait/stadtgeschichte/stolpersteine/``
but the live site is fronted by Cloudflare Turnstile, which blocks bots
with a 403 + "Just a moment..." challenge page. We therefore fetch the
biographies from the Wayback Machine.

URL pattern of an individual biography:

    /stadtgeschichte/stolpersteine/<district-slug>/familien/<bio-slug>

The OSM ``website`` tag and our WFS-derived records both point at these
biography URLs. The bio pages are static HTML with the body inside a
``<div class="contentBox _article…">`` container.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

UA = "FrankfurtHistoryBot/1.0 (https://history.jonas-strassel.de)"
HOST = "frankfurt.de"
SOURCE_KEY = "frankfurt_de"

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_MIN_PAGE_SIZE = 10_000
CDX_TIMEOUT = 8
FETCH_TIMEOUT = 15


# ---------- Wayback resolution ----------

def _submit_to_wayback(url: str) -> None:
    """Best-effort fire-and-forget request to nudge Wayback into snapshotting
    a URL we couldn't find. Doesn't wait or care about the result."""
    import threading

    def _do():
        try:
            req = urllib.request.Request(
                f"https://web.archive.org/save/{url}",
                headers={"User-Agent": UA},
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()


def _resolve_wayback(url: str) -> str | None:
    cdx_url = (
        f"{WAYBACK_CDX}?url={urllib.parse.quote(url, safe='')}"
        f"&output=json&fl=timestamp,statuscode,length&filter=statuscode:200&limit=50"
    )
    req = urllib.request.Request(cdx_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=CDX_TIMEOUT) as resp:
            rows = json.loads(resp.read())
    except Exception:
        return None
    for row in reversed(rows[1:]):
        _ts, _status, length = row
        if int(length) >= WAYBACK_MIN_PAGE_SIZE:
            return f"https://web.archive.org/web/{row[0]}/{url}"
    _submit_to_wayback(url)
    return None


def _fetch(url: str) -> str | None:
    wb = _resolve_wayback(url)
    if not wb:
        return None
    req = urllib.request.Request(wb, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read()
    except Exception:
        return None
    html = data.decode("utf-8", errors="replace")
    if "Just a moment" in html[:1000] or len(html) < 500:
        return None
    return html


# ---------- Parsing ----------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_SKIP_LINES = ("inhalte teilen", "Internal Link", "Stadtplan", "Biographien", "Kontakt")


def _find_article(html: str) -> str | None:
    m = re.search(
        r'class="contentBox _article[^"]*">(.*?)<div[^>]*class="contentBox(?! _article)',
        html, re.DOTALL,
    )
    return m.group(1) if m else None


def _extract_text(article: str) -> str:
    text = re.sub(r"<[^>]+>", "\n", article)
    text = html_mod.unescape(text)
    text = re.sub(r"\n[ \t]*\n", "\n\n", text).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "\n\n".join(
        l for l in lines if not any(p in l for p in _SKIP_LINES) and not l.startswith("©")
    )


def _extract_images(article: str) -> list[dict]:
    """Find direct image URLs (stripping Wayback-Machine prefixes).

    Wayback wraps image src like ``/web/<ts>im_/<original>``; we want only
    the canonical frankfurt.de URL so downstream proxies/caches work."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'src="([^"]*stolpersteine[^"]*\.(?:jpe?g|png))"',
        article, re.IGNORECASE,
    ):
        url = re.sub(r".*/web/\d+(?:im_)?/", "", m.group(1))
        if not url.startswith("https://"):
            continue
        url = url.split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        out.append({
            "url": url,
            "caption": "",
            "source": HOST,
            "kind": "biography",
        })
    return out


# ---------- Public API ----------

class Scraper:
    host = HOST
    source_key = SOURCE_KEY

    def can_handle(self, url: str) -> bool:
        return "frankfurt.de" in (url or "")

    def fetch(self, record: dict) -> Optional[dict]:
        url = (record.get("refs") or {}).get("website") or ""
        if not self.can_handle(url):
            return None
        # Only individual biography URLs are useful — location pages are
        # mostly stone-photo placeholders.
        if "/familien/" not in url:
            return None

        # Light politeness — Wayback's CDX endpoint can rate-limit aggressive callers.
        time.sleep(0.2)

        html = _fetch(url)
        if not html:
            return None
        article = _find_article(html)
        if not article:
            return None

        text = _extract_text(article)
        if not text:
            return None

        return {
            "biographies": [
                {
                    "source": HOST,
                    "source_url": url,
                    "lang": "de",
                    "text": text,
                }
            ],
            "images": _extract_images(article),
            "person_updates": {},
            "address_updates": {},
            "extras": {},
        }
