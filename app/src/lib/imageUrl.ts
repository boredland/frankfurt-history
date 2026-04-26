const R2_PUBLIC_URL = "https://pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev";

const PROXY_BASE = "https://frankfurt-history.pages.dev/cdn-cgi/image";

type ImagePreset = "article" | "thumbnail" | "lightbox" | "og";

const PRESETS: Record<ImagePreset, string> = {
  article: "w=800,f=auto,q=85",
  thumbnail: "w=200,h=150,fit=cover,f=auto",
  lightbox: "w=1600,f=auto",
  og: "w=1200,h=630,fit=cover,f=jpg",
};

export function imageUrl(src: string, preset: ImagePreset = "article"): string {
  if (!src.startsWith(R2_PUBLIC_URL)) return src;
  const path = src.slice(R2_PUBLIC_URL.length);
  return `${PROXY_BASE}/${PRESETS[preset]}${path}`;
}

export function rewriteImgSrc(html: string, preset: ImagePreset): string {
  return html.replace(
    /src="(https:\/\/pub-d6ff75a2458a49e5b81457a2e7841032\.r2\.dev\/[^"]+)"/g,
    (_, url) => `src="${imageUrl(url, preset)}"`,
  );
}
