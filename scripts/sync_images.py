#!/usr/bin/env python3
"""Sync images from the Frankfurt History API to Cloudflare R2.

Reads all markdown files in data/, extracts image filenames,
downloads from the API, and uploads to R2 via wrangler.

Requires: wrangler CLI authenticated.
"""

import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

API_BASE = "https://api.frankfurthistory.app"
R2_BUCKET = "frankfurt-history-assets"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORKERS = int(os.environ.get("SYNC_WORKERS", "8"))
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2


def find_image_refs() -> set[str]:
    refs = set()
    ref_pattern = re.compile(r"\.\.\/images\/([^\)\]\"\x27\n]+)")
    for md in DATA_DIR.rglob("*.md"):
        refs.update(ref_pattern.findall(md.read_text()))
    return refs


def list_r2_keys() -> set[str]:
    """List existing image keys in R2 to skip re-uploads."""
    result = subprocess.run(
        ["wrangler", "r2", "object", "list", R2_BUCKET, "--prefix=images/", "--remote"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    keys = set()
    import json
    try:
        objects = json.loads(result.stdout)
        for obj in objects:
            keys.add(obj.get("key", ""))
    except (json.JSONDecodeError, TypeError):
        pass
    return keys


def sync_one(filename: str) -> str:
    key = f"images/{filename}"
    url = f"{API_BASE}/storage/images/{filename}"

    suffix = Path(filename).suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        client = httpx.Client(timeout=60, follow_redirects=True)
        for attempt in range(RETRY_ATTEMPTS):
            try:
                resp = client.get(url)
                resp.raise_for_status()
                tmp_path.write_bytes(resp.content)
                break
            except (httpx.HTTPStatusError, httpx.TransportError):
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    client.close()
                    return "fail"
        client.close()

        result = subprocess.run(
            [
                "wrangler",
                "r2",
                "object",
                "put",
                f"{R2_BUCKET}/{key}",
                f"--file={tmp_path}",
                "--remote",
            ],
            capture_output=True,
            text=True,
        )
        return "ok" if result.returncode == 0 else "fail"
    finally:
        tmp_path.unlink(missing_ok=True)


def main():
    refs = find_image_refs()
    print(f"Found {len(refs)} unique image references")

    # Try to list existing to skip
    existing = list_r2_keys()
    to_sync = [r for r in refs if f"images/{r}" not in existing]
    print(f"Already in R2: {len(refs) - len(to_sync)}, to upload: {len(to_sync)}")

    if not to_sync:
        print("Nothing to sync.")
        return

    ok = 0
    fail = 0
    total = len(to_sync)
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(sync_one, f): f for f in sorted(to_sync)}
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            if result == "ok":
                ok += 1
            else:
                fail += 1
                print(f"  Failed: {futures[future]}")
            done = i + 1
            if done % 25 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total}] {ok} ok, {fail} fail — {rate:.1f}/s, ETA {eta:.0f}s")

    print(f"\nDone: {ok} uploaded, {fail} failed")


if __name__ == "__main__":
    main()
