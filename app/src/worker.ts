interface Env {
  ASSETS: R2Bucket;
}

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

async function handleR2(
  request: Request,
  env: Env,
  key: string,
): Promise<Response> {
  if (request.method === "OPTIONS") {
    return corsResponse();
  }

  const keyAllowed =
    ALLOWED_R2_KEYS.has(key) ||
    ALLOWED_R2_PREFIXES.some((prefix) => key.startsWith(prefix));
  if (!keyAllowed) {
    return new Response("Forbidden", { status: 403 });
  }

  const rangeHeader = request.headers.get("Range");
  const range = rangeHeader ? parseRange(rangeHeader) : null;
  if (rangeHeader && range === null) {
    return new Response("Range Not Satisfiable", { status: 416 });
  }
  const object = range
    ? await env.ASSETS.get(key, { range })
    : await env.ASSETS.get(key);

  if (!object) {
    return new Response("Not Found", { status: 404 });
  }

  const headers = new Headers();
  headers.set(
    "Content-Type",
    object.httpMetadata?.contentType || "application/octet-stream",
  );
  headers.set("Accept-Ranges", "bytes");
  headers.set("Cache-Control", "public, max-age=604800");
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("Access-Control-Allow-Headers", "Range");

  if (range) {
    if (!("range" in object)) {
      return unsatisfiableRange(object.size);
    }
    const { offset, length } = object.range as {
      offset: number;
      length: number;
    };
    // An offset at or past the end yields length 0, which would render as the
    // nonsense header "bytes 500-499/100" on a 206. PMTiles readers treat that
    // as a valid partial response and corrupt their index state.
    if (length <= 0 || offset >= object.size) {
      return unsatisfiableRange(object.size);
    }
    headers.set("Content-Length", String(length));
    headers.set(
      "Content-Range",
      `bytes ${offset}-${offset + length - 1}/${object.size}`,
    );
    return new Response(object.body, { status: 206, headers });
  }

  headers.set("Content-Length", String(object.size));
  return new Response(object.body, { status: 200, headers });
}

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

async function handleImage(url: URL): Promise<Response> {
  const rest = url.pathname.slice(5);
  const slashIdx = rest.indexOf("/");
  if (slashIdx < 0) return new Response("Bad Request", { status: 400 });

  const params = rest.slice(0, slashIdx);
  const originUrl = rest.slice(slashIdx + 1);

  let origin: URL;
  try {
    origin = new URL(originUrl);
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  if (origin.protocol !== "https:") {
    return new Response("Bad Request", { status: 400 });
  }

  // origin.port is "" for the default 443; anything else is a different service
  // on an allowlisted name and is not what the allowlist vouched for.
  if (!ALLOWED_IMAGE_HOSTS.has(origin.hostname) || origin.port !== "") {
    return new Response("Forbidden", { status: 403 });
  }

  const cfImage: Record<string, unknown> = {};
  for (const pair of params.split(",")) {
    const eqIdx = pair.indexOf("=");
    if (eqIdx < 0) continue;
    const k = pair.slice(0, eqIdx);
    const v = pair.slice(eqIdx + 1);
    switch (k) {
      case "w":
        cfImage.width = clampInt(v, 1, 4000);
        break;
      case "h":
        cfImage.height = clampInt(v, 1, 4000);
        break;
      case "f":
        if (v !== "auto") cfImage.format = v;
        break;
      case "q":
        cfImage.quality = clampInt(v, 1, 100);
        break;
      case "fit":
        cfImage.fit = v;
        break;
    }
  }

  return fetch(origin.toString(), { cf: { image: cfImage } });
}

function clampInt(raw: string, min: number, max: number): number | undefined {
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return undefined;
  return Math.min(Math.max(n, min), max);
}

function unsatisfiableRange(size: number): Response {
  return new Response("Range Not Satisfiable", {
    status: 416,
    headers: {
      "Content-Range": `bytes */${size}`,
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function corsResponse(): Response {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
      "Access-Control-Allow-Headers": "Range",
      "Access-Control-Max-Age": "86400",
    },
  });
}
