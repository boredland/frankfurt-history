const R2_PUBLIC_URL = "https://pub-d6ff75a2458a49e5b81457a2e7841032.r2.dev";

type ImagePreset = "article" | "thumbnail" | "lightbox" | "og";

const PRESETS: Record<ImagePreset, string> = {
  article: "w=800,f=auto,q=85",
  thumbnail: "w=200,h=150,fit=cover,f=auto",
  lightbox: "w=1600,f=auto",
  og: "w=1200,h=630,fit=cover,f=jpg",
};

export function imageUrl(src: string, preset: ImagePreset = "article"): string {
  if (!src.startsWith(R2_PUBLIC_URL)) return src;
  return `/img/${PRESETS[preset]}/${src}`;
}
