export interface Theme {
  id: number;
  title: string;
  title_en?: string;
  short_title: string;
  short_title_en?: string;
  slug: string;
  poi_count: number;
}

export function themeTitle(theme: Theme, lang: string): string {
  return (lang === "en" && theme.title_en) || theme.title;
}

export function themeShortTitle(theme: Theme, lang: string): string {
  if (lang === "en" && theme.short_title_en) return theme.short_title_en;
  return theme.short_title || theme.title;
}

export interface POIProperties {
  id: number;
  title: string;
  subtitle?: string;
  theme: string;
  slug: string;
  categories?: string[];
  filters?: string[];
}

export const THEME_SLUGS = [
  "feministisches-frankfurt",
  "frankfurt-stories",
  "frankfurt-und-der-ns",
  "leichte-sprache",
  "neues-frankfurt",
  "revolution-1848-49",
] as const;

export const SNAP_TOLERANCE = {
  lat: 0.000045,
  lng: 0.00007,
} as const;

export const THEME_COLORS: Record<string, string> = {
  "frankfurt-und-der-ns": "#7A5C3E",
  "revolution-1848-49": "#A0522D",
  "frankfurt-stories": "#6B7B5E",
  "neues-frankfurt": "#5B6B7A",
  "feministisches-frankfurt": "#8B6B7A",
  "leichte-sprache": "#7A7B5E",
  stolpersteine: "#B8860B",
};

export function themeColor(slug: string): string {
  return THEME_COLORS[slug] ?? "#8B7355";
}

export const FILTER_COLORS = [
  "#7B68AE",
  "#C1666B",
  "#D4A373",
  "#E07A3E",
  "#5B8266",
  "#D4AF37",
  "#8B6CAB",
  "#4A7C8F",
  "#9B7653",
  "#6B8F71",
];

export function buildFilterColorMap(
  features: GeoJSON.Feature[],
): Record<string, string> {
  const set = new Set<string>();
  for (const f of features) {
    const filters = (f.properties as Record<string, unknown>).filters as
      | string[]
      | undefined;
    if (filters) for (const filt of filters) set.add(filt);
  }
  const sorted = [...set].sort();
  const map: Record<string, string> = {};
  for (let i = 0; i < sorted.length; i++) {
    map[sorted[i]] = FILTER_COLORS[i % FILTER_COLORS.length];
  }
  return map;
}
