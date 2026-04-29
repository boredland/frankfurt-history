#!/usr/bin/env python3
"""Download Stolperstein images via Wayback Machine and prepare for R2 sync.

Reads image URLs from data/stolpersteine/*.md articles, downloads them
via Wayback Machine (no CF protection), stores in data/images/stolpersteine/,
and rewrites the markdown to use relative paths that geojson.py converts to R2 URLs.

Usage:
    uv run scripts/download_stolperstein_images.py
"""

import hashlib
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
THEME_DIR = DATA_DIR / "stolpersteine"
IMG_DIR = DATA_DIR / "images" / "stolpersteine"
IMG_PROXY = os.environ.get("IMG_PROXY_URL", "https://history.jonas-strassel.de/img")
UA = "Mozilla/5.0 (compatible; FrankfurtHistoryBot/1.0)"
WORKERS = 8

_start = time.monotonic()


def log(msg: str):
    m, s = divmod(int(time.monotonic() - _start), 60)
    print(f"[{m:02d}:{s:02d}] {msg}", flush=True)


def url_to_filename(url: str) -> str:
    """Deterministic filename from URL."""
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    name = url.split("/")[-1].split("?")[0]
    name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
    if len(name) > 60:
        name = name[:60]
    return f"{h}_{name}{'' if name.endswith(ext) else ext}"


def download_image(url: str) -> str | None:
    """Download an image via the CF image proxy. Returns local filename or None."""
    filename = url_to_filename(url)
    out_path = IMG_DIR / filename
    if out_path.exists() and out_path.stat().st_size > 100:
        return filename

    proxy_url = f"{IMG_PROXY}/w=800,f=auto/{url}"
    req = urllib.request.Request(proxy_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        if len(data) < 100:
            return None
        out_path.write_bytes(data)
        return filename
    except Exception:
        return None


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all unique image URLs from stolperstein articles
    url_refs: dict[str, list[tuple[Path, str]]] = {}
    for md_file in sorted(THEME_DIR.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        text = md_file.read_text()
        for m in re.finditer(r"!\[([^\]]*)\]\((https://frankfurt\.de/[^)]+)\)", text):
            alt, url = m.group(1), m.group(2)
            url_refs.setdefault(url, []).append((md_file, alt))

    log(f"{len(url_refs)} unique images to download")

    # Download in parallel
    ok = 0
    fail = 0
    url_to_file: dict[str, str] = {}

    urls = list(url_refs.keys())
    for batch_start in range(0, len(urls), WORKERS * 5):
        batch = urls[batch_start: batch_start + WORKERS * 5]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(download_image, url): url for url in batch}
            for future in as_completed(futures):
                url = futures[future]
                filename = future.result()
                if filename:
                    url_to_file[url] = filename
                    ok += 1
                else:
                    fail += 1

        done = batch_start + len(batch)
        if done % 100 < WORKERS * 5 or done >= len(urls):
            log(f"  {done}/{len(urls)} — {ok} ok, {fail} failed")

    log(f"Downloaded: {ok}, Failed: {fail}")

    # Rewrite markdown files to use relative image paths
    rewritten = 0
    for url, refs in url_refs.items():
        filename = url_to_file.get(url)
        if not filename:
            continue
        rel_path = f"../../images/stolpersteine/{filename}"
        for md_file, alt in refs:
            text = md_file.read_text()
            new_text = text.replace(f"]({url})", f"]({rel_path})")
            if new_text != text:
                md_file.write_text(new_text)
                rewritten += 1

    log(f"Rewrote {rewritten} image references in markdown files")


if __name__ == "__main__":
    main()
