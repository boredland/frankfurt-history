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


def clean_body(body: str) -> str:
    """Join fragmented paragraphs and replace single newlines with spaces."""
    if not body:
        return ""

    # Strip duplicated title (H1) and subtitle (Italic line) from the top
    lines = body.splitlines()
    while lines:
        line = lines[0].strip()
        if not line:
            lines.pop(0)
            continue
        if line.startswith('# '):
            lines.pop(0)
            continue
        if line.startswith('*') and line.endswith('*') and len(line) < 100:
            lines.pop(0)
            continue
        break

    body = "\n".join(lines).strip()

    # Heuristic for joining lines within a block
    blocks = re.split(r'\n\s*\n', body)
    processed_blocks = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # If it's a structural element (heading, list), keep as is
        if block.startswith('#') or block.startswith('-'):
            processed_blocks.append(block)
            continue

        # Strip filename-like lines (e.g., kueferstrasse-3)
        if re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)+$', block, re.I) and len(block) < 50:
            continue

        # If it's a sequence of images, keep them on separate lines
        if '![' in block:
            lines = block.splitlines()
            new_lines = []
            for line in lines:
                line = line.strip()
                if not line: continue
                if line.startswith('!['):
                    new_lines.append(line)
                else:
                    if new_lines and not new_lines[-1].startswith('!['):
                        new_lines[-1] = f"{new_lines[-1]} {line}"
                    else:
                        new_lines.append(line)
            processed_blocks.append("\n".join(new_lines))
            continue

        # Replace single newlines with spaces within the block
        cleaned_block = re.sub(r'(?<!\n)\n(?!\n)', ' ', block)
        processed_blocks.append(cleaned_block)

    # Table reconstruction logic
    # Look for sequences of labels followed by sequences of values
    interleaved_blocks = []
    i = 0
    while i < len(processed_blocks):
        # Find a sequence of labels
        labels = []
        j = i
        while j < len(processed_blocks) and processed_blocks[j].endswith(':'):
            labels.append(processed_blocks[j])
            j += 1

        if labels and j < len(processed_blocks):
            # Check if we have a matching number of value blocks
            values = []
            k = j
            while k < len(processed_blocks) and len(values) < len(labels) and not processed_blocks[k].endswith(':'):
                # Ensure it's not a structural element
                if (processed_blocks[k].startswith('#') or 
                    processed_blocks[k].startswith('-')):
                    break
                values.append(processed_blocks[k])
                k += 1

            if len(labels) == len(values):
                # Interleave them!
                for label, value in zip(labels, values):
                    interleaved_blocks.append(f"{label} {value}")
                i = k # Skip processed labels AND values
                continue

        interleaved_blocks.append(processed_blocks[i])
        i += 1

    # Heuristic for joining blocks that were split mid-sentence
    final_blocks = []
    for block in interleaved_blocks:
        if not final_blocks:
            final_blocks.append(block)
            continue

        prev = final_blocks[-1]
        # Don't join if either is a structural element or contains images
        if (prev.startswith('#') or prev.startswith('-') or '![' in prev or 
            block.startswith('#') or block.startswith('-') or '![' in block):
            final_blocks.append(block)
            continue

        # Don't join if either looks like an interleaved KV pair
        if ': ' in prev or ': ' in block:
            final_blocks.append(block)
            continue

        prev_clean = re.sub(r'<[^>]+>', '', prev).strip()
        if not prev_clean:
            final_blocks.append(block)
            continue

        last_char = prev_clean[-1]
        first_char = block[0]

        is_sentence_end = last_char in '.!?:'
        is_abbreviation = re.search(r'\b(?:Jg|geb|ca|u|v|Dr|Chr|Nr|Bd|S|orig|[A-Z])\.$', prev_clean, re.I)
        starts_with_lowercase = first_char.islower()
        starts_with_digit = first_char.isdigit()
        ends_with_comma = last_char == ','
        is_brace_join = last_char == '(' or first_char == ')'

        # Join if it clearly continues OR if previous didn't end with proper terminator
        if (ends_with_comma or is_abbreviation or 
            starts_with_lowercase or starts_with_digit or is_brace_join or
            not is_sentence_end):
            if block.startswith(','):
                final_blocks[-1] = f"{prev}{block}"
            else:
                final_blocks[-1] = f"{prev} {block}"
        else:
            final_blocks.append(block)            

    # Final cleanup: strip very short fragments from the end of the blocks
    cleaned_final = []
    for i, block in enumerate(final_blocks):
        is_structural = block.startswith('#') or block.startswith('-') or '![' in block
        # Aggressively strip short fragments that don't end in punctuation
        if not is_structural and len(block) < 30 and not block.endswith('.') and not block.endswith(':') and ': ' not in block:
            # Check if it's followed by a structural element or it's the last block
            is_last = i == len(final_blocks) - 1
            next_is_structural = not is_last and (final_blocks[i+1].startswith('#') or '![' in final_blocks[i+1])
            if is_last or next_is_structural:
                continue 
        cleaned_final.append(block)

    # Rename "## Links" to "## Sources" for consistent UI
    content = "\n\n".join(cleaned_final)
    content = re.sub(r'^## Links\s*$', '## Sources', content, flags=re.M)
    return content

def merge_file(base_path: Path, override_path: Path | None) -> str:
    base_text = base_path.read_text() if base_path.exists() else ""
    if not override_path or not override_path.exists():
        # Even if no override, we might want to clean the base body
        base_fm, base_body = parse_frontmatter(base_text)
        return serialize_frontmatter(base_fm, clean_body(base_body))

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
    return serialize_frontmatter(merged_fm, clean_body(merged_body))


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
