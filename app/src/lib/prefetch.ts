import { imageUrl } from "./imageUrl";
import { SNAP_TOLERANCE, THEME_SLUGS } from "./themes";

interface PrefetchPoi {
  lng: number;
  lat: number;
  theme: string;
  slug: string;
  thumb: string;
  address: string;
}

let allPoisCache: PrefetchPoi[] | null = null;

async function getAllPois(): Promise<PrefetchPoi[]> {
  if (allPoisCache) return allPoisCache;

  const results = await Promise.all(
    THEME_SLUGS.map((s) =>
      fetch(`/data/${s}.geojson`)
        .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
        .then((gj) => ({ theme: s, features: gj.features }))
        .catch(() => ({ theme: s, features: [] as GeoJSON.Feature[] })),
    ),
  );

  const pois: PrefetchPoi[] = [];
  for (const { theme, features } of results) {
    for (const f of features) {
      const p = f.properties as Record<string, unknown>;
      const coords = (f.geometry as GeoJSON.Point).coordinates;
      pois.push({
        lng: coords[0] ?? 0,
        lat: coords[1] ?? 0,
        theme,
        slug: (p.slug as string) || "",
        thumb: (p.thumb as string) || "",
        address: (p.address as string) || "",
      });
    }
  }

  allPoisCache = pois;
  return pois;
}

function findNearby(
  pois: PrefetchPoi[],
  lat: number,
  lng: number,
  address: string,
  excludeSlug: string,
  limit: number,
): PrefetchPoi[] {
  const hasNum = (a: string) => /\d/.test(a);

  const withDistance = pois
    .filter((p) => p.slug !== excludeSlug)
    .map((p) => {
      const addrMatch =
        address &&
        p.address &&
        hasNum(address) &&
        hasNum(p.address) &&
        address === p.address;
      const dist = Math.sqrt((p.lng - lng) ** 2 + (p.lat - lat) ** 2);
      return { ...p, dist, addrMatch };
    })
    .filter(
      (p) =>
        p.addrMatch ||
        p.dist < Math.max(SNAP_TOLERANCE.lng, SNAP_TOLERANCE.lat) * 20,
    );

  withDistance.sort((a, b) => {
    if (a.addrMatch && !b.addrMatch) return -1;
    if (!a.addrMatch && b.addrMatch) return 1;
    return a.dist - b.dist;
  });

  return withDistance.slice(0, limit);
}

function prefetchUrl(url: string) {
  fetch(url, { priority: "low" } as RequestInit).catch(() => {});
}

export async function prefetchNearbyContent(
  lang: string,
  theme: string,
  slug: string,
  lat: number,
  lng: number,
) {
  const pois = await getAllPois();

  const currentAddress = pois.find((p) => p.slug === slug)?.address || "";

  const nearby = findNearby(pois, lat, lng, currentAddress, slug, 10);

  for (const poi of nearby) {
    prefetchUrl(`/data/content/${lang}/${poi.theme}/${poi.slug}.json`);

    if (poi.thumb) {
      prefetchUrl(imageUrl(poi.thumb, "thumbnail"));
      prefetchUrl(imageUrl(poi.thumb, "article"));
    }
  }

  prefetchUrl(`/data/routes/${theme}/${slug}.json`);
}
