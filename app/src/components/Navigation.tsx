import { useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { t } from "~/lib/i18n";
import {
  type CachedRoute,
  fetchLiveRoute,
  formatDistance,
  formatDuration,
  type LiveRoute,
  loadCachedRoutes,
} from "~/lib/routing";

interface NavigationProps {
  lang: string;
  theme: string;
  slug: string;
  poiLng: number;
  poiLat: number;
  onRouteGeometry: (geometry: GeoJSON.LineString | null) => void;
}

export function Navigation({
  lang,
  theme,
  slug,
  poiLng,
  poiLat,
  onRouteGeometry,
}: NavigationProps) {
  const navigate = useNavigate();
  const [nearby, setNearby] = useState<CachedRoute[]>([]);
  const [liveRoute, setLiveRoute] = useState<LiveRoute | null>(null);
  const [locating, setLocating] = useState(false);
  const [showSteps, setShowSteps] = useState(false);

  useEffect(() => {
    loadCachedRoutes(theme, slug).then(setNearby);
    return () => {
      onRouteGeometry(null);
      setLiveRoute(null);
    };
  }, [theme, slug, onRouteGeometry]);

  const handleNavigateHere = useCallback(() => {
    if (!navigator.geolocation) {
      window.open(
        `https://www.google.com/maps/dir/?api=1&destination=${poiLat},${poiLng}&travelmode=walking`,
        "_blank",
      );
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const route = await fetchLiveRoute(
          pos.coords.longitude,
          pos.coords.latitude,
          poiLng,
          poiLat,
        );
        setLocating(false);
        if (route) {
          setLiveRoute(route);
          onRouteGeometry(route.geometry);
        } else {
          window.open(
            `https://www.google.com/maps/dir/?api=1&destination=${poiLat},${poiLng}&travelmode=walking`,
            "_blank",
          );
        }
      },
      () => {
        setLocating(false);
        window.open(
          `https://www.google.com/maps/dir/?api=1&destination=${poiLat},${poiLng}&travelmode=walking`,
          "_blank",
        );
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, [poiLng, poiLat, onRouteGeometry]);

  const handleNearbyClick = useCallback(
    (route: CachedRoute) => {
      if (route.geometry) {
        onRouteGeometry(route.geometry);
      }
      navigate({
        to: "/$lang/$theme/$slug",
        params: {
          lang: lang as "de" | "en",
          theme,
          slug: route.target_slug,
        },
        search: (prev: Record<string, unknown>) => prev,
      });
    },
    [navigate, lang, theme, onRouteGeometry],
  );

  const dismissRoute = useCallback(() => {
    setLiveRoute(null);
    setShowSteps(false);
    onRouteGeometry(null);
  }, [onRouteGeometry]);

  return (
    <div className="border-t border-sepia-light">
      {liveRoute ? (
        <div className="px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-ink">
                {formatDistance(liveRoute.distance_m)}
              </span>
              <span className="text-xs text-faded">
                {formatDuration(liveRoute.duration_s)} walk
              </span>
            </div>
            <div className="flex items-center gap-1">
              {liveRoute.steps.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowSteps(!showSteps)}
                  className="text-xs text-sepia hover:underline cursor-pointer"
                >
                  {showSteps ? "Hide steps" : "Steps"}
                </button>
              )}
              <button
                type="button"
                onClick={dismissRoute}
                className="p-1 text-faded hover:text-ink cursor-pointer"
                aria-label="Close route"
              >
                <svg
                  width="14"
                  height="14"
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
          </div>
          {showSteps && (
            <ol className="text-xs text-faded space-y-1 max-h-40 overflow-y-auto">
              {liveRoute.steps.map((step, i) => (
                <li key={step.instruction} className="flex gap-2">
                  <span className="text-sepia shrink-0">{i + 1}.</span>
                  <span>{step.instruction}</span>
                  <span className="shrink-0 text-faded/70 ml-auto">
                    {formatDistance(step.distance_m)}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : (
        <div className="px-4 py-3">
          <button
            type="button"
            onClick={handleNavigateHere}
            disabled={locating}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-sepia text-paper rounded text-sm hover:bg-sepia/90 disabled:opacity-50 cursor-pointer"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              role="img"
              aria-label="Navigate"
            >
              <path d="M3 13l5-10 5 10-5-3z" />
            </svg>
            {locating ? t("locating", lang) : t("navigateHere", lang)}
          </button>
        </div>
      )}

      {nearby.length > 0 && (
        <div className="px-4 pb-3">
          <h3 className="text-xs uppercase tracking-wider text-faded mb-2">
            Nearby
          </h3>
          <div className="space-y-1">
            {nearby.map((route) => (
              <button
                key={route.target_slug}
                type="button"
                onClick={() => handleNearbyClick(route)}
                className="w-full flex items-center gap-3 px-2 py-1.5 rounded text-left hover:bg-sepia-light/30 cursor-pointer transition-colors"
              >
                <span className="text-sm text-ink truncate flex-1">
                  {route.target_title}
                </span>
                <span className="text-xs text-faded shrink-0">
                  {formatDistance(route.distance_m)}
                </span>
                <span className="text-xs text-faded shrink-0">
                  {formatDuration(route.duration_s)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
