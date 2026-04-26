export interface RouteStep {
  instruction: string;
  distance_m: number;
  duration_s: number;
}

export interface CachedRoute {
  target_slug: string;
  target_title: string;
  straight_distance_m: number;
  distance_m: number;
  duration_s: number;
  geometry?: GeoJSON.LineString;
  steps?: RouteStep[];
}

export interface LiveRoute {
  geometry: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  steps: RouteStep[];
}

export async function loadCachedRoutes(
  theme: string,
  slug: string,
): Promise<CachedRoute[]> {
  try {
    const r = await fetch(`/data/routes/${theme}/${slug}.json`);
    if (!r.ok) return [];
    return (await r.json()) as CachedRoute[];
  } catch {
    return [];
  }
}

export async function fetchLiveRoute(
  startLng: number,
  startLat: number,
  endLng: number,
  endLat: number,
): Promise<LiveRoute | null> {
  try {
    const r = await fetch(
      `https://api.openrouteservice.org/v2/directions/foot-walking?start=${startLng},${startLat}&end=${endLng},${endLat}`,
    );
    if (!r.ok) return null;
    const data = await r.json();
    const feat = data.features?.[0];
    if (!feat) return null;
    const summary = feat.properties?.summary;
    const segments = feat.properties?.segments?.[0];
    return {
      geometry: feat.geometry as GeoJSON.LineString,
      distance_m: Math.round(summary?.distance ?? 0),
      duration_s: Math.round(summary?.duration ?? 0),
      steps: (segments?.steps ?? []).map(
        (s: { instruction: string; distance: number; duration: number }) => ({
          instruction: s.instruction,
          distance_m: Math.round(s.distance),
          duration_s: Math.round(s.duration),
        }),
      ),
    };
  } catch {
    return null;
  }
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

export function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m > 0 ? `${h} h ${m} min` : `${h} h`;
}
