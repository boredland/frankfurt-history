import { useNavigate } from "@tanstack/react-router";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapGL, {
  GeolocateControl,
  Layer,
  type MapLayerMouseEvent,
  type MapRef,
  Popup,
  Source,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import { createMapStyle } from "~/lib/mapStyle";
import { useNavigation } from "~/lib/NavigationContext";
import { THEME_COLORS, type Theme, themeColor } from "~/lib/themes";
import { LayerPicker } from "./LayerPicker";

if (typeof window !== "undefined") {
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
}

const FRANKFURT_CENTER = { lng: 8.68, lat: 50.11 };
const DEFAULT_ZOOM = 13;
const MAX_BOUNDS: [number, number, number, number] = [8.4, 50.0, 8.9, 50.25];

const MAP_STYLE = createMapStyle();

interface MapViewProps {
  lat?: number;
  lng?: number;
  zoom?: number;
  lang: string;
  activeLayers: Set<number>;
  onToggleLayer: (themeId: number) => void;
  onSetLayers: (ids: Set<number>) => void;
  activeSlug?: string;
}

interface HoverInfo {
  lng: number;
  lat: number;
  title: string;
}

export function MapView({
  lat,
  lng,
  zoom,
  lang,
  activeLayers,
  onToggleLayer,
  onSetLayers,
  activeSlug,
}: MapViewProps) {
  const navigate = useNavigate();
  const mapRef = useRef<MapRef>(null);
  const { routeGeometry, activePoiCoords } = useNavigation();
  const [themes, setThemes] = useState<Theme[]>([]);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [cursor, setCursor] = useState("auto");
  const [poiIndex, setPoiIndex] = useState<Map<string, [number, number]>>(
    new Map(),
  );
  const [stackPopup, setStackPopup] = useState<{
    lng: number;
    lat: number;
    pois: { title: string; subtitle: string; theme: string; slug: string }[];
  } | null>(null);

  useEffect(() => {
    fetch("/data/themes.json")
      .then((r) => r.json() as Promise<Theme[]>)
      .then(setThemes)
      .catch(console.error);
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: initial view should only be set once from URL params
  const initialView = useMemo(
    () => ({
      longitude: lng ?? FRANKFURT_CENTER.lng,
      latitude: lat ?? FRANKFURT_CENTER.lat,
      zoom: zoom ?? DEFAULT_ZOOM,
    }),
    [],
  );

  const allPois = useRef<
    {
      lng: number;
      lat: number;
      title: string;
      subtitle: string;
      theme: string;
      slug: string;
    }[]
  >([]);
  const registeredSlugs = useRef<Set<string>>(new Set());

  const registerPois = useCallback((features: GeoJSON.Feature[]) => {
    for (const f of features) {
      const p = f.properties as Record<string, unknown>;
      const coords = (f.geometry as GeoJSON.Point).coordinates;
      if (!coords || !p?.slug) continue;
      const slug = p.slug as string;
      if (registeredSlugs.current.has(slug)) continue;
      registeredSlugs.current.add(slug);
      allPois.current.push({
        lng: coords[0] ?? 0,
        lat: coords[1] ?? 0,
        title: (p.title as string) || "",
        subtitle: (p.subtitle as string) || "",
        theme: (p.theme as string) || "",
        slug,
      });
    }

    setPoiIndex((prev) => {
      const next = new Map(prev);
      for (const f of features) {
        const slug = (f.properties as Record<string, unknown>)?.slug as string;
        const coords = (f.geometry as GeoJSON.Point).coordinates;
        if (slug && coords) {
          next.set(slug, [coords[0] ?? 0, coords[1] ?? 0]);
        }
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (!activeSlug || !mapRef.current) return;
    // Prefer coordinates from article frontmatter (available before GeoJSON loads)
    const coords = activePoiCoords
      ? [activePoiCoords[1], activePoiCoords[0]]
      : poiIndex.get(activeSlug);
    if (!coords) return;
    mapRef.current.flyTo({
      center: [coords[0], coords[1]],
      zoom: Math.max(mapRef.current.getZoom(), 15),
      duration: 800,
      padding: { right: 220, top: 0, bottom: 0, left: 0 },
    });
  }, [activeSlug, activePoiCoords, poiIndex]);

  const visibleThemeSlugs = useMemo(() => {
    const slugs = new Set<string>();
    for (const th of themes) {
      if (activeLayers.has(th.id)) slugs.add(th.slug);
    }
    return slugs;
  }, [themes, activeLayers]);

  const handleClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (!feature?.properties) return;

      const props = feature.properties;
      if (props.cluster) return;

      const coords = (feature.geometry as GeoJSON.Point).coordinates;
      const clickLng = coords[0] ?? 0;
      const clickLat = coords[1] ?? 0;

      // ~15m tolerance: 0.000135° lat, 0.00021° lng at 50°N
      const TOLERANCE_LAT = 0.000135;
      const TOLERANCE_LNG = 0.00021;

      const nearby = allPois.current.filter(
        (p) =>
          visibleThemeSlugs.has(p.theme) &&
          Math.abs(p.lng - clickLng) < TOLERANCE_LNG &&
          Math.abs(p.lat - clickLat) < TOLERANCE_LAT,
      );

      if (nearby.length > 1) {
        setHover(null);
        setStackPopup({ lng: clickLng, lat: clickLat, pois: nearby });
        return;
      }

      const theme = props.theme as string;
      const slug = props.slug as string;
      if (theme && slug) {
        setHover(null);
        setStackPopup(null);
        navigate({
          to: "/$lang/$theme/$slug",
          params: { lang: lang as "de" | "en", theme, slug },
          search: (prev: Record<string, unknown>) => prev,
        });
      }
    },
    [navigate, lang, visibleThemeSlugs],
  );

  const handleMouseEnter = useCallback((e: MapLayerMouseEvent) => {
    setCursor("pointer");
    const feature = e.features?.[0];
    if (!feature?.properties || feature.properties.cluster) return;
    const coords = (feature.geometry as GeoJSON.Point).coordinates;
    setHover({
      lng: coords[0] ?? 0,
      lat: coords[1] ?? 0,
      title: feature.properties.title as string,
    });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setCursor("auto");
    setHover(null);
  }, []);

  const handleMoveEnd = useCallback(
    (e: ViewStateChangeEvent) => {
      const { longitude, latitude, zoom: z } = e.viewState;
      navigate({
        to: ".",
        search: (prev: object) => ({
          ...prev,
          lat: Math.round(latitude * 10000) / 10000,
          lng: Math.round(longitude * 10000) / 10000,
          z: Math.round(z * 10) / 10,
        }),
        replace: true,
      });
    },
    [navigate],
  );

  const visibleThemes = useMemo(
    () => themes.filter((t) => activeLayers.has(t.id)),
    [themes, activeLayers],
  );

  const interactiveLayerIds = useMemo(
    () =>
      visibleThemes.flatMap((t) => [`poi-${t.slug}`, `poi-active-${t.slug}`]),
    [visibleThemes],
  );

  return (
    <MapGL
      ref={mapRef}
      initialViewState={initialView}
      mapStyle={MAP_STYLE}
      onMoveEnd={handleMoveEnd}
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      interactiveLayerIds={interactiveLayerIds}
      maxBounds={MAX_BOUNDS}
      style={{ width: "100%", height: "100%" }}
      cursor={cursor}
    >
      {visibleThemes.map((theme) => (
        <ThemeLayer
          key={theme.slug}
          theme={theme}
          activeSlug={activeSlug}
          onFeaturesLoaded={registerPois}
        />
      ))}
      <LayerPicker
        themes={themes}
        activeLayers={activeLayers}
        onToggle={onToggleLayer}
        onSetAll={onSetLayers}
        lang={lang}
      />
      {routeGeometry && (
        <Source
          id="route-line"
          type="geojson"
          data={{
            type: "Feature",
            properties: {},
            geometry: routeGeometry,
          }}
        >
          <Layer
            id="route-line-bg"
            type="line"
            paint={{
              "line-color": "#FAF8F5",
              "line-width": 6,
              "line-opacity": 0.8,
            }}
          />
          <Layer
            id="route-line-fg"
            type="line"
            paint={{
              "line-color": "#8B7355",
              "line-width": 3,
              "line-dasharray": [2, 1],
            }}
          />
        </Source>
      )}
      <GeolocateControl position="bottom-right" trackUserLocation />
      {hover && !stackPopup && (
        <Popup
          longitude={hover.lng}
          latitude={hover.lat}
          closeButton={false}
          closeOnClick={false}
          anchor="bottom"
          offset={12}
          className="poi-tooltip"
        >
          <span className="text-xs font-medium text-ink">{hover.title}</span>
        </Popup>
      )}
      {stackPopup && (
        <Popup
          longitude={stackPopup.lng}
          latitude={stackPopup.lat}
          closeButton={false}
          closeOnClick={false}
          anchor="bottom"
          offset={16}
          maxWidth="320px"
          className="stack-popup"
        >
          <div className="-mx-2.5 -my-1.5">
            <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5">
              <span className="text-[11px] font-medium text-faded uppercase tracking-wider">
                {stackPopup.pois.length} {lang === "de" ? "Orte" : "places"}
              </span>
              <button
                type="button"
                onClick={() => setStackPopup(null)}
                className="text-faded/60 hover:text-ink cursor-pointer -mr-1 p-0.5"
                aria-label="Close"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  role="img"
                  aria-label="Close"
                >
                  <path d="M3 3l6 6M9 3l-6 6" />
                </svg>
              </button>
            </div>
            <div className="max-h-56 overflow-y-auto px-2 pb-2 space-y-1">
              {stackPopup.pois.map((poi) => (
                <button
                  key={`${poi.theme}-${poi.slug}`}
                  type="button"
                  onClick={() => {
                    setStackPopup(null);
                    navigate({
                      to: "/$lang/$theme/$slug",
                      params: {
                        lang: lang as "de" | "en",
                        theme: poi.theme,
                        slug: poi.slug,
                      },
                      search: (prev: Record<string, unknown>) => prev,
                    });
                  }}
                  className="w-full flex items-stretch rounded-lg overflow-hidden bg-paper border border-sepia-light/60 hover:border-sepia hover:shadow-sm cursor-pointer transition-all text-left group"
                >
                  <div
                    className="w-1 shrink-0"
                    style={{
                      backgroundColor: THEME_COLORS[poi.theme] || "#8B7355",
                    }}
                  />
                  <div className="min-w-0 px-2.5 py-2">
                    <div className="text-[13px] font-medium text-ink leading-snug group-hover:text-sepia transition-colors">
                      {poi.title}
                    </div>
                    {poi.subtitle && poi.subtitle !== poi.title && (
                      <div className="text-[11px] text-faded mt-0.5 leading-tight">
                        {poi.subtitle}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center pr-2 shrink-0 text-sepia-light group-hover:text-sepia transition-colors">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 14 14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      role="img"
                      aria-label="Open"
                    >
                      <path d="M5 3l4 4-4 4" />
                    </svg>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </Popup>
      )}
    </MapGL>
  );
}

function ThemeLayer({
  theme,
  activeSlug,
  onFeaturesLoaded,
}: {
  theme: Theme;
  activeSlug?: string;
  onFeaturesLoaded: (features: GeoJSON.Feature[]) => void;
}) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(
    null,
  );
  const color = themeColor(theme.slug);

  useEffect(() => {
    fetch(`/data/${theme.slug}.geojson`)
      .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
      .then((data) => {
        setGeojson(data);
        onFeaturesLoaded(data.features);
      })
      .catch(console.error);
  }, [theme.slug, onFeaturesLoaded]);

  if (!geojson) return null;

  return (
    <Source
      id={`theme-${theme.slug}`}
      type="geojson"
      data={geojson}
      cluster={true}
      clusterMaxZoom={14}
      clusterRadius={50}
    >
      <Layer
        id={`cluster-${theme.slug}`}
        type="circle"
        filter={["has", "point_count"]}
        paint={{
          "circle-color": color,
          "circle-opacity": 0.6,
          "circle-radius": ["step", ["get", "point_count"], 15, 10, 20, 50, 25],
        }}
      />
      <Layer
        id={`cluster-count-${theme.slug}`}
        type="symbol"
        filter={["has", "point_count"]}
        layout={{
          "text-field": "{point_count_abbreviated}",
          "text-font": ["Noto Sans Regular"],
          "text-size": 11,
        }}
        paint={{
          "text-color": "#FAF8F5",
        }}
      />
      {/* Active POI highlight ring */}
      <Layer
        id={`poi-active-${theme.slug}`}
        type="circle"
        filter={[
          "all",
          ["!", ["has", "point_count"]],
          ["==", ["get", "slug"], activeSlug ?? ""],
        ]}
        paint={{
          "circle-color": "#A0522D",
          "circle-radius": 10,
          "circle-stroke-width": 3,
          "circle-stroke-color": "#FAF8F5",
          "circle-opacity": 1,
        }}
      />
      {/* Regular POIs */}
      <Layer
        id={`poi-${theme.slug}`}
        type="circle"
        filter={[
          "all",
          ["!", ["has", "point_count"]],
          ["!=", ["get", "slug"], activeSlug ?? ""],
        ]}
        paint={{
          "circle-color": color,
          "circle-radius": 6,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#FAF8F5",
        }}
      />
    </Source>
  );
}
