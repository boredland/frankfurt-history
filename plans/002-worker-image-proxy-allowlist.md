# Plan 002: Constrain the Worker image proxy and R2 route to an allowlist

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat a44900bf..HEAD -- app/src/worker.ts app/src/lib/imageUrl.ts wrangler.json`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `a44900bf`, 2026-08-16

## Why this matters

`app/src/worker.ts` exposes two routes on the production domain
`history.jonas-strassel.de`. Both are unconstrained:

1. `/img/<params>/<originUrl>` accepts **any** URL beginning with the four
   characters `http` and fetches it through Cloudflare Images. Anyone can use
   the site's own domain and the owner's Cloudflare Images quota to fetch and
   re-serve arbitrary third-party content. Content served from the project's
   origin also inherits the project's reputation, and the transform billing is
   the account owner's.
2. `/r2/<key>` passes the request path straight to `env.ASSETS.get(key)` with
   no prefix restriction, so every object in the `frankfurt-history-assets`
   bucket is publicly readable, not just the intended PMTiles basemap and
   images.

Both fixes are small, local to one file, and verifiable. After this plan the
Worker serves only the origins and key prefixes the app actually uses, and
rejects everything else with a 400/403.

## Current state

`app/src/worker.ts` is 128 lines and is the entire Cloudflare Worker. Full
router (lines 1-19):

```typescript
interface Env {
  ASSETS: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/r2/")) {
      return handleR2(request, env, url.pathname.slice(4));
    }

    if (url.pathname.startsWith("/img/")) {
      return handleImage(url);
    }

    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

The image handler (lines 78-116) — note the only validation is
`startsWith("http")` at line 86, and the unguarded `fetch` at line 115:

```typescript
async function handleImage(url: URL): Promise<Response> {
  const rest = url.pathname.slice(5);
  const slashIdx = rest.indexOf("/");
  if (slashIdx < 0) return new Response("Bad Request", { status: 400 });

  const params = rest.slice(0, slashIdx);
  const originUrl = rest.slice(slashIdx + 1);

  if (!originUrl.startsWith("http")) {
    return new Response("Bad Request", { status: 400 });
  }

  const cfImage: Record<string, unknown> = {};
  for (const pair of params.split(",")) {
    const eqIdx = pair.indexOf("=");
    if (eqIdx < 0) continue;
    const k = pair.slice(0, eqIdx);
    const v = pair.slice(eqIdx + 1);
    switch (k) {
      case "w":
        cfImage.width = Number.parseInt(v, 10);
        break;
      case "h":
        cfImage.height = Number.parseInt(v, 10);
        break;
      case "f":
        if (v !== "auto") cfImage.format = v;
        break;
      case "q":
        cfImage.quality = Number.parseInt(v, 10);
        break;
      case "fit":
        cfImage.fit = v;
        break;
    }
  }

  return fetch(originUrl, { cf: { image: cfImage } });
}
```

The range parser (lines 66-76) — no 416 handling, and a reversed range yields a
negative `length`:

```typescript
function parseRange(header: string): R2Range {
  const match = header.match(/bytes=(\d+)-(\d*)/);
  if (!match) return { offset: 0 };
  const start = match[1] ?? "0";
  const offset = Number.parseInt(start, 10);
  const end = match[2] ? Number.parseInt(match[2], 10) : undefined;
  if (end !== undefined) {
    return { offset, length: end - offset + 1 };
  }
  return { offset };
}
```

**Which origins are legitimate.** `app/src/lib/imageUrl.ts` is the only code
that builds `/img/` URLs. Its full contents:

```typescript
const R2_PUBLIC_URL = "https://pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev";

type Preset = "article" | "thumbnail" | "lightbox" | "og";

const PRESETS: Record<Preset, string> = {
  article: "w=800,f=auto,q=85",
  thumbnail: "w=200,h=150,fit=cover,f=auto",
  lightbox: "w=1600,f=auto",
  og: "w=1200,h=630,fit=cover,f=jpg",
};

export function imageUrl(src: string, preset: Preset = "article"): string {
  if (!src.startsWith(R2_PUBLIC_URL)) return src;
  return `/img/${PRESETS[preset]}/${src}`;
}
```

So the **only** origin the app ever proxies is the R2 public bucket host
`pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev`.

One more consumer exists outside the app: `scripts/download_stolperstein_images.py:23`
uses the same proxy during the data pipeline:

```python
IMG_PROXY = os.environ.get("IMG_PROXY_URL", "https://history.jonas-strassel.de/img")
```

and at line 56-60 it proxies `frankfurt.de` image URLs through it. Therefore the
allowlist must include **both** the R2 host and `frankfurt.de`, or the weekly
cron image download breaks. This is the single most important constraint in this
plan — see the STOP conditions.

**Which R2 key prefixes are legitimate.** Two:

- `images/` — written by `scripts/sync_images.py:42` (`key = f"images/{filename}"`)
  and `sync_images.py:129` (`f"{key_prefix}/{p.name}"` with prefix
  `images/stolpersteine`).
- `frankfurt.pmtiles` — referenced by `app/src/lib/mapStyle.ts` as
  `/r2/frankfurt.pmtiles` in production.

**Repo conventions you must match:**

- TypeScript, 2-space indent, double quotes, semicolons, trailing commas.
  Biome enforces this (`app/biome.json`); run `bun run lint` to confirm.
- Module-level `SCREAMING_CASE` constants declared above the functions that use
  them — see `PRESETS` in `imageUrl.ts` above.
- Plain `function` declarations, not arrow consts, for top-level helpers (every
  helper in `worker.ts` follows this).
- Commit messages are Conventional Commits, e.g.
  `fix: restrict worker image proxy to allowlisted origins`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Install JS deps | `cd app && bun install` | exit 0 |
| Typecheck | `cd app && bun run typecheck` | exit 0, no errors |
| Lint | `cd app && bun run lint` | exit 0 |
| Both | `cd app && bun run check` | exit 0 |

## Scope

**In scope** (the only file you should modify):

- `app/src/worker.ts`

**Out of scope** (do NOT touch, even though they look related):

- `app/src/lib/imageUrl.ts` — the client-side URL builder. It only ever emits
  R2 URLs, so it needs no change. Changing it does not fix the server-side hole,
  because an attacker calls the Worker directly, not through the app.
- `scripts/download_stolperstein_images.py` — the pipeline consumer. It must
  keep working; this plan accommodates it via the allowlist rather than changing
  it.
- `wrangler.json` — bindings are correct as they are.
- `app/public/_headers` — response headers are handled in a separate plan.
- Any change that removes the `/img/` or `/r2/` routes entirely. The app depends
  on both.

## Git workflow

- Branch: `advisor/002-worker-image-proxy-allowlist`
- One commit is fine; message style Conventional Commits, e.g.
  `fix: restrict worker image proxy and r2 route to allowlisted origins`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the origin and key-prefix allowlists

At the top of `app/src/worker.ts`, directly below the `interface Env` block,
add these module-level constants:

```typescript
/** Hosts the image proxy is permitted to fetch from. */
const ALLOWED_IMAGE_HOSTS = new Set([
  "pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev",
  "frankfurt.de",
  "www.frankfurt.de",
]);

/** R2 key prefixes the /r2/ route is permitted to serve (must end in "/"). */
const ALLOWED_R2_PREFIXES = ["images/"];

/** Exact R2 object keys the /r2/ route is permitted to serve. */
const ALLOWED_R2_KEYS = new Set(["frankfurt.pmtiles"]);
```

`frankfurt.de` and `www.frankfurt.de` are required by
`scripts/download_stolperstein_images.py`, which proxies image URLs from that
host during the weekly cron. Removing them breaks the pipeline.

**Verify**: `cd app && bun run typecheck` → exit 0.

### Step 2: Validate the origin URL in `handleImage`

In `handleImage`, replace this block:

```typescript
  if (!originUrl.startsWith("http")) {
    return new Response("Bad Request", { status: 400 });
  }
```

with a real URL parse plus a host and scheme check:

```typescript
  let origin: URL;
  try {
    origin = new URL(originUrl);
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  if (origin.protocol !== "https:") {
    return new Response("Bad Request", { status: 400 });
  }

  if (!ALLOWED_IMAGE_HOSTS.has(origin.hostname)) {
    return new Response("Forbidden", { status: 403 });
  }
```

Then change the final line of `handleImage` from `fetch(originUrl, ...)` to use
the parsed, normalized URL:

```typescript
  return fetch(origin.toString(), { cf: { image: cfImage } });
```

Using `origin.hostname` (not `originUrl.includes(...)`) is what makes this
sound: a substring check would accept a URL whose *path* or *userinfo* contains
an allowlisted host name while the actual host is attacker-controlled.

**Verify**: `cd app && bun run check` → exit 0.

### Step 3: Constrain the R2 key

In `handleR2`, immediately after the `if (request.method === "OPTIONS")` block,
add the prefix check:

```typescript
  const keyAllowed =
    ALLOWED_R2_KEYS.has(key) ||
    ALLOWED_R2_PREFIXES.some((prefix) => key.startsWith(prefix));
  if (!keyAllowed) {
    return new Response("Forbidden", { status: 403 });
  }
```

Exact keys and directory prefixes are deliberately separate lists. A single
`startsWith("frankfurt.pmtiles")` check would also match
`frankfurt.pmtiles.backup` or `frankfurt.pmtilesX/secret` — every prefix entry
must therefore end in `/`, and anything else belongs in `ALLOWED_R2_KEYS`.

**Verify**: `cd app && bun run check` → exit 0.

### Step 3b: Clamp image transform dimensions

The `w`, `h` and `q` values are parsed straight from the request path with no
bounds, so `?w=100000` is passed to Cloudflare Images as-is. Now that the origin
is allowlisted this is a quota concern rather than a content one, but it is two
lines to close. In the `switch` inside `handleImage`, replace the `w`, `h` and
`q` cases with clamped versions:

```typescript
      case "w":
        cfImage.width = clampInt(v, 1, 4000);
        break;
      case "h":
        cfImage.height = clampInt(v, 1, 4000);
        break;
      case "q":
        cfImage.quality = clampInt(v, 1, 100);
        break;
```

and add the helper beside the other module-level functions:

```typescript
function clampInt(raw: string, min: number, max: number): number | undefined {
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return undefined;
  return Math.min(Math.max(n, min), max);
}
```

The widest preset in `app/src/lib/imageUrl.ts` is `lightbox` at `w=1600`, so a
4000px ceiling leaves ample headroom for every existing caller.

**Verify**: `cd app && bun run check` → exit 0.

### Step 4: Reject unsatisfiable and malformed ranges

Replace `parseRange` with a version that signals invalid input instead of
silently returning `{ offset: 0 }` or a negative length:

```typescript
function parseRange(header: string): R2Range | null {
  const match = header.match(/^bytes=(\d+)-(\d*)$/);
  if (!match) return null;
  const offset = Number.parseInt(match[1] ?? "0", 10);
  if (!Number.isFinite(offset)) return null;
  if (!match[2]) return { offset };
  const end = Number.parseInt(match[2], 10);
  if (!Number.isFinite(end) || end < offset) return null;
  return { offset, length: end - offset + 1 };
}
```

Then update the caller in `handleR2`. The current code is:

```typescript
  const rangeHeader = request.headers.get("Range");
  const object = rangeHeader
    ? await env.ASSETS.get(key, { range: parseRange(rangeHeader) })
    : await env.ASSETS.get(key);
```

Replace it with:

```typescript
  const rangeHeader = request.headers.get("Range");
  const range = rangeHeader ? parseRange(rangeHeader) : null;
  if (rangeHeader && range === null) {
    return new Response("Range Not Satisfiable", { status: 416 });
  }
  const object = range
    ? await env.ASSETS.get(key, { range })
    : await env.ASSETS.get(key);
```

Then fix the 206-response block below it. Currently it reads
`if (rangeHeader && "range" in object)`. Change it to handle the case where R2
could not satisfy the range at all — an offset past the end of the object makes
`"range" in object` false, and the current code would silently fall through and
return **200 with the entire file**:

```typescript
  if (range) {
    if (!("range" in object)) {
      return new Response("Range Not Satisfiable", { status: 416 });
    }
    const { offset, length } = object.range as {
      offset: number;
      length: number;
    };
    headers.set("Content-Length", String(length));
    headers.set(
      "Content-Range",
      `bytes ${offset}-${offset + length - 1}/${object.size}`,
    );
    return new Response(object.body, { status: 206, headers });
  }
```

Note: this is a behaviour change for suffix ranges (`bytes=-500`), which the old
regex silently treated as "whole object from offset 0" and which now return 416.
MapLibre's PMTiles reader issues only explicit `bytes=start-end` ranges, so this
does not affect the basemap. Confirm in step 5.

**Verify**: `cd app && bun run check` → exit 0.

### Step 5: Smoke-test the map still loads

The PMTiles basemap is served through `/r2/frankfurt.pmtiles` with range
requests. A mistake in step 4 breaks the map silently, so verify it renders.

```bash
cd app && bun run build:data && bun run dev
```

Open the dev server URL, load `/de/`, and confirm:

- the basemap tiles render (streets and labels visible, not a blank canvas),
- POI markers appear,
- the browser devtools Network tab shows `206 Partial Content` responses for
  the PMTiles requests, not `416`.

If `bun run build:data` fails because Python dependencies are unavailable, run
`bun run dev` alone — a previously built `app/public/data/` may still be present.
If the map cannot be verified at all in your environment, say so explicitly in
your report rather than claiming it works.

**Verify**: map renders with visible basemap and markers; no `416` responses in
the Network tab.

## Test plan

No automated test infrastructure exists for the Worker, and this plan does not
add one (adding a Workers test runner is a larger decision, deliberately
deferred). Verification is the typecheck, the lint, and the step-5 smoke test.

If plan 001 has landed and you want a regression guard, the pure functions
(`parseRange`, and an extracted host-check helper) are the testable seams — but
extracting them is out of scope here.

Manual checks that must hold after the change, verified by reading the code:

- `/img/w=800,f=auto/https://pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev/images/x.jpg`
  → allowed (R2 host on the list).
- `/img/w=800,f=auto/https://frankfurt.de/…/x.jpg` → allowed (pipeline needs it).
- `/img/w=800,f=auto/https://example.com/x.png` → `403 Forbidden`.
- `/img/w=800,f=auto/http://…` (plain HTTP) → `400 Bad Request`.
- `/r2/images/stolpersteine/x.jpg` → allowed.
- `/r2/frankfurt.pmtiles` → allowed (exact key).
- `/r2/frankfurt.pmtiles.backup` → `403 Forbidden` (not an exact key, and
  `frankfurt.pmtiles` is not a `/`-terminated prefix).
- `/r2/some-other-object` → `403 Forbidden`.
- `Range: bytes=100-199` → `206` with `Content-Range: bytes 100-199/<size>`.
- `Range: bytes=200-100` → `416`.
- `Range: garbage` → `416`.
- `Range: bytes=999999999-` on a smaller object → `416`, **not** a `200` with
  the whole file.
- `/img/w=100000/<allowlisted-origin>` → width clamped to 4000, not forwarded raw.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd app && bun run typecheck` exits 0
- [ ] `cd app && bun run lint` exits 0
- [ ] `grep -c "ALLOWED_IMAGE_HOSTS" app/src/worker.ts` returns ≥ 2
- [ ] `grep -c "ALLOWED_R2_PREFIXES" app/src/worker.ts` returns ≥ 2
- [ ] `grep -c "ALLOWED_R2_KEYS" app/src/worker.ts` returns ≥ 2
- [ ] Every string in `ALLOWED_R2_PREFIXES` ends with `/`
- [ ] `grep -n "clampInt" app/src/worker.ts` returns the definition and its uses
- [ ] `grep -n 'originUrl.startsWith("http")' app/src/worker.ts` returns **no matches**
- [ ] `grep -n "fetch(originUrl" app/src/worker.ts` returns **no matches**
- [ ] `grep -n "416" app/src/worker.ts` returns at least one match
- [ ] `git status --porcelain` shows **only** `app/src/worker.ts` modified (plus `plans/README.md`)
- [ ] The step-5 map smoke test passed, or its failure is reported explicitly
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations quoted in "Current state" doesn't match the live
  file (the codebase drifted since this plan was written).
- You find any **other** caller that builds `/img/` URLs with a host not on the
  allowlist. Check with:
  `grep -rn "/img/" app/src/ scripts/ --include=*.ts --include=*.tsx --include=*.py`
  If a fourth host appears, STOP — silently omitting it would break the weekly
  cron, and silently adding it would defeat the plan. Report the host and let
  the operator decide.
- The R2 public bucket hostname in `app/src/lib/imageUrl.ts` differs from the one
  quoted above — the allowlist must match the real bucket or every image 403s.
- The map fails to render after step 4 and the cause is not obvious from the
  Network tab.
- `bun install` cannot run in your environment — then you cannot verify at all;
  report that rather than shipping unverified security code.

## Maintenance notes

- **The allowlist is now a coupling point.** If images are ever migrated to a
  new R2 bucket or a new upstream source is scraped, `ALLOWED_IMAGE_HOSTS` must
  be updated in the same change, or images silently 403. Consider a code comment
  at `scripts/download_stolperstein_images.py:23` pointing at this list.
- `frankfurt.de` is on the allowlist **only** because the data pipeline proxies
  through the production Worker. If
  `scripts/download_stolperstein_images.py` is ever changed to fetch directly
  instead of through `/img/`, both `frankfurt.de` entries should be removed.
- A reviewer should check that the host comparison uses `URL.hostname` equality,
  never `includes()` or `endsWith()` on the raw string.
- Deferred out of this plan: response security headers (CSP, nosniff,
  Referrer-Policy) — `app/public/_headers` currently sets headers only for
  `/*.pmtiles`. That is a separate, independent change.
- Also deferred: rate limiting on `/img/`. The allowlist removes the arbitrary-
  origin problem; volume abuse against allowlisted origins is a different
  control and needs Cloudflare-side configuration, not Worker code.
