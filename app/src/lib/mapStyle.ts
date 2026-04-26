import type { StyleSpecification } from "maplibre-gl";
import { layersWithPartialCustomTheme } from "protomaps-themes-base";

const PMTILES_URL = "/frankfurt.pmtiles";

const archivalTheme = {
  background: "#FAF8F5",
  earth: "#F0EBE4",
  park_a: "#E6DFCF",
  park_b: "#E0D9C8",
  hospital: "#EDE7DB",
  industrial: "#EDE9E0",
  school: "#EDE7DB",
  wood_a: "#DDD7C5",
  wood_b: "#D8D1BF",
  pedestrian: "#F0EBE4",
  scrub_a: "#E2DBC9",
  scrub_b: "#DDD5C3",
  glacier: "#E8E4DC",
  sand: "#E8E0CC",
  beach: "#E8E0CC",
  aerodrome: "#EDE9E0",
  runway: "#D4CFC4",
  water: "#C4CECE",
  zoo: "#E6DFCF",
  military: "#E0D9C8",

  tunnel_other_casing: "#D4C5AD",
  tunnel_minor_casing: "#D4C5AD",
  tunnel_link_casing: "#D4C5AD",
  tunnel_major_casing: "#C8B99A",
  tunnel_highway_casing: "#C8B99A",
  tunnel_other: "#F0EBE4",
  tunnel_minor: "#F0EBE4",
  tunnel_link: "#EDE7DB",
  tunnel_major: "#EDE7DB",
  tunnel_highway: "#E8DFD0",

  pier: "#E8E1D4",
  buildings: "#E0D9CC",

  minor_service_casing: "#D4C5AD",
  minor_casing: "#D4C5AD",
  link_casing: "#C8B99A",
  major_casing_late: "#C8B99A",
  highway_casing_late: "#B8A98A",
  other: "#F5F0E8",
  minor_service: "#F5F0E8",
  minor_a: "#F5F0E8",
  minor_b: "#F0EBE4",
  link: "#EDE7DB",
  major_casing_early: "#C8B99A",
  major: "#EDE7DB",
  highway_casing_early: "#B8A98A",
  highway: "#E8DFD0",
  railway: "#C8B99A",
  boundaries: "#B8A98A",

  waterway_label: "#8B9B9B",

  bridges_other_casing: "#D4C5AD",
  bridges_minor_casing: "#D4C5AD",
  bridges_link_casing: "#C8B99A",
  bridges_major_casing: "#C8B99A",
  bridges_highway_casing: "#B8A98A",
  bridges_other: "#F5F0E8",
  bridges_minor: "#F5F0E8",
  bridges_link: "#EDE7DB",
  bridges_major: "#EDE7DB",
  bridges_highway: "#E8DFD0",

  roads_label_minor: "#8B7355",
  roads_label_minor_halo: "#FAF8F5",
  roads_label_major: "#6B6560",
  roads_label_major_halo: "#FAF8F5",
  ocean_label: "#8B9B9B",
  peak_label: "#8B7355",
  subplace_label: "#8B7355",
  subplace_label_halo: "#FAF8F5",
  city_label: "#6B6560",
  city_label_halo: "#FAF8F5",
  state_label: "#8B7355",
  state_label_halo: "#FAF8F5",
  country_label: "#6B6560",
  address_label: "#A09080",
  address_label_halo: "#FAF8F5",
  landcover: {
    grassland: "#E4DDD0",
    barren: "#E8E0CC",
    urban_area: "#EDE9E0",
    farmland: "#E2DBC9",
    glacier: "#E8E4DC",
    scrub: "#DDD5C3",
    forest: "#D8D1BF",
  },
};

export function createMapStyle(): StyleSpecification {
  return {
    version: 8,
    sprite: "https://protomaps.github.io/basemaps-assets/sprites/v4/light",
    glyphs:
      "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${PMTILES_URL}`,
        attribution:
          '<a href="https://protomaps.com">Protomaps</a> &copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
      },
    },
    layers: layersWithPartialCustomTheme(
      "protomaps",
      "light",
      archivalTheme,
      "de",
      "Latin",
    ) as StyleSpecification["layers"],
  };
}
