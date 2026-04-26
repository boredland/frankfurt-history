#!/usr/bin/env python3
"""Deep-merge data/ with overrides/ into content/ for the web app build.

For each locale (de, en):
1. Copy all markdown from data/<lang>/<theme>/ as the base
2. Apply overrides from overrides/<lang>/<theme>/ on top:
   - Frontmatter fields in the override replace same fields from data
   - If override has body content, it replaces the full body
   - If override only has frontmatter (no body), original body is kept
3. For structural fields (coordinates, categories, filters), DE overrides
   apply to EN too unless an EN-specific override exists for that field
4. Override-only files (no corresponding data file) are included as-is

Also handles the flat layout fallback (data/<theme>/ without lang prefix).
"""

import os
import re
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OVERRIDES_DIR = Path(__file__).resolve().parent.parent / "overrides"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"

STRUCTURAL_FIELDS = {"coordinates", "categories", "filters", "id"}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.index("---", 3)
    fm_block = text[3:end].strip()
    body = text[end + 3:].strip()
    fm: dict[str, str] = {}
    current_key = ""
    current_val_lines: list[str] = []

    def flush():
        if current_key:
            fm[current_key] = "\n".join(current_val_lines)

    for line in fm_block.splitlines():
        if re.match(r"^[a-zA-Z_]\w*:", line):
            flush()
            key, _, val = line.partition(":")
            current_key = key.strip()
            current_val_lines = [val.strip()]
        elif current_key and line.startswith("  "):
            current_val_lines.append(line)
        else:
            flush()
            current_key = ""
            current_val_lines = []
    flush()
    return fm, body


def serialize_frontmatter(fm: dict[str, str], body: str) -> str:
    lines = ["---"]
    for key, val in fm.items():
        if "\n" in val:
            lines.append(f"{key}:")
            for vline in val.split("\n"):
                if vline.strip():
                    lines.append(vline)
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append("")
    if body:
        lines.append(body)
    return "\n".join(lines) + "\n"


def merge_file(base_path: Path, override_path: Path | None) -> str:
    base_text = base_path.read_text() if base_path.exists() else ""
    if not override_path or not override_path.exists():
        return base_text

    override_text = override_path.read_text()
    base_fm, base_body = parse_frontmatter(base_text)
    override_fm, override_body = parse_frontmatter(override_text)

    merged_fm = dict(base_fm)
    for key, val in override_fm.items():
        if val == "null":
            merged_fm.pop(key, None)
        else:
            merged_fm[key] = val

    merged_body = override_body if override_body else base_body
    return serialize_frontmatter(merged_fm, merged_body)


def merge_lang(lang: str):
    """Merge data and overrides for one language."""
    # Determine source directories
    data_lang_dir = DATA_DIR / lang
    if not data_lang_dir.is_dir():
        data_lang_dir = DATA_DIR  # flat layout fallback

    override_lang_dir = OVERRIDES_DIR / lang
    de_override_dir = OVERRIDES_DIR / "de" if lang != "de" else None
    content_lang_dir = CONTENT_DIR / lang

    if content_lang_dir.exists():
        shutil.rmtree(content_lang_dir)

    theme_dirs = set()
    if data_lang_dir.is_dir():
        for d in data_lang_dir.iterdir():
            if d.is_dir() and d.name not in ("images", "de", "en"):
                theme_dirs.add(d.name)
    if override_lang_dir.is_dir():
        for d in override_lang_dir.iterdir():
            if d.is_dir():
                theme_dirs.add(d.name)

    total = 0
    for theme_slug in sorted(theme_dirs):
        data_theme = data_lang_dir / theme_slug
        override_theme = override_lang_dir / theme_slug if override_lang_dir.is_dir() else None
        de_override_theme = de_override_dir / theme_slug if de_override_dir and de_override_dir.is_dir() else None

        dest = content_lang_dir / theme_slug
        dest.mkdir(parents=True, exist_ok=True)

        # Collect all markdown files from data + overrides
        md_files: set[str] = set()
        if data_theme.is_dir():
            for f in data_theme.glob("*.md"):
                md_files.add(f.name)
        if override_theme and override_theme.is_dir():
            for f in override_theme.glob("*.md"):
                md_files.add(f.name)

        for filename in sorted(md_files):
            base = data_theme / filename if data_theme.is_dir() else Path("/nonexistent")
            override = (override_theme / filename) if override_theme and (override_theme / filename).exists() else None

            # For non-DE langs, apply structural DE overrides if no lang-specific override
            if not override and de_override_theme and (de_override_theme / filename).exists():
                de_override = de_override_theme / filename
                de_fm, _ = parse_frontmatter(de_override.read_text())
                structural_only = {k: v for k, v in de_fm.items() if k in STRUCTURAL_FIELDS}
                if structural_only and base.exists():
                    base_fm, base_body = parse_frontmatter(base.read_text())
                    for k, v in structural_only.items():
                        if v == "null":
                            base_fm.pop(k, None)
                        else:
                            base_fm[k] = v
                    (dest / filename).write_text(serialize_frontmatter(base_fm, base_body))
                    total += 1
                    continue

            merged = merge_file(base, override)
            if merged:
                (dest / filename).write_text(merged)
                total += 1

    print(f"  {lang}: {total} files")


def main():
    print("Merging data + overrides → content/")

    for lang in ("de", "en"):
        merge_lang(lang)

    # Also handle flat layout (data/<theme>/ without lang prefix)
    has_flat = any(
        d.is_dir() and d.name not in ("images", "de", "en")
        for d in DATA_DIR.iterdir()
        if d.is_dir()
    )
    if has_flat:
        flat_content = CONTENT_DIR
        for theme_dir in sorted(DATA_DIR.iterdir()):
            if not theme_dir.is_dir() or theme_dir.name in ("images", "de", "en"):
                continue
            dest = flat_content / theme_dir.name
            dest.mkdir(parents=True, exist_ok=True)
            override_theme = OVERRIDES_DIR / "de" / theme_dir.name if (OVERRIDES_DIR / "de").is_dir() else None
            count = 0
            for md in sorted(theme_dir.glob("*.md")):
                override = (override_theme / md.name) if override_theme and (override_theme / md.name).exists() else None
                merged = merge_file(md, override)
                if merged:
                    (dest / md.name).write_text(merged)
                    count += 1
            print(f"  flat/{theme_dir.name}: {count} files")

    print("Done.")


if __name__ == "__main__":
    main()
