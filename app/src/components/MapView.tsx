import { useCallback, useEffect, useMemo, useState } from "react";
import Map, {
  Layer,
  type MapLayerMouseEvent,
  Source,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import { useNavigate } from "@tanstack/react-router";
import { themeColor, type Theme } from "~/lib/themes";
import { LayerPicker } from "./LayerPicker";

const FRANKFURT_CENTER = { lng: 8.68, lat: 50.11 };
const DEFAULT_ZOOM = 13;

const BASEMAP_STYLE =
  "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

interface MapViewProps {
  lat?: number;
  lng?: number;
  zoom?: number;
  lang: string;
  activeLayers: Set<number>;
  onToggleLayer: (themeId: number) => void;
}

export function MapView({
  lat,
  lng,
  zoom,
  lang,
  activeLayers,
  onToggleLayer,
}: MapViewProps) {
  const navigate = useNavigate();
  const [themes, setThemes] = useState<Theme[]>([]);

  useEffect(() => {
    fetch("/data/themes.json")
      .then((r) => r.json())
      .then(setThemes)
      .catch(console.error);
  }, []);

  const initialView = useMemo(
    () => ({
      longitude: lng ?? FRANKFURT_CENTER.lng,
      latitude: lat ?? FRANKFURT_CENTER.lat,
      zoom: zoom ?? DEFAULT_ZOOM,
    }),
    [],
  );

  const handleClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (!feature?.properties) return;

      const props = feature.properties;
      if (props.cluster) return;

      const theme = props.theme as string;
      const slug = props.slug as string;
      if (theme && slug) {
        navigate({
          to: "/$lang/$theme/$slug",
          params: { lang, theme, slug },
          search: (prev) => prev,
        });
      }
    },
    [navigate, lang],
  );

  const handleMoveEnd = useCallback(
    (e: ViewStateChangeEvent) => {
      const { longitude, latitude, zoom: z } = e.viewState;
      navigate({
        search: (prev) => ({
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
    () => visibleThemes.map((t) => `poi-${t.slug}`),
    [visibleThemes],
  );

  return (
    <Map
      initialViewState={initialView}
      mapStyle={BASEMAP_STYLE}
      onMoveEnd={handleMoveEnd}
      onClick={handleClick}
      interactiveLayerIds={interactiveLayerIds}
      style={{ width: "100%", height: "100%" }}
      cursor="auto"
    >
      {visibleThemes.map((theme) => (
        <ThemeLayer key={theme.slug} theme={theme} />
      ))}
      <LayerPicker
        themes={themes}
        activeLayers={activeLayers}
        onToggle={onToggleLayer}
      />
    </Map>
  );
}

function ThemeLayer({ theme }: { theme: Theme }) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(
    null,
  );
  const color = themeColor(theme.slug);

  useEffect(() => {
    fetch(`/data/${theme.slug}.geojson`)
      .then((r) => r.json())
      .then(setGeojson)
      .catch(console.error);
  }, [theme.slug]);

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
          "circle-radius": [
            "step",
            ["get", "point_count"],
            15,
            10,
            20,
            50,
            25,
          ],
        }}
      />
      <Layer
        id={`cluster-count-${theme.slug}`}
        type="symbol"
        filter={["has", "point_count"]}
        layout={{
          "text-field": "{point_count_abbreviated}",
          "text-size": 11,
        }}
        paint={{
          "text-color": "#FAF8F5",
        }}
      />
      <Layer
        id={`poi-${theme.slug}`}
        type="circle"
        filter={["!", ["has", "point_count"]]}
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
