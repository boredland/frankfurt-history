import { createContext, useCallback, useContext, useState } from "react";

interface NavigationState {
  routeGeometry: GeoJSON.LineString | null;
  setRouteGeometry: (geometry: GeoJSON.LineString | null) => void;
}

const NavigationContext = createContext<NavigationState>({
  routeGeometry: null,
  setRouteGeometry: () => {},
});

export function NavigationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [routeGeometry, setRouteGeometryRaw] =
    useState<GeoJSON.LineString | null>(null);

  const setRouteGeometry = useCallback(
    (geometry: GeoJSON.LineString | null) => {
      setRouteGeometryRaw(geometry);
    },
    [],
  );

  return (
    <NavigationContext value={{ routeGeometry, setRouteGeometry }}>
      {children}
    </NavigationContext>
  );
}

export function useNavigation() {
  return useContext(NavigationContext);
}
