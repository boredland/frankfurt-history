#!/usr/bin/env python3
"""Sync images from the Frankfurt History API to Cloudflare R2.

Reads data/images.json (written by archive.py) which maps each image
filename to its source API URL. For each entry:
1. HEAD the R2 public URL — skip if already there
2. Download from the source URL
3. Upload to R2 via wrangler

Requires: wrangler CLI authenticated, data/images.json from archive.py.
"""

import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

R2_BUCKET = "frankfurt-history-assets"
R2_PUBLIC_URL = os.environ.get(
    "R2_PUBLIC_URL", "https://pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev"
)
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "images.json"
WORKERS = int(os.environ.get("SYNC_WORKERS", "8"))
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2


def sync_one(filename: str, source_url: str) -> str:
    """Check R2, download from source if missing, upload to R2. Returns 'ok', 'skip', or 'fail'."""
    key = f"images/{filename}"
    r2_url = f"{R2_PUBLIC_URL}/{key}"

    try:
        head = httpx.head(r2_url, timeout=10, follow_redirects=True)
        if head.status_code == 200:
            return "skip"
    except httpx.TransportError:
        pass

    suffix = Path(filename).suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        client = httpx.Client(timeout=60, follow_redirects=True)
        for attempt in range(RETRY_ATTEMPTS):
            try:
                resp = client.get(source_url)
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
    if not MANIFEST_PATH.exists():
        print(f"No manifest at {MANIFEST_PATH} — run archive.py first.")
        sys.exit(1)

    manifest: dict[str, str] = json.loads(MANIFEST_PATH.read_text())
    print(f"Manifest: {len(manifest)} images")

    if not manifest:
        print("Nothing to sync.")
        return

    ok = 0
    skip = 0
    fail = 0
    total = len(manifest)
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(sync_one, filename, source_url): filename
            for filename, source_url in sorted(manifest.items())
        }
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            if result == "ok":
                ok += 1
            elif result == "skip":
                skip += 1
            else:
                fail += 1
                print(f"  Failed: {futures[future]}")
            done = i + 1
            if done % 100 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(
                    f"  [{done}/{total}] {ok} new, {skip} exist, {fail} fail — {rate:.1f}/s, ETA {eta:.0f}s"
                )

    print(f"\nDone: {ok} uploaded, {skip} already in R2, {fail} failed")


if __name__ == "__main__":
    main()
