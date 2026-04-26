const translations = {
  search: { de: "Suche", en: "Search" },
  searchPlaceholder: { de: "Ort suchen…", en: "Search places…" },
  searchEmpty: { de: "Keine Ergebnisse", en: "No results" },
  searchHint: {
    de: "Tippe, um nach Orten zu suchen",
    en: "Type to search for places",
  },
  nearby: { de: "In der Nähe", en: "Nearby" },
  nearbyLocating: {
    de: "Standort wird ermittelt…",
    en: "Getting location…",
  },
  nearbyUnavailable: {
    de: "Standort nicht verfügbar",
    en: "Location not available",
  },
  nearbyDenied: {
    de: "Standortzugriff verweigert",
    en: "Location access denied",
  },
  ttsPlay: { de: "Vorlesen", en: "Read aloud" },
  ttsSpeaking: { de: "Wird vorgelesen…", en: "Reading…" },
  ttsStop: { de: "Stopp", en: "Stop" },
  navigateHere: { de: "Hierher navigieren", en: "Navigate here" },
  locating: { de: "Standort wird ermittelt…", en: "Locating…" },
  nearbyPois: { de: "In der Nähe", en: "Nearby" },
  steps: { de: "Schritte", en: "Steps" },
  hideSteps: { de: "Ausblenden", en: "Hide steps" },
  loading: { de: "Laden…", en: "Loading…" },
  notFound: { de: "Artikel nicht gefunden.", en: "Article not found." },
  share: { de: "Teilen", en: "Share" },
  print: { de: "Drucken", en: "Print" },
  close: { de: "Schließen", en: "Close" },
  layers: { de: "Ebenen", en: "Layers" },
  themes: { de: "Themen", en: "Themes" },
  hideAll: { de: "Alle ausblenden", en: "Hide all" },
  showAll: { de: "Alle einblenden", en: "Show all" },
} satisfies Record<string, { de: string; en: string }>;

export type TranslationKey = keyof typeof translations;

export function t(key: TranslationKey, lang: string): string {
  const entry = translations[key];
  return lang === "de" ? entry.de : entry.en;
}
