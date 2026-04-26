import { createContext, useCallback, useContext, useState } from "react";

interface NavigationState {
  routeGeometry: GeoJSON.LineString | null;
  setRouteGeometry: (geometry: GeoJSON.LineString | null) => void;
  activePoiCoords: [number, number] | null;
  setActivePoiCoords: (coords: [number, number] | null) => void;
}

const NavigationContext = createContext<NavigationState>({
  routeGeometry: null,
  setRouteGeometry: () => {},
  activePoiCoords: null,
  setActivePoiCoords: () => {},
});

export function NavigationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [routeGeometry, setRouteGeometryRaw] =
    useState<GeoJSON.LineString | null>(null);
  const [activePoiCoords, setActivePoiCoordsRaw] = useState<
    [number, number] | null
  >(null);

  const setRouteGeometry = useCallback(
    (geometry: GeoJSON.LineString | null) => {
      setRouteGeometryRaw(geometry);
    },
    [],
  );

  const setActivePoiCoords = useCallback((coords: [number, number] | null) => {
    setActivePoiCoordsRaw(coords);
  }, []);

  return (
    <NavigationContext
      value={{
        routeGeometry,
        setRouteGeometry,
        activePoiCoords,
        setActivePoiCoords,
      }}
    >
      {children}
    </NavigationContext>
  );
}

export function useNavigation() {
  return useContext(NavigationContext);
}
