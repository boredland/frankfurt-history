#!/usr/bin/env python3
"""Archive Frankfurt History app content (texts, images, metadata) from its API."""

import html
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from bs4 import BeautifulSoup

API_BASE = "https://api.frankfurthistory.app"
AUTH_PARAMS = {
    "grant_type": "password",
    "username": "app@karlmax-berlin.com",
    "password": "EZD\\s8>6%vf!Vn[ZH",
    "client_id": "2",
    "client_secret": "hioRnHjbH5E0N3dMxmQzSRTjRjL35FDVy9TiaR9p",
}

OUT_DIR = Path("data")
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "medium")
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2


def get_token(client: httpx.Client) -> str:
    resp = client.post(f"{API_BASE}/oauth/token", data=AUTH_PARAMS)
    resp.raise_for_status()
    return resp.json()["access_token"]


def api_get(client: httpx.Client, path: str) -> dict:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.get(f"{API_BASE}/{path}")
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"  Retry {attempt + 1} for {path}: {e}")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise


def download_image(client: httpx.Client, url: str, dest: Path) -> bool:
    if dest.exists():
        return False
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"  Failed to download {url}: {e}")
                return False


def image_local_path(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(unquote(url))
    name = Path(parsed.path).name
    return f"images/{name}" if name else None


def best_image_url(img_data, prefer: str = IMAGE_SIZE) -> str | None:
    """Extract the preferred image URL. Falls back through: prefer → large → original → any."""
    if not img_data or not isinstance(img_data, dict):
        return None
    by_type = {}
    for u in img_data.get("urls", []):
        if isinstance(u, dict) and u.get("url"):
            by_type[u.get("type", "")] = u["url"]
    for t in (prefer, "large", "original", "small"):
        if t in by_type:
            return by_type[t]
    return next(iter(by_type.values()), None)


def html_to_markdown(body: str) -> str:
    if not body:
        return ""
    body = body.replace("­", "")
    soup = BeautifulSoup(body, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.insert_before("\n")
        p.insert_after("\n")
    text = soup.get_text()
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def collect_image_urls(poi: dict) -> list[str]:
    """Collect only the best (original) image URL from each image content."""
    urls = []

    def add_from(img_data):
        url = best_image_url(img_data)
        if url:
            urls.append(url)

    add_from(poi.get("thumbnail"))
    for key in ("galleryContents", "interactiveGalleryContents"):
        for gallery in poi.get(key, []):
            if not isinstance(gallery, dict):
                continue
            add_from(gallery.get("thumbnail"))
            for img in gallery.get("images", []):
                add_from(img)
    for key in ("audioContents", "videoContents"):
        for item in poi.get(key, []):
            if isinstance(item, dict):
                add_from(item.get("thumbnail"))

    return urls


def meta_str(meta: dict | None) -> str:
    if not meta or not isinstance(meta, dict):
        return ""
    parts = []
    author = (meta.get("author") or "").strip()
    if author:
        parts.append(f"Author: {author}")
    copyright_ = (meta.get("copyright") or "").strip()
    if copyright_:
        parts.append(f"License: {copyright_}")
    desc = (meta.get("description") or "").strip()
    if desc:
        parts.append(f"Description: {desc}")
    return " | ".join(parts)


def image_markdown(img_data, prefix: str = "") -> str:
    """Render an image content object as a markdown image reference."""
    if not img_data or not isinstance(img_data, dict):
        return ""
    url = best_image_url(img_data)
    if not url:
        return ""
    local = image_local_path(url)
    meta = img_data.get("metadata")
    alt = ""
    if meta and isinstance(meta, dict):
        alt = (meta.get("description") or meta.get("title") or "").strip()
    date_str = (img_data.get("dateString") or "").strip()
    caption_parts = []
    if date_str:
        caption_parts.append(date_str)
    m = meta_str(meta)
    if m:
        caption_parts.append(m)
    lines = []
    if local:
        lines.append(f"{prefix}![{alt}](../{local})")
    if caption_parts:
        lines.append(f"{prefix}*{' — '.join(caption_parts)}*")
    return "\n".join(lines)


def yaml_escape(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    if any(c in s for c in ":{}[]#&*!|>',@`"):
        return f'"{s}"'
    return f'"{s}"'


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[äÄ]", "ae", text)
    text = re.sub(r"[öÖ]", "oe", text)
    text = re.sub(r"[üÜ]", "ue", text)
    text = re.sub(r"[ß]", "ss", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def poi_to_markdown(poi: dict) -> str:
    title = (poi.get("title") or "").strip()
    subtitle = (poi.get("subtitle") or "").strip()
    description = (poi.get("description") or "").strip()
    lat = poi.get("lat")
    lng = poi.get("lng")
    updated = poi.get("updatedAt", "")

    lines = ["---"]
    lines.append(f"id: {poi['id']}")
    lines.append(f"title: {yaml_escape(title)}")
    if subtitle:
        lines.append(f"subtitle: {yaml_escape(subtitle)}")
    if lat is not None and lng is not None:
        lines.append(f"coordinates: [{lat}, {lng}]")
    if updated:
        lines.append(f"updated_at: {yaml_escape(updated)}")

    categories = []
    for cat in poi.get("categories", []):
        cat_title = (cat.get("title") or "").strip()
        cat_sub = (cat.get("subtitle") or "").strip()
        if cat_title:
            categories.append(f"{cat_title} {cat_sub}".strip())
    if categories:
        lines.append("categories:")
        for c in categories:
            lines.append(f"  - {yaml_escape(c)}")

    filters = []
    for f in poi.get("filters", []):
        ft = (f.get("title") or "").strip()
        if ft:
            filters.append(ft)
    if filters:
        lines.append("filters:")
        for f in filters:
            lines.append(f"  - {yaml_escape(f)}")

    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    if subtitle and subtitle != title:
        lines.append(f"\n*{subtitle}*")
    if description and description != subtitle and description != title:
        lines.append(f"\n{description}")

    # Thumbnail
    thumb_md = image_markdown(poi.get("thumbnail"))
    if thumb_md:
        lines.append(f"\n{thumb_md}")

    # Texts
    text_contents = sorted(
        poi.get("textContents", []), key=lambda x: x.get("pos", 0)
    )
    for tc in text_contents:
        body = html_to_markdown(tc.get("body", ""))
        if not body:
            continue
        lines.append(f"\n{body}")
        m = meta_str(tc.get("metadata"))
        if m:
            lines.append(f"\n*{m}*")

    # Galleries
    for key, heading in [
        ("galleryContents", "Gallery"),
        ("interactiveGalleryContents", "Before & After"),
    ]:
        galleries = sorted(
            poi.get(key, []), key=lambda x: x.get("pos", 0) if isinstance(x, dict) else 0
        )
        for gc in galleries:
            if not isinstance(gc, dict):
                continue
            gallery_type = gc.get("type", "gallery")
            images = gc.get("images", [])
            if not images:
                continue
            label = heading
            if gallery_type == "timeline":
                label = "Timeline"
            elif gallery_type == "beforeAfter":
                label = "Before & After"
            elif gallery_type == "interactiveBeforeAfter":
                label = "Interactive Before & After"
            lines.append(f"\n## {label}\n")
            for img in images:
                md = image_markdown(img)
                if md:
                    lines.append(md)
                    lines.append("")

    # Audio
    audios = sorted(
        poi.get("audioContents", []), key=lambda x: x.get("pos", 0) if isinstance(x, dict) else 0
    )
    if audios:
        lines.append("\n## Audio\n")
        for ac in audios:
            if not isinstance(ac, dict):
                continue
            src = (ac.get("src") or "").strip()
            meta = ac.get("metadata", {})
            atitle = ""
            if isinstance(meta, dict):
                atitle = (meta.get("title") or "").strip()
            if src:
                lines.append(f"- [{atitle or 'Audio'}]({src})")
                m = meta_str(meta)
                if m:
                    lines.append(f"  *{m}*")

    # Video
    videos = sorted(
        poi.get("videoContents", []), key=lambda x: x.get("pos", 0) if isinstance(x, dict) else 0
    )
    if videos:
        lines.append("\n## Video\n")
        for vc in videos:
            if not isinstance(vc, dict):
                continue
            src = (vc.get("src") or "").strip()
            vimeo = (vc.get("vimeoId") or "").strip()
            meta = vc.get("metadata", {})
            vtitle = ""
            if isinstance(meta, dict):
                vtitle = (meta.get("title") or "").strip()
            if vimeo:
                lines.append(f"- [{vtitle or 'Video'}](https://vimeo.com/{vimeo})")
            elif src:
                lines.append(f"- [{vtitle or 'Video'}]({src})")
            m = meta_str(meta)
            if m:
                lines.append(f"  *{m}*")

    # Links
    link_contents = poi.get("linkContents", [])
    if link_contents:
        lines.append("\n## Links\n")
        for lc in link_contents:
            if not isinstance(lc, dict):
                continue
            url = (lc.get("url") or "").strip()
            lt = (lc.get("title") or "").strip()
            if url:
                lines.append(f"- [{lt or url}]({url})")

    return "\n".join(lines) + "\n"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(timeout=60, follow_redirects=True)

    print("Authenticating...")
    token = get_token(client)
    client.headers["Authorization"] = f"Bearer {token}"

    print("Fetching themes...")
    themes_resp = api_get(client, "themes")
    themes = themes_resp["data"]
    print(f"Found {len(themes)} themes")

    all_image_urls: list[tuple[str, Path]] = []
    total_pois = 0

    for theme in themes:
        tid = theme["id"]
        tslug = slugify(theme["title"])
        theme_dir = OUT_DIR / tslug
        theme_dir.mkdir(parents=True, exist_ok=True)

        # Theme index
        theme_md = f"""---
id: {tid}
title: {yaml_escape(theme['title'])}
short_title: {yaml_escape(theme.get('shortTitle', ''))}
---

# {theme['title']}

{(theme.get('description') or '').strip()}
"""
        (theme_dir / "_index.md").write_text(theme_md)

        print(f"\nFetching POIs for theme {tid}: {theme['title']}...")
        pois_resp = api_get(client, f"themes/{tid}/pois")
        raw_pois = pois_resp["data"]
        print(f"  {len(raw_pois)} POIs")

        for poi in raw_pois:
            poi_id = poi["id"]
            poi_slug = slugify(poi.get("title") or str(poi_id))
            filename = f"{poi_id:04d}-{poi_slug}.md"

            md = poi_to_markdown(poi)
            (theme_dir / filename).write_text(md)

            for url in collect_image_urls(poi):
                local = image_local_path(url)
                if local:
                    all_image_urls.append((url, OUT_DIR / local))

        total_pois += len(raw_pois)
        print(f"  Wrote {len(raw_pois)} markdown files to {theme_dir}/")

        print(f"  Fetching tours for theme {tid}...")
        tours_resp = api_get(client, f"themes/{tid}/tours")
        raw_tours = tours_resp["data"]
        if raw_tours:
            tours_lines = ["---", f"theme_id: {tid}", "---", "", "# Tours", ""]
            for tour in raw_tours:
                t_title = (tour.get("title") or "").strip()
                t_sub = (tour.get("subtitle") or "").strip()
                t_desc = (tour.get("description") or "").strip()
                t_dur = tour.get("duration")
                tours_lines.append(f"## {t_title}")
                if t_sub:
                    tours_lines.append(f"*{t_sub}*")
                if t_dur:
                    tours_lines.append(f"Duration: {t_dur} min")
                if t_desc:
                    tours_lines.append(f"\n{t_desc}")
                tours_lines.append("")
            (theme_dir / "_tours.md").write_text("\n".join(tours_lines) + "\n")
            print(f"  {len(raw_tours)} tours")

    # Deduplicate images
    unique_images = {}
    for url, dest in all_image_urls:
        key = str(dest)
        if key not in unique_images:
            unique_images[key] = (url, dest)

    print(f"\n--- Summary ---")
    print(f"Themes: {len(themes)}")
    print(f"POIs: {total_pois}")
    print(f"Unique images to download: {len(unique_images)}")
    print(f"\nDownloading images...")

    downloaded = 0
    skipped = 0
    failed = 0
    for i, (url, dest) in enumerate(unique_images.values()):
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{len(unique_images)}")
        result = download_image(client, url, dest)
        if result:
            downloaded += 1
        elif dest.exists():
            skipped += 1
        else:
            failed += 1

    print(f"\nImages: {downloaded} new, {skipped} cached, {failed} failed")
    print("Done.")
    client.close()


if __name__ == "__main__":
    main()
