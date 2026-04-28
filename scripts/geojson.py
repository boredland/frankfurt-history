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
            fm[key] = val[1:-1].replace('\\"', '"')
        elif val.startswith("'") and val.endswith("'"):
            fm[key] = val[1:-1].replace("\\'", "'")
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


def _build_en_lookup(en_dir: Path) -> dict[str, dict]:
    """Build {poi_id: {title, subtitle, filters}} from the English theme directory."""
    lookup = {}
    if not en_dir or not en_dir.is_dir():
        return lookup
    for md in en_dir.glob("*.md"):
        if md.name.startswith("_"):
            continue
        fm = parse_frontmatter(md)
        poi_id = fm.get("id")
        if not poi_id:
            m = re.match(r"(\d+)", md.stem)
            if m:
                poi_id = int(m.group(1))
        if not poi_id:
            continue
        entry = {}
        if fm.get("title"):
            entry["title"] = fm["title"]
        if fm.get("subtitle"):
            entry["subtitle"] = fm["subtitle"]
        filters_en = parse_yaml_list(md, "filters")
        if filters_en:
            entry["filters"] = filters_en
        lookup[int(poi_id)] = entry
    # English theme-level metadata
    idx = en_dir / "_index.md"
    if idx.exists():
        fm = parse_frontmatter(idx)
        if fm.get("title"):
            lookup["_theme_title"] = fm["title"]
        if fm.get("short_title"):
            lookup["_theme_short_title"] = fm["short_title"]
    return lookup


def build_theme(
    theme_dir: Path,
    addresses: dict[str, str] | None = None,
    en_dir: Path | None = None,
) -> tuple[dict | None, dict | None]:
    index_path = theme_dir / "_index.md"
    if not index_path.exists():
        return None, None

    theme_fm = parse_frontmatter(index_path)
    theme_slug = theme_dir.name
    theme_id = theme_fm.get("id")
    theme_title = theme_fm.get("title", theme_slug)
    short_title = theme_fm.get("short_title", "")

    en_lookup = _build_en_lookup(en_dir)

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

        # English translations
        poi_id = fm.get("id", 0)
        en = en_lookup.get(int(poi_id), {}) if poi_id else {}
        if en.get("title"):
            feature["properties"]["title_en"] = en["title"]
        if en.get("subtitle"):
            feature["properties"]["subtitle_en"] = en["subtitle"]
        if en.get("filters"):
            feature["properties"]["filters_en"] = en["filters"]

        addr = ""
        if addresses:
            addr_key = f"{lat:.6f},{lng:.6f}"
            addr = addresses.get(addr_key, "")
        if not addr:
            subtitle = fm.get("subtitle", "")
            if re.search(
                r"(?:straße|strasse|weg|platz|allee|gasse|ring|anlage|pfad|ufer|damm|chaussee)\s*\d",
                subtitle, re.IGNORECASE,
            ):
                addr = subtitle
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
    en_theme_title = en_lookup.get("_theme_title")
    en_short = en_lookup.get("_theme_short_title")
    if en_theme_title:
        theme_meta["title_en"] = en_theme_title
    if en_short:
        theme_meta["short_title_en"] = en_short

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

    # Resolve English directories for translations
    en_base = geojson_source / "en"
    if not en_base.is_dir():
        en_base = DATA_DIR / "en"

    for theme_dir in sorted(geojson_source.iterdir()):
        if not theme_dir.is_dir() or theme_dir.name in ("images", "de", "en"):
            continue
        en_dir = en_base / theme_dir.name if en_base.is_dir() else None
        theme_meta, geojson = build_theme(theme_dir, addresses, en_dir)
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
            en_dir = en_base / theme_dir.name if en_base.is_dir() else None
            theme_meta, geojson = build_theme(theme_dir, addresses, en_dir)
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
    # Use wider tolerance for grouping (15m) so visually overlapping markers
    # from different themes merge into one group with a single primary
    tolerance_lat = 0.000135
    tolerance_lng = 0.00021
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

    # Build adjacency: group POIs that share a location
    from collections import defaultdict
    parent = {f["slug"]: f["slug"] for f in all_features}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def addresses_match(addr_a: str, addr_b: str) -> bool:
        """Match addresses including house number ranges (e.g. 31 matches 29-33)."""
        if not addr_a or not addr_b:
            return False
        if addr_a == addr_b:
            return True
        # Extract street + numbers
        m_a = re.match(r"^(.+?)\s+([\d]+(?:\s*[-–]\s*\d+)?[a-zA-Z]?)$", addr_a)
        m_b = re.match(r"^(.+?)\s+([\d]+(?:\s*[-–]\s*\d+)?[a-zA-Z]?)$", addr_b)
        if not m_a or not m_b:
            return False
        if m_a.group(1).strip().lower() != m_b.group(1).strip().lower():
            return False
        # Parse number/range for each
        def parse_range(s):
            s = re.sub(r"[a-zA-Z]$", "", s.strip())
            parts = re.split(r"\s*[-–]\s*", s)
            try:
                nums = [int(p) for p in parts]
                return (min(nums), max(nums))
            except ValueError:
                return None
        r_a = parse_range(m_a.group(2))
        r_b = parse_range(m_b.group(2))
        if not r_a or not r_b:
            return False
        # Check if ranges overlap
        return r_a[0] <= r_b[1] and r_b[0] <= r_a[1]

    for i, a in enumerate(all_features):
        for j, b in enumerate(all_features):
            if i >= j:
                continue
            address_match = addresses_match(a["address"], b["address"])
            coord_match = (
                abs(a["lng"] - b["lng"]) < tolerance_lng and
                abs(a["lat"] - b["lat"]) < tolerance_lat
            )
            if address_match or coord_match:
                union(a["slug"], b["slug"])

    # Group by root and pick one primary per group
    groups = defaultdict(list)
    for f in all_features:
        root = find(f["slug"])
        groups[root].append(f["slug"])

    # Build slug→theme mapping from the geojson files
    slug_to_theme = {}
    for name, data in geojson_files.items():
        theme_slug = name.replace(".geojson", "")
        for f in data["features"]:
            slug_to_theme[f["properties"]["slug"]] = theme_slug

    stacked_slugs = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        for s in members:
            stacked_slugs.add(s)

    # Pick one primary per theme per group so each theme has a visible marker
    primary_slugs = set()
    slug_to_group = {}
    for root, members in groups.items():
        if len(members) < 2:
            continue
        seen_themes = set()
        for s in members:
            slug_to_group[s] = root
            t = slug_to_theme.get(s)
            if t and t not in seen_themes:
                seen_themes.add(t)
                primary_slugs.add(s)

    # Collect all filters per group per theme for multicolor stacked indicators
    group_theme_filters: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for name, data in geojson_files.items():
        theme_slug = name.replace(".geojson", "")
        for f in data["features"]:
            slug = f["properties"]["slug"]
            grp = slug_to_group.get(slug)
            if grp is None:
                continue
            for filt in f["properties"].get("filters", []):
                if filt not in group_theme_filters[grp][theme_slug]:
                    group_theme_filters[grp][theme_slug].append(filt)

    stacked_count = 0
    hidden_count = 0
    for name, data in geojson_files.items():
        theme_slug = name.replace(".geojson", "")
        for f in data["features"]:
            slug = f["properties"]["slug"]
            if slug in stacked_slugs:
                f["properties"]["stacked"] = True
                stacked_count += 1
                if slug not in primary_slugs:
                    f["properties"]["stackHidden"] = True
                    hidden_count += 1
                else:
                    grp = slug_to_group.get(slug)
                    if grp:
                        all_filters = group_theme_filters[grp].get(theme_slug, [])
                        if len(all_filters) > 1:
                            f["properties"]["stackFilters"] = all_filters
        (OUT_DIR / name).write_text(json.dumps(data, ensure_ascii=False) + "\n")

    print(f"  {stacked_count} POIs stacked, {hidden_count} hidden (1 primary per theme per group)")

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
                    val = v.strip()
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1].replace('\\"', '"')
                    elif val.startswith("'") and val.endswith("'"):
                        val = val[1:-1].replace("\\'", "'")
                    fm[k.strip()] = val
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
