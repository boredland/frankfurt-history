# Plan 003: Escape scraped content before it becomes article HTML

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat a44900bf..HEAD -- app/src/lib/parseArticle.ts app/src/components/ArticlePanel.tsx`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (independent of 001; 001 adds Python tests only)
- **Category**: security
- **Planned at**: commit `a44900bf`, 2026-08-16

## Why this matters

Article body text is scraped from third-party sources, stored as markdown in
`data/`, compiled to JSON, then converted to an HTML string by a hand-rolled
regex converter and injected into the DOM with `dangerouslySetInnerHTML`.
**Nothing escapes HTML anywhere along that path.** Any HTML markup present in
the source content is rendered as live markup rather than as text.

The upstream ingest actively *creates* this condition: `archive.py:88` calls
`html.unescape(...)` **after** `soup.get_text()`, which converts already-escaped
entities back into raw tag syntax. Verified behaviour:

```
input:  <p>Text &lt;img src=x onerror=X&gt; Ende</p>
output: Text <img src=x onerror=X> Ende
```

Today's archive is mostly benign — a scan of `data/de/**` finds only 50 `<br>`,
3 `<p>`, and 1 `<span class="tab2">` — so this is not an active incident. But
the pipeline re-scrapes third-party HTML every Monday via cron and commits the
result unreviewed, so the content of `data/` is not a trusted input, and the
current code has no defence if a source page changes.

The fix has two halves, and the order matters: escape first, then re-allow the
specific markup the converter itself generates.

## Current state

**The renderer.** `app/src/components/ArticlePanel.tsx:320-327` — the only place
article HTML enters the DOM:

```tsx
      {sections.map((section, i) => {
        const key = `s-${i}`;
        switch (section.type) {
          case "html":
            return (
              <div
                key={key}
                className="article-body"
                dangerouslySetInnerHTML={{ __html: section.content }}
              />
            );
```

(There is a second `dangerouslySetInnerHTML` at `app/src/routes/__root.tsx:61`.
It injects a fixed service-worker registration string with no interpolation.
It is **not** in scope and must not be changed.)

**The converter.** `app/src/lib/parseArticle.ts:13-47`, complete and verbatim —
this is what produces `section.content`:

```typescript
function markdownBlockToHtml(md: string): string {
  let html = md;
  // Bare URLs → markdown links (before any HTML is generated)
  html = html.replace(/(?<![(["])(https?:\/\/[^\s<)\]]+)/g, "[$1]($1)");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Strip inline images — they'll be collected separately as gallery images
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)\n?(\*[^*]+\*)?/g, "");
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Require space/start before opening * to avoid matching Gendersternchen (Bürger*innen)
  html = html.replace(/(?<=^|[\s(])\*([^*\n]+)\*(?![*\w])/gm, "<em>$1</em>");
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

  const paragraphs = html
    .split(/\n{2,}/)
    .map((block) => {
      block = block.trim();
      if (!block) return "";
      if (
        block.startsWith("<h") ||
        block.startsWith("<ul") ||
        block.startsWith("<img") ||
        block.startsWith("<a ")
      )
        return block;
      return `<p>${block}</p>`;
    })
    .filter(Boolean);
  return paragraphs.join("\n");
}
```

Two distinct problems in that function:

1. No escaping — source markup passes straight through into the output string.
2. Link `href` values (capture group `$2`) are interpolated into
   `<a href="$2">` with no scheme check and no attribute-quote escaping, so a
   `javascript:` URL or a `"` inside the URL both reach the DOM.

**The exact set of tags the converter legitimately emits** (this is the
allowlist you will need in step 2): `h1`, `h2`, `h3`, `p`, `ul`, `li`,
`strong`, `em`, and `a` with exactly the attributes `href`, `target="_blank"`,
`rel="noopener"`.

**Repo conventions you must match:**

- TypeScript, 2-space indent, double quotes, semicolons, trailing commas —
  enforced by Biome (`app/biome.json`).
- Top-level helpers are `function` declarations; module constants are
  `SCREAMING_CASE` above their first use. `parseArticle.ts` already follows both.
- No new runtime dependency should be added for this. The app's dependency list
  (`app/package.json`) is deliberately small; a sanitizer library is a heavier
  answer than this converter needs, and DOMPurify would also need a DOM shim
  during prerender (`app/vite.config.ts` sets `prerender: { enabled: true }`).
  Escape-then-allowlist in pure string code avoids both problems.
- Commit style: Conventional Commits, e.g.
  `fix: escape scraped markup before article html conversion`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Install JS deps | `cd app && bun install` | exit 0 |
| Typecheck | `cd app && bun run typecheck` | exit 0, no errors |
| Lint | `cd app && bun run lint` | exit 0 |
| Both | `cd app && bun run check` | exit 0 |
| Build data | `cd app && bun run build:data` | exit 0, writes `app/public/data/` |
| Dev server | `cd app && bun run dev` | serves the app |

## Scope

**In scope** (the only files you should modify):

- `app/src/lib/parseArticle.ts`

**Out of scope** (do NOT touch, even though they look related):

- `app/src/components/ArticlePanel.tsx` — the `dangerouslySetInnerHTML` call
  stays. Once `markdownBlockToHtml` only ever emits allowlisted markup, the sink
  is fed trusted output. Rewriting the renderer into React nodes is a much larger
  change and is not this plan.
- `app/src/routes/__root.tsx:61` — the service-worker registration script. Fixed
  string, no interpolation, not a finding.
- `archive.py` — the `html.unescape` call at line 88 is the upstream cause, but
  changing it would rewrite the meaning of the entire committed `data/` archive
  and require a full re-scrape. Defence at the render boundary is the correct
  place for this fix. Do not touch the pipeline.
- Anything under `data/` — the committed archive.
- Adding a sanitizer dependency (DOMPurify, sanitize-html, etc.). See the
  conventions note above.

## Git workflow

- Branch: `advisor/003-sanitize-article-html`
- One or two commits; Conventional Commits style, e.g.
  `fix: escape scraped markup and validate link hrefs in article rendering`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add an HTML-escape helper and escape the input first

At the top of `app/src/lib/parseArticle.ts`, above `markdownBlockToHtml`, add:

```typescript
const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch] ?? ch);
}
```

Then make escaping the **first** operation in `markdownBlockToHtml`. Change:

```typescript
function markdownBlockToHtml(md: string): string {
  let html = md;
```

to:

```typescript
function markdownBlockToHtml(md: string): string {
  let html = escapeHtml(md);
```

Order is load-bearing: escaping must happen before any tag is generated,
otherwise the escape pass would mangle the converter's own output.

**Verify**: `cd app && bun run typecheck` → exit 0.

At this point the converter is safe but *over*-escaped: markdown syntax
characters are untouched (`&<>"'` only), so headings, bold, italics and lists
still work — but link URLs containing `&` are now `&amp;`, which is correct in
HTML attribute context. Step 2 handles the link href specifically.

### Step 2: Validate link hrefs against a scheme allowlist

Replace the link-generating `replace` call:

```typescript
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
```

with a callback form that checks the scheme and drops the anchor when the URL is
not safe:

```typescript
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_full, label: string, href: string) => {
      const safe = safeHref(href);
      if (!safe) return label;
      return `<a href="${safe}" target="_blank" rel="noopener">${label}</a>`;
    },
  );
```

And add the helper next to `escapeHtml`:

```typescript
const SAFE_URL_SCHEMES = ["http://", "https://", "mailto:"];

/** Returns the href if it uses a safe scheme or is a relative path, else null. */
function safeHref(href: string): string | null {
  const trimmed = href.trim();
  if (!trimmed) return null;
  // Already HTML-escaped upstream; compare on the unescaped form.
  const probe = trimmed.replace(/&amp;/g, "&").toLowerCase();
  // "//host" is protocol-relative and resolves to an arbitrary third-party
  // origin — it must NOT be treated as a same-site relative path.
  if (probe.startsWith("//")) return null;
  if (probe.startsWith("/") || probe.startsWith("#")) return trimmed;
  if (SAFE_URL_SCHEMES.some((scheme) => probe.startsWith(scheme))) return trimmed;
  return null;
}
```

The `//` check must come **before** the `/` check. Without it,
`[text](//evil.example/page)` satisfies `startsWith("/")` and renders as a link
to an arbitrary external origin, bypassing the scheme allowlist entirely.

Rejected URLs degrade to plain label text rather than a broken link — that keeps
the sentence readable, which matters for a memorial archive.

**Verify**: `cd app && bun run check` → exit 0.

### Step 2b: Keep query strings intact in bare-URL link-ification

`markdownBlockToHtml` link-ifies bare URLs on its first line:

```typescript
  html = html.replace(/(?<![(["])(https?:\/\/[^\s<)\]]+)/g, "[$1]($1)");
```

Because escaping now runs first, a bare URL containing a query string has
already had its `&` turned into `&amp;`. Verified:

```
input:  Siehe https://example.com/item?id=1&ref=2 hier.
after escape:    …/item?id=1&amp;ref=2
after link-ify:  [https://example.com/item?id=1&amp;ref=2](https://example.com/item?id=1&amp;ref=2)
```

The resulting `href` is `…?id=1&amp;ref=2`. In an HTML attribute that is the
**correct** encoding — a browser decodes it back to `&` when following the link —
so this is not a bug, but the visible link *text* also shows `&amp;`, which is
wrong. Fix only the label by unescaping it in the link callback you wrote in
step 2:

```typescript
      if (!safe) return label;
      const text = label.replace(/&amp;/g, "&");
      return `<a href="${safe}" target="_blank" rel="noopener">${text}</a>`;
```

Do **not** unescape the `href` — leaving it encoded is what keeps the attribute
safe.

**Verify**: `cd app && bun run check` → exit 0.

### Step 3: Confirm the `<br>` markup in real content still behaves

The archive contains 50 literal `<br>` occurrences (e.g.
`data/de/frankfurt-stories/1432-peterskirchhof-totenkapelle.md:17`) and one
`<span class="tab2">K</span>`
(`data/de/frankfurt-und-der-ns/2233-universitaets-hautklinik.md:20`). After step 1
these now render as **visible text** (`<br>`) instead of a line break.

That is the correct security outcome but a visible content regression. Decide
explicitly, and record the decision in your report:

- If the rendered `<br>` text is acceptable, leave it.
- If not, add a narrow post-escape re-allow for `<br>` only, placed immediately
  after the `escapeHtml` call:

```typescript
  // Re-allow the one inline tag present in the archived content.
  html = html.replace(/&lt;br\s*\/?&gt;/gi, "<br />");
```

Do **not** generalise this into a re-allow list for arbitrary tags — one
explicit exception with a comment is the whole point.

**Verify**: `cd app && bun run check` → exit 0.

### Step 4: Smoke-test real articles in the browser

```bash
cd app && bun run build:data && bun run dev
```

Open the dev server and check at least these three real articles:

- `/de/frankfurt-stories/1432-peterskirchhof-totenkapelle` — contains `<br>`.
- `/de/frankfurt-und-der-ns/2233-universitaets-hautklinik` — contains a `<span>`.
- `/de/frankfurt-stories/2205-hauptwache` — ordinary prose plus a gallery.

Confirm for each:

- Body text renders as prose, not as visible escaped entities like `&amp;` or
  `&lt;p&gt;` scattered through the text.
- Headings, bold, italics and bullet lists still render as formatting.
- Links in the "Sources" section are still clickable and point at the right URL.
- German umlauts and the Gendersternchen form (`Bürger*innen`, present in
  `2205-hauptwache`) render correctly and are not turned into `<em>`.

If `bun run build:data` fails because Python dependencies are unavailable,
report that and stop — you cannot verify this change without rendering it.

**Verify**: all three articles render correctly; no stray entities; no visible
raw tags other than any `<br>` you deliberately left in step 3.

## Test plan

There is no JavaScript test runner in this repo, and this plan does not add one.
Verification is typecheck, lint, and the step-4 browser smoke test.

Behaviour that must hold after the change (verify by reading the code and by the
step-4 render):

| Input fragment | Expected rendered result |
|---|---|
| `Ein normaler Absatz.` | unchanged prose |
| `## Überschrift` | `<h2>` heading |
| `**fett**` / `*kursiv*` | `<strong>` / `<em>` |
| `Bürger*innen` | literal text, **not** `<em>` |
| `- Punkt` | list item inside `<ul>` |
| `[Quelle](https://example.org/a)` | clickable link |
| `[x](javascript:…)` | plain text `x`, no anchor |
| `[x](//evil.example/p)` | plain text `x`, no anchor (protocol-relative) |
| `[x](/de/theme/slug)` | clickable same-site link |
| bare `https://e.com/a?i=1&r=2` | link text shows `&`, href keeps `&amp;` |
| a literal `<script>` tag in source | visible text, not executed |
| a literal `<img onerror=…>` in source | visible text, no element created |

If plan 001's harness is later extended to JavaScript, `escapeHtml`,
`safeHref`, and `markdownBlockToHtml` are pure functions and are the natural
first unit tests. Extracting them into a test file is deliberately out of scope
here.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd app && bun run typecheck` exits 0
- [ ] `cd app && bun run lint` exits 0
- [ ] `grep -n "escapeHtml" app/src/lib/parseArticle.ts` shows the definition and a call as the first statement of `markdownBlockToHtml`
- [ ] `grep -n "safeHref" app/src/lib/parseArticle.ts` shows the definition and its use in the link replacement
- [ ] `grep -n 'startsWith("//")' app/src/lib/parseArticle.ts` returns a match, and it appears **before** the single-slash check
- [ ] `grep -n 'href="\$2"' app/src/lib/parseArticle.ts` returns **no matches** (the raw interpolation is gone)
- [ ] `grep -rn "dompurify\|sanitize-html" app/package.json` returns **no matches** (no dependency added)
- [ ] `git status --porcelain` shows **only** `app/src/lib/parseArticle.ts` modified (plus `plans/README.md`)
- [ ] The step-4 smoke test passed on all three named articles, or its failure is reported explicitly
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations quoted in "Current state" doesn't match the live
  file (the codebase drifted since this plan was written).
- After step 1, articles render with visible escaped entities (`&amp;` etc.)
  throughout the prose. That means escaping is interacting with the pipeline's
  own output in a way this plan did not predict — report an example article and
  the exact rendered string rather than patching around it.
- Removing the raw `href="$2"` interpolation breaks the "Sources" links on real
  articles in a way step 2's `safeHref` does not explain.
- You conclude the fix requires changing `ArticlePanel.tsx` or `archive.py`.
  Both are out of scope; report why instead.
- `bun install` cannot run in your environment — you then cannot verify, and
  shipping unverified escaping logic is worse than not shipping it.

## Maintenance notes

- **The root cause is still upstream and deliberately unfixed here.**
  `archive.py:88` runs `html.unescape()` after `BeautifulSoup.get_text()`, which
  re-creates raw tag syntax inside the archived markdown. This plan defends at
  the render boundary. If the pipeline is ever reworked, that line is where to
  fix it properly — and this escaping should stay regardless, as defence in
  depth.
- The allowlisted output tags are `h1 h2 h3 p ul li strong em a` plus, if step 3
  kept it, `br`. Any future addition to `markdownBlockToHtml` that emits a new
  tag must be added consciously — the escape pass will otherwise neutralise it,
  which is the safe failure direction.
- A reviewer should check that `escapeHtml` is the **first** statement in
  `markdownBlockToHtml`, that no later `replace` reintroduces raw input into an
  attribute, and that the `<br>` exception (if present) matches only `<br>`.
- Deferred out of this plan: rendering articles as React nodes instead of an
  HTML string, which would remove `dangerouslySetInnerHTML` entirely. That is
  the durable fix and a much larger change.
- Also deferred: a Content-Security-Policy header. `app/public/_headers` sets
  headers only for `/*.pmtiles`. A CSP would be a second, independent layer.
