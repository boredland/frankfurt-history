import { useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { t } from "~/lib/i18n";
import { formatDistance } from "~/lib/routing";
import { THEME_COLORS, THEME_SLUGS } from "~/lib/themes";

interface NearbyPOI {
  title: string;
  subtitle: string;
  theme: string;
  slug: string;
  distance: number;
  lat: number;
  lng: number;
}

interface NearbyPanelProps {
  lang: string;
  open: boolean;
  onClose: () => void;
}

function haversine(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const R = 6371000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function NearbyPanel({ lang, open, onClose }: NearbyPanelProps) {
  const navigate = useNavigate();
  const [nearby, setNearby] = useState<NearbyPOI[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);

    if (!navigator.geolocation) {
      setError(t("nearbyUnavailable", lang));
      setLoading(false);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        const geojsonFiles = THEME_SLUGS;

        const all: NearbyPOI[] = [];
        for (const slug of geojsonFiles) {
          try {
            const r = await fetch(`/data/${slug}.geojson`);
            const gj = (await r.json()) as GeoJSON.FeatureCollection;
            for (const f of gj.features) {
              const p = f.properties as Record<string, unknown>;
              const coords = (f.geometry as GeoJSON.Point).coordinates;
              const dist = haversine(
                latitude,
                longitude,
                coords[1] ?? 0,
                coords[0] ?? 0,
              );
              all.push({
                title: (p.title as string) || "",
                subtitle: (p.subtitle as string) || "",
                theme: slug,
                slug: p.slug as string,
                distance: dist,
                lat: coords[1] ?? 0,
                lng: coords[0] ?? 0,
              });
            }
          } catch {
            /* skip failed loads */
          }
        }

        all.sort((a, b) => a.distance - b.distance);
        setNearby(all.slice(0, 20));
        setLoading(false);
      },
      () => {
        setError(t("nearbyDenied", lang));
        setLoading(false);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, [open, lang]);

  const goTo = useCallback(
    (poi: NearbyPOI) => {
      onClose();
      navigate({
        to: "/$lang/$theme/$slug",
        params: {
          lang: lang as "de" | "en",
          theme: poi.theme,
          slug: poi.slug,
        },
        search: (prev: Record<string, unknown>) => prev,
      });
    },
    [navigate, lang, onClose],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      className="fixed inset-0 z-50 flex items-end sm:items-start sm:justify-center sm:pt-[10vh] px-0 sm:px-4"
      onClick={onClose}
      onKeyDown={undefined}
    >
      <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm" />
      <div
        role="none"
        className="relative w-full sm:max-w-md bg-paper rounded-t-2xl sm:rounded-xl shadow-2xl border border-sepia-light overflow-hidden max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={undefined}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-sepia-light shrink-0">
          <div className="flex items-center gap-2">
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-red-oxide"
              role="img"
              aria-label="Location"
            >
              <path d="M8 1C5.24 1 3 3.24 3 6c0 3.75 5 9 5 9s5-5.25 5-9c0-2.76-2.24-5-5-5z" />
              <circle cx="8" cy="6" r="1.5" />
            </svg>
            <h2 className="font-serif text-sm font-bold text-ink">
              {t("nearby", lang)}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-faded hover:text-ink cursor-pointer"
            aria-label="Close"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              role="img"
              aria-label="Close"
            >
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overscroll-contain">
          {loading && (
            <div className="flex items-center justify-center py-12 text-sm text-faded">
              <svg
                className="animate-spin mr-2 h-4 w-4 text-sepia"
                viewBox="0 0 24 24"
                fill="none"
                role="img"
                aria-label="Loading"
              >
                <circle
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="opacity-25"
                />
                <path
                  d="M4 12a8 8 0 018-8"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
              {t("nearbyLocating", lang)}
            </div>
          )}

          {error && (
            <div className="px-4 py-8 text-center text-sm text-faded">
              {error}
            </div>
          )}

          {!loading && !error && nearby.length > 0 && (
            <div className="divide-y divide-sepia-light/50">
              {nearby.map((poi) => (
                <button
                  key={`${poi.theme}-${poi.slug}`}
                  type="button"
                  onClick={() => goTo(poi)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left cursor-pointer hover:bg-sepia-light/15 transition-colors"
                >
                  <div className="relative shrink-0">
                    <span
                      className="block w-3 h-3 rounded-full border-2 border-paper"
                      style={{
                        backgroundColor: THEME_COLORS[poi.theme] || "#8B7355",
                      }}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-ink truncate">{poi.title}</div>
                    {poi.subtitle && (
                      <div className="text-xs text-faded truncate">
                        {poi.subtitle}
                      </div>
                    )}
                  </div>
                  <span className="text-xs font-medium text-sepia tabular-nums shrink-0">
                    {formatDistance(poi.distance)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
