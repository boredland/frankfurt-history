#!/usr/bin/env python3
"""Archive Frankfurt History app content (texts, images, metadata) from its API."""

import html
import json
import os
import re
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# filename → source API URL, written to data/images.json at the end
IMAGE_MANIFEST: dict[str, str] = {}

API_BASE = "https://api.frankfurthistory.app"
AUTH_PARAMS = {
    "grant_type": "password",
    "username": "app@karlmax-berlin.com",
    "password": "EZD\\s8>6%vf!Vn[ZH",
    "client_id": "2",
    "client_secret": "hioRnHjbH5E0N3dMxmQzSRTjRjL35FDVy9TiaR9p",
}

OUT_DIR = Path("data")
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "original")
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



def image_local_path(url: str) -> str | None:
    if not url:
        return None
    path = url.split("?")[0].split("#")[0]
    name = path.rsplit("/", 1)[-1]
    if not name:
        return None
    return f"images/{name}"


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



def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def meta_str(meta: dict | None) -> str:
    if not meta or not isinstance(meta, dict):
        return ""
    parts = []
    author = strip_tags(meta.get("author") or "")
    if author:
        parts.append(f"Author: {author}")
    copyright_ = strip_tags(meta.get("copyright") or "")
    if copyright_:
        parts.append(f"License: {copyright_}")
    desc = strip_tags(meta.get("description") or "")
    if desc:
        parts.append(f"Description: {desc}")
    return " | ".join(parts)


def image_markdown(img_data, prefix: str = "", depth: int = 1) -> str:
    """Render an image content object as a markdown image reference."""
    if not img_data or not isinstance(img_data, dict):
        return ""
    url = best_image_url(img_data)
    if not url:
        return ""
    local = image_local_path(url)
    if local:
        filename = local.removeprefix("images/")
        IMAGE_MANIFEST[filename] = url
    meta = img_data.get("metadata")
    alt = ""
    if meta and isinstance(meta, dict):
        alt = strip_tags(meta.get("description") or meta.get("title") or "")
    date_str = (img_data.get("dateString") or "").strip()
    caption_parts = []
    if date_str:
        caption_parts.append(date_str)
    m = meta_str(meta)
    if m:
        caption_parts.append(m)
    up = "../" * depth
    lines = []
    if local:
        lines.append(f"{prefix}![{alt}]({up}{local})")
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


def poi_to_markdown(poi: dict, depth: int = 1) -> str:
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
    thumb_md = image_markdown(poi.get("thumbnail"), depth=depth)
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
    for key in ("galleryContents", "interactiveGalleryContents"):
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

            if gallery_type in ("beforeAfter", "interactiveBeforeAfter"):
                before_img = images.get("before") if isinstance(images, dict) else None
                after_img = images.get("after") if isinstance(images, dict) else None
                if not before_img and not after_img:
                    continue
                lines.append("\n## Before & After\n")
                lines.append("<!-- gallery:before-after -->")
                if before_img:
                    md = image_markdown(before_img, depth=depth)
                    if md:
                        lines.append(md)
                        lines.append("")
                if after_img:
                    md = image_markdown(after_img, depth=depth)
                    if md:
                        lines.append(md)
                        lines.append("")
            elif gallery_type == "timeline":
                lines.append("\n## Timeline\n")
                lines.append("<!-- gallery:timeline -->")
                for img in images if isinstance(images, list) else []:
                    md = image_markdown(img, depth=depth)
                    if md:
                        lines.append(md)
                        lines.append("")
            else:
                lines.append("\n## Gallery\n")
                lines.append("<!-- gallery:standard -->")
                for img in images if isinstance(images, list) else []:
                    md = image_markdown(img, depth=depth)
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


LANGUAGES = ["de", "en"]


def archive_language(client: httpx.Client, lang: str, themes: list[dict]):
    """Archive all POIs and tours for one language."""
    lang_dir = OUT_DIR / lang
    total_pois = 0

    for theme in themes:
        tid = theme["id"]
        tslug = slugify(theme["title"])
        theme_dir = lang_dir / tslug
        theme_dir.mkdir(parents=True, exist_ok=True)

        theme_md = f"""---
id: {tid}
title: {yaml_escape(theme['title'])}
short_title: {yaml_escape(theme.get('shortTitle', ''))}
---

# {theme['title']}

{(theme.get('description') or '').strip()}
"""
        (theme_dir / "_index.md").write_text(theme_md)

        print(f"  Fetching POIs for theme {tid}: {theme['title']}...")
        client.headers["Accept-Language"] = lang
        pois_resp = api_get(client, f"themes/{tid}/pois")
        raw_pois = pois_resp["data"]
        print(f"    {len(raw_pois)} POIs")

        for poi in raw_pois:
            poi_id = poi["id"]
            poi_slug = slugify(poi.get("title") or str(poi_id))
            filename = f"{poi_id:04d}-{poi_slug}.md"

            md = poi_to_markdown(poi, depth=2)
            (theme_dir / filename).write_text(md)

        total_pois += len(raw_pois)

        client.headers["Accept-Language"] = lang
        tours_resp = api_get(client, f"themes/{tid}/tours")
        raw_tours = tours_resp["data"]
        if raw_tours:
            # Save raw JSON for full tour data (POI sequences, IDs, etc.)
            (theme_dir / "_tours.json").write_text(
                json.dumps(raw_tours, ensure_ascii=False, indent=2) + "\n"
            )

            tours_lines = ["---", f"theme_id: {tid}", "---", "", "# Tours", ""]
            for tour in raw_tours:
                t_id = tour.get("id", "")
                t_title = (tour.get("title") or "").strip()
                t_sub = (tour.get("subtitle") or "").strip()
                t_desc = (tour.get("description") or "").strip()
                t_dur = tour.get("duration")
                poi_ids = [p.get("id") for p in tour.get("pois", [])]
                tours_lines.append(f"## {t_title}")
                tours_lines.append(f"ID: {t_id}")
                if t_sub:
                    tours_lines.append(f"*{t_sub}*")
                if t_dur:
                    tours_lines.append(f"Duration: {t_dur}s")
                if poi_ids:
                    tours_lines.append(f"POIs: {', '.join(str(p) for p in poi_ids)}")
                if t_desc:
                    tours_lines.append(f"\n{t_desc}")
                tours_lines.append("")
            (theme_dir / "_tours.md").write_text("\n".join(tours_lines) + "\n")

    print(f"  {lang}: {total_pois} POIs total")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(timeout=60, follow_redirects=True)

    print("Authenticating...")
    token = get_token(client)
    client.headers["Authorization"] = f"Bearer {token}"

    print("Fetching themes...")
    themes_resp = api_get(client, "themes")
    themes = themes_resp["data"]
    print(f"Found {len(themes)} themes\n")

    for lang in LANGUAGES:
        print(f"[{lang}] Archiving...")
        archive_language(client, lang, themes)

    # Write image manifest: filename → source URL
    manifest_path = OUT_DIR / "images.json"
    manifest_path.write_text(
        json.dumps(IMAGE_MANIFEST, indent=2, ensure_ascii=False) + "\n"
    )

    print(f"\n--- Summary ---")
    print(f"Languages: {', '.join(LANGUAGES)}")
    print(f"Themes: {len(themes)}")
    print(f"Images: {len(IMAGE_MANIFEST)} unique")
    print("Done.")
    client.close()


if __name__ == "__main__":
    main()
