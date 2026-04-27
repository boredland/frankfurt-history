#!/usr/bin/env python3
"""Build GeoJSON feature collections and theme index from archived markdown."""

import json
import os
import re
import shutil
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MERGED_DIR = Path(__file__).resolve().parent.parent / "content"
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "public" / "data"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "app" / "public" / "data" / "content"

R2_PUBLIC_URL = os.environ.get(
    "R2_PUBLIC_URL", "https://pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev"
)
ADDRESS_CACHE = DATA_DIR / "addresses.json"


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    fm = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            if inner.strip():
                items = [v.strip().strip('"').strip("'") for v in inner.split(",")]
                try:
                    fm[key] = [float(x) for x in items]
                except ValueError:
                    fm[key] = items
            else:
                fm[key] = []
        elif val.startswith('"') and val.endswith('"'):
            fm[key] = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            fm[key] = val[1:-1]
        else:
            try:
                fm[key] = int(val)
            except ValueError:
                try:
                    fm[key] = float(val)
                except ValueError:
                    fm[key] = val
    if key == "categories" or key == "filters":
        pass
    return fm


def parse_yaml_list(path: Path, field: str) -> list[str]:
    """Parse a YAML list field that spans multiple lines (indented `- value`)."""
    text = path.read_text()
    if not text.startswith("---"):
        return []
    end = text.index("---", 3)
    fm_text = text[3:end]
    items = []
    in_field = False
    for line in fm_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            in_field = True
            continue
        if in_field:
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                items.append(val)
            elif stripped and not stripped.startswith("-"):
                break
    return items


def build_theme(theme_dir: Path, addresses: dict[str, str] | None = None) -> tuple[dict | None, dict | None]:
    index_path = theme_dir / "_index.md"
    if not index_path.exists():
        return None, None

    theme_fm = parse_frontmatter(index_path)
    theme_slug = theme_dir.name
    theme_id = theme_fm.get("id")
    theme_title = theme_fm.get("title", theme_slug)
    short_title = theme_fm.get("short_title", "")

    features = []
    for poi_path in sorted(theme_dir.glob("*.md")):
        if poi_path.name.startswith("_"):
            continue
        fm = parse_frontmatter(poi_path)
        coords = fm.get("coordinates", [])
        if not coords or len(coords) < 2:
            continue

        lat, lng = coords[0], coords[1]
        if lat == 0 and lng == 0:
            continue
        if not (49.5 < lat < 50.5 and 8.0 < lng < 9.5):
            print(f"    SKIP {poi_path.stem}: bad coordinates [{lat}, {lng}]")
            continue

        categories = parse_yaml_list(poi_path, "categories")
        filters = parse_yaml_list(poi_path, "filters")

        if any(f.startswith("Orte mit mehreren") for f in filters):
            continue

        slug = poi_path.stem

        # Extract first image URL for thumbnail
        thumb = ""
        body = poi_path.read_text()
        img_match = re.search(r"!\[[^\]]*\]\(([^)]+)\)", body)
        if img_match:
            thumb = img_match.group(1)
            thumb = re.sub(r"(\.\./)+images/", f"{R2_PUBLIC_URL}/images/", thumb)

        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "id": fm.get("id", 0),
                "title": fm.get("title", ""),
                "subtitle": fm.get("subtitle", ""),
                "theme": theme_slug,
                "slug": slug,
            },
        }
        if thumb:
            feature["properties"]["thumb"] = thumb
        if addresses:
            addr_key = f"{lat:.6f},{lng:.6f}"
            addr = addresses.get(addr_key, "")
            if addr:
                feature["properties"]["address"] = addr
        if categories:
            feature["properties"]["categories"] = categories
        if filters:
            feature["properties"]["filters"] = filters

        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}

    theme_meta = {
        "id": theme_id,
        "title": theme_title,
        "short_title": short_title,
        "slug": theme_slug,
        "poi_count": len(features),
    }

    return theme_meta, geojson


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load address cache if available
    addresses = None
    if ADDRESS_CACHE.exists():
        addresses = json.loads(ADDRESS_CACHE.read_text())
        print(f"Loaded {len(addresses)} cached addresses")

    # Prefer merged content/ (includes overrides) over raw data/
    geojson_source = MERGED_DIR if MERGED_DIR.is_dir() else DATA_DIR

    themes = []
    total = 0

    for theme_dir in sorted(geojson_source.iterdir()):
        if not theme_dir.is_dir() or theme_dir.name in ("images", "de", "en"):
            continue
        theme_meta, geojson = build_theme(theme_dir, addresses)
        if not theme_meta:
            continue

        out_path = OUT_DIR / f"{theme_dir.name}.geojson"
        out_path.write_text(json.dumps(geojson, ensure_ascii=False) + "\n")
        themes.append(theme_meta)
        total += theme_meta["poi_count"]
        print(f"  {theme_dir.name}: {theme_meta['poi_count']} POIs with coordinates")

    # Also check <source>/de/ layout
    de_dir = geojson_source / "de"
    if not de_dir.is_dir():
        de_dir = DATA_DIR / "de"
    if de_dir.is_dir():
        for theme_dir in sorted(de_dir.iterdir()):
            if not theme_dir.is_dir():
                continue
            if any(t["slug"] == theme_dir.name for t in themes):
                continue
            theme_meta, geojson = build_theme(theme_dir, addresses)
            if not theme_meta:
                continue
            out_path = OUT_DIR / f"{theme_dir.name}.geojson"
            out_path.write_text(json.dumps(geojson, ensure_ascii=False) + "\n")
            themes.append(theme_meta)
            total += theme_meta["poi_count"]
            print(f"  {theme_dir.name}: {theme_meta['poi_count']} POIs with coordinates")

    themes.sort(key=lambda t: -(t.get("poi_count", 0)))
    (OUT_DIR / "themes.json").write_text(
        json.dumps(themes, indent=2, ensure_ascii=False) + "\n"
    )

    # Post-process: mark stacked POIs (address match + 5m radius fallback)
    tolerance_lat = 0.000045
    tolerance_lng = 0.00007
    all_features = []
    geojson_files = {}
    for gj_path in sorted(OUT_DIR.glob("*.geojson")):
        data = json.loads(gj_path.read_text())
        geojson_files[gj_path.name] = data
        for f in data["features"]:
            coords = f["geometry"]["coordinates"]
            all_features.append({
                "lng": coords[0], "lat": coords[1],
                "address": f["properties"].get("address", ""),
                "slug": f["properties"]["slug"],
            })

    stacked_slugs = set()
    for i, a in enumerate(all_features):
        for j, b in enumerate(all_features):
            if i >= j:
                continue
            address_match = a["address"] and b["address"] and a["address"] == b["address"]
            coord_match = (
                abs(a["lng"] - b["lng"]) < tolerance_lng and
                abs(a["lat"] - b["lat"]) < tolerance_lat
            )
            if address_match or coord_match:
                stacked_slugs.add(a["slug"])
                stacked_slugs.add(b["slug"])

    stacked_count = 0
    for name, data in geojson_files.items():
        for f in data["features"]:
            if f["properties"]["slug"] in stacked_slugs:
                f["properties"]["stacked"] = True
                stacked_count += 1
        (OUT_DIR / name).write_text(json.dumps(data, ensure_ascii=False) + "\n")

    print(f"  {stacked_count} POIs marked as stacked")

    # Copy markdown files to public/content/, rewriting image paths to R2 URLs
    image_path_re = re.compile(r"(\.\./)+images/")
    if CONTENT_DIR.exists():
        shutil.rmtree(CONTENT_DIR)

    def copy_theme_content(theme_dir: Path, dest_prefix: Path):
        dest = dest_prefix / theme_dir.name
        dest.mkdir(parents=True, exist_ok=True)
        id_index = {}
        for md in theme_dir.glob("*.md"):
            if md.name.startswith("_"):
                continue
            text = md.read_text()
            text = image_path_re.sub(f"{R2_PUBLIC_URL}/images/", text)
            json_name = md.stem + ".json"
            fm, body = {}, text
            if text.startswith("---"):
                end = text.index("---", 3)
                fm_block = text[3:end].strip()
                body = text[end + 3:].strip()
                for line in fm_block.splitlines():
                    if ":" not in line:
                        continue
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip().strip('"').strip("'")
            (dest / json_name).write_text(
                json.dumps({"frontmatter": fm, "body": body}, ensure_ascii=False) + "\n"
            )
            poi_id = re.match(r"(\d+)", md.stem)
            if poi_id:
                id_index[poi_id.group(1)] = json_name
        (dest / "_index.json").write_text(
            json.dumps(id_index, ensure_ascii=False) + "\n"
        )

    # Prefer merged content/ directory (from merge.py), fall back to data/
    source = MERGED_DIR if MERGED_DIR.is_dir() else DATA_DIR

    # Flat layout: source/<theme>/ → public content/<theme>/
    for theme_dir in sorted(source.iterdir()):
        if not theme_dir.is_dir() or theme_dir.name in ("images", "de", "en"):
            continue
        copy_theme_content(theme_dir, CONTENT_DIR)

    # Nested layout: source/<lang>/<theme>/ → public content/<lang>/<theme>/
    for lang in ("de", "en"):
        lang_dir = source / lang
        if not lang_dir.is_dir():
            # Fall back to data/<lang>/ if merged doesn't have it
            lang_dir = DATA_DIR / lang
        if not lang_dir.is_dir():
            continue
        for theme_dir in sorted(lang_dir.iterdir()):
            if not theme_dir.is_dir():
                continue
            copy_theme_content(theme_dir, CONTENT_DIR / lang)

    print(f"\nTotal: {total} POIs across {len(themes)} themes")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
