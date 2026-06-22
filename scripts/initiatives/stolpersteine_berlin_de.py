"""Initiative scraper for stolpersteine-berlin.de.

Site is Drupal 10 with stable, well-structured markup. Bio pages live at
``/de/<street-slug>/<housenumber>/<person-slug>``; the OSM ``website`` tag
points straight at those URLs.

Page structure (German page):

    <h1 class="biografie">Bela Friede geb. Wendriner</h1>

    <div class="st-table">
        <div class="st-table-row">
            <div class="st-col-label">Verlegeort</div>
            <div class="st-col-data">Aachener Str. 4</div>
        </div>
        ... Bezirk/Ortsteil, Verlegedatum, Geboren, Deportation, Später deportiert, Ermordet ...
    </div>

    <div class="biography-image"> <a href="/sites/default/files/..."> <img alt="caption" />

    <div class="field_bio">
        <article> <div class="text"> <div class="field__item"> ...bio text... </div>

    <div class="author-public">Stolpersteine-Initiative Charlottenburg-Wilmersdorf</div>

English page sometimes exists at the same path under ``/en/``; when absent
Drupal serves the German content with the URL prefix swapped. We treat a
returned English body as English only if it differs from the German body.
"""

from __future__ import annotations

import html as html_mod
import re
import time
import urllib.error
import urllib.request
from typing import Optional

UA = "FrankfurtHistoryBot/1.0 (https://history.jonas-strassel.de)"
HOST = "stolpersteine-berlin.de"
SOURCE_KEY = "stolpersteine_berlin_de"
REQUEST_TIMEOUT = 20
RETRY_WAIT_S = 3


# ---------- HTTP ----------

SOFT_404_MARKER = "Die Seite wurde nicht gefunden"


def _fetch_raw(url: str, retries: int = 2) -> str | None:
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de;q=0.9,en;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last_err = e
        except Exception as e:
            last_err = e
        if attempt < retries:
            time.sleep(RETRY_WAIT_S)
    return None


def _is_soft_404(html: str) -> bool:
    return SOFT_404_MARKER in html[:4000]


def _url_variants(url: str) -> list[str]:
    """Generate plausible URL alternates for the slug variations the OSM website tag misses.

    The site uses ``-str`` instead of ``-strasse`` for a small number of streets, and
    sometimes capitalisation/encoding differs. Try the OSM URL first, then a couple
    of fallbacks before giving up."""
    out = [url]
    if "strasse" in url:
        out.append(url.replace("strasse", "str"))
    if "-str/" in url or "-str-" in url:
        out.append(url.replace("-str/", "-strasse/").replace("-str-", "-strasse-"))
    # Deduplicate, preserve order.
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _fetch(url: str, retries: int = 2) -> tuple[str | None, str | None]:
    """Fetch the page, trying URL variants on soft-404. Returns (html, final_url)."""
    for candidate in _url_variants(url):
        html = _fetch_raw(candidate, retries=retries)
        if html and not _is_soft_404(html):
            return html, candidate
    return None, None


# ---------- Parsing helpers ----------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(s: str) -> str:
    return _WS_RE.sub(" ", html_mod.unescape(_TAG_RE.sub("", s))).strip()


def _find_main(html: str) -> str:
    m = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL)
    return m.group(1) if m else html


def _extract_table_fields(main: str) -> dict[str, str]:
    """Walk the .st-table rows and return {label: text-value}."""
    fields: dict[str, str] = {}
    # Each row has a col-label followed by col-data.
    for row in re.finditer(
        r'<div[^>]*class="[^"]*st-table-row[^"]*"[^>]*>(.*?)</div>\s*</div>',
        main, re.DOTALL,
    ):
        block = row.group(1)
        label_m = re.search(r'class="[^"]*st-col-label[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        data_m = re.search(r'class="[^"]*st-col-data[^"]*"[^>]*>(.*?)</div>\s*$', block, re.DOTALL)
        if not label_m:
            continue
        label = _strip_tags(label_m.group(1))
        value = _strip_tags(data_m.group(1)) if data_m else ""
        if not value:
            # Sometimes the closing isn't matched by the lazy regex; fall back to greedy.
            data_m2 = re.search(r'class="[^"]*st-col-data[^"]*"[^>]*>(.*)', block, re.DOTALL)
            if data_m2:
                value = _strip_tags(data_m2.group(1))
        if label:
            fields[label] = value
    return fields


def _extract_bio_text(main: str) -> str:
    """Extract the long-form biography body (preserves paragraph breaks)."""
    m = re.search(
        r'<div[^>]*class="[^"]*field_bio[^"]*"[^>]*>(.*?)<hr',
        main, re.DOTALL,
    )
    if not m:
        # Fallback: capture content of class="text" inside field_bio area.
        m = re.search(
            r'<div[^>]*class="[^"]*field__item"[^>]*>(.*?)</div>\s*</div>\s*</article>',
            main, re.DOTALL,
        )
        if not m:
            return ""
        body = m.group(1)
    else:
        body = m.group(1)
        # Drill to the field__item inside.
        item = re.search(r'<div[^>]*class="[^"]*field__item[^"]*"[^>]*>(.*?)</div>\s*</div>',
                         body, re.DOTALL)
        if item:
            body = item.group(1)
    # Drop links but keep their text.
    body = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', body, flags=re.DOTALL)
    # Paragraphs: replace <br>, </p>, </div> with newlines before stripping tags.
    body = re.sub(r"<\s*br\s*/?\s*>", "\n", body, flags=re.I)
    body = re.sub(r"</p\s*>", "\n\n", body, flags=re.I)
    body = re.sub(r"</div\s*>", "\n", body, flags=re.I)
    text = html_mod.unescape(_TAG_RE.sub("", body))
    # Collapse 3+ newlines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_images(main: str, base_url: str) -> list[dict]:
    """Pull images from .biography-image (gallery), preserving captions and resolving to full URLs."""
    images: list[dict] = []
    gallery_m = re.search(
        r'<div[^>]*class="[^"]*biography-image[^"]*"[^>]*>(.*?)</article>',
        main, re.DOTALL,
    )
    if not gallery_m:
        return images
    block = gallery_m.group(1)
    # Each slide: <a href="/sites/default/files/styles/wide/public/..."> ... <img alt="..." />
    # Also a caption may live in <div class="slide__caption">...</div>
    for slide in re.finditer(
        r'<li[^>]*class="[^"]*splide__slide[^"]*"[^>]*>(.*?)</li>',
        block, re.DOTALL,
    ):
        slide_html = slide.group(1)
        href_m = re.search(r'<a[^>]+href="([^"]*/sites/default/files/[^"]+)"', slide_html)
        url = href_m.group(1) if href_m else None
        if not url:
            # Fall back to data-src on <img>.
            img_m = re.search(r'<img[^>]+data-src="([^"]+)"', slide_html)
            if img_m:
                url = img_m.group(1)
        if not url:
            continue
        if url.startswith("/"):
            url = f"https://www.{HOST}{url}"
        # Strip Drupal image-style derivative path and the (expiring) itok query
        # so we end up with the canonical original.
        url = re.sub(r"/sites/default/files/styles/[^/]+/public/",
                     "/sites/default/files/", url)
        url = re.sub(r"\?itok=.*$", "", url)
        cap_m = re.search(r'class="slide__caption"[^>]*>(.*?)</div>', slide_html, re.DOTALL)
        caption = _strip_tags(cap_m.group(1)) if cap_m else ""
        if not caption:
            alt_m = re.search(r'<img[^>]+alt="([^"]*)"', slide_html)
            caption = html_mod.unescape(alt_m.group(1)) if alt_m else ""
        images.append({
            "url": url,
            "caption": caption,
            "source": HOST,
            "kind": "portrait",
        })
    return images


def _extract_author(main: str) -> str:
    m = re.search(
        r'<div[^>]*class="[^"]*author-public[^"]*"[^>]*>(.*?)</div>',
        main, re.DOTALL,
    )
    return _strip_tags(m.group(1)) if m else ""


# ---------- Field interpreters ----------

_MONTHS_DE = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
}


def _parse_german_date(s: str) -> str | None:
    """'24. November 1887' → '1887-11-24'. Returns ISO yyyy-mm-dd or None."""
    m = re.search(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})", s)
    if not m:
        return None
    d, month_de, y = m.group(1), m.group(2), m.group(3)
    month = _MONTHS_DE.get(month_de)
    if not month:
        return None
    return f"{int(y):04d}-{month:02d}-{int(d):02d}"


def _parse_geboren(value: str) -> dict:
    """'24. November 1887 in Berlin' → {birth_date: ..., birth_place: 'Berlin'}."""
    out: dict[str, str] = {}
    date = _parse_german_date(value)
    if date:
        out["birth_date"] = date
    place_m = re.search(r"\bin\s+(.+)$", value)
    if place_m:
        out["birth_place"] = place_m.group(1).strip()
    return out


def _parse_deportation(value: str) -> dict:
    """'am 26. Januar 1943 nach Theresienstadt' → {date, destination}."""
    out: dict[str, str] = {}
    date = _parse_german_date(value)
    if date:
        out["date"] = date
    dest_m = re.search(r"\bnach\s+(.+?)(?:\s*$|\s+am\s)", value)
    if dest_m:
        out["destination"] = dest_m.group(1).strip()
    return out


# ---------- Public API ----------

class Scraper:
    host = HOST
    source_key = SOURCE_KEY

    def can_handle(self, url: str) -> bool:
        return HOST in (url or "")

    def fetch(self, record: dict) -> Optional[dict]:
        url = (record.get("refs") or {}).get("website") or ""
        if not self.can_handle(url):
            return None

        html, final_url = _fetch(url)
        if not html:
            return None
        # The actual URL we landed on may differ from the OSM-provided one; track it.
        url = final_url or url

        main = _find_main(html)
        fields = _extract_table_fields(main)
        text = _extract_bio_text(main)
        images = _extract_images(main, url)
        author = _extract_author(main)

        # Person/address updates from the table fields.
        person_updates: dict = {}
        address_updates: dict = {}

        if "Geboren" in fields:
            person_updates.update(_parse_geboren(fields["Geboren"]))

        if "Bezirk/Ortsteil" in fields:
            address_updates["district"] = fields["Bezirk/Ortsteil"]

        deportations: list[dict] = []
        for label in ("Deportation", "Später deportiert", "Spätere Deportation", "Weiter deportiert"):
            if label in fields:
                d = _parse_deportation(fields[label])
                if d:
                    deportations.append(d)
        if deportations:
            person_updates["deportations"] = deportations

        # The fate label is one of several possible keys; the value (if any) holds
        # context like " in Auschwitz" or "1934 Schweiz". Order matters — most
        # specific first.
        for fate_label in ("Ermordet", "Tot", "Überlebt", "Flucht", "Suizid", "Selbstmord", "Verschollen"):
            if fate_label not in fields:
                continue
            person_updates["fate"] = fate_label
            tail = fields[fate_label].strip()
            if tail.startswith("in "):
                person_updates["death_place"] = tail[3:].strip()
            elif fate_label == "Flucht" and tail:
                person_updates["flight"] = tail
            break

        # Laying date.
        if "Verlegedatum" in fields:
            laying = _parse_german_date(fields["Verlegedatum"])
            if laying:
                # Returned via extras; the dispatcher decides whether to overwrite record["laying_date"].
                pass

        biographies: list[dict] = []
        if text:
            bio_entry = {
                "source": HOST,
                "source_url": url,
                "lang": "de",
                "text": text,
            }
            if author:
                bio_entry["author"] = author
            biographies.append(bio_entry)

        result: dict = {
            "biographies": biographies,
            "images": images,
            "person_updates": person_updates,
            "address_updates": address_updates,
            "extras": {
                "table_fields": fields,
                "laying_date_iso": _parse_german_date(fields.get("Verlegedatum", "")) if "Verlegedatum" in fields else None,
            },
        }
        return result
