import tanstackHandler from "@tanstack/react-start/server-entry";

interface Env {
  ASSETS: R2Bucket;
  IMAGES: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/r2/")) {
      return handleR2(request, env, url.pathname.slice(4));
    }

    if (url.pathname.startsWith("/img/")) {
      return handleImage(env, url);
    }

    return tanstackHandler.fetch(request);
  },
} satisfies ExportedHandler<Env>;

async function handleR2(
  request: Request,
  env: Env,
  key: string,
): Promise<Response> {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders() });
  }

  const rangeHeader = request.headers.get("Range");
  const object = rangeHeader
    ? await env.ASSETS.get(key, { range: parseRange(rangeHeader) })
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

  if (rangeHeader && "range" in object) {
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

  headers.set("Content-Length", String(object.size));
  return new Response(object.body, { status: 200, headers });
}

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

async function handleImage(env: Env, url: URL): Promise<Response> {
  const rest = url.pathname.slice(5);
  const slashIdx = rest.indexOf("/");
  if (slashIdx < 0) return new Response("Bad Request", { status: 400 });

  const params = rest.slice(0, slashIdx);
  const originUrl = rest.slice(slashIdx + 1);

  if (!originUrl.startsWith("http")) {
    return new Response("Bad Request", { status: 400 });
  }

  return env.IMAGES.fetch(
    `https://images.local/cdn-cgi/image/${params}/${originUrl}`,
  );
}

function corsHeaders(): Headers {
  const h = new Headers();
  h.set("Access-Control-Allow-Origin", "*");
  h.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
  h.set("Access-Control-Allow-Headers", "Range");
  h.set("Access-Control-Max-Age", "86400");
  return h;
}
