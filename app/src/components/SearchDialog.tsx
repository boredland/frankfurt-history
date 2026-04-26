import { useNavigate } from "@tanstack/react-router";
import Fuse from "fuse.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { THEME_COLORS, type Theme } from "~/lib/themes";

interface POIEntry {
  title: string;
  subtitle: string;
  theme: string;
  themeTitle: string;
  slug: string;
  lat: number;
  lng: number;
}

interface SearchDialogProps {
  lang: string;
  open: boolean;
  onClose: () => void;
}

export function SearchDialog({ lang, open, onClose }: SearchDialogProps) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [pois, setPois] = useState<POIEntry[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelectedIndex(0);

    Promise.all([
      fetch("/data/themes.json").then((r) => r.json()) as Promise<Theme[]>,
      ...[
        "feministisches-frankfurt",
        "frankfurt-stories",
        "frankfurt-und-der-ns",
        "leichte-sprache",
        "neues-frankfurt",
        "revolution-1848-49",
      ].map((slug) =>
        fetch(`/data/${slug}.geojson`)
          .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
          .then((gj) => ({
            slug,
            features: gj.features,
          })),
      ),
    ]).then(([themes, ...geojsons]) => {
      const themeMap = new Map(
        (themes as Theme[]).map((t) => [t.slug, t.title]),
      );
      const entries: POIEntry[] = [];
      for (const { slug: themeSlug, features } of geojsons as {
        slug: string;
        features: GeoJSON.Feature[];
      }[]) {
        for (const f of features) {
          const p = f.properties as Record<string, unknown>;
          const coords = (f.geometry as GeoJSON.Point).coordinates;
          entries.push({
            title: (p.title as string) || "",
            subtitle: (p.subtitle as string) || "",
            theme: themeSlug,
            themeTitle: themeMap.get(themeSlug) || themeSlug,
            slug: p.slug as string,
            lng: coords[0] ?? 0,
            lat: coords[1] ?? 0,
          });
        }
      }
      setPois(entries);
    });
  }, [open]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const fuse = useMemo(
    () =>
      new Fuse(pois, {
        keys: [
          { name: "title", weight: 2 },
          { name: "subtitle", weight: 1.5 },
          { name: "themeTitle", weight: 0.5 },
        ],
        threshold: 0.35,
        minMatchCharLength: 2,
      }),
    [pois],
  );

  const results = useMemo(() => {
    if (!query.trim()) return [];
    return fuse.search(query, { limit: 12 }).map((r) => r.item);
  }, [fuse, query]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: reset selection when results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [results]);

  const goTo = useCallback(
    (poi: POIEntry) => {
      onClose();
      navigate({
        to: "/$lang/$theme/$slug",
        params: { lang: lang as "de" | "en", theme: poi.theme, slug: poi.slug },
        search: (prev: Record<string, unknown>) => prev,
      });
    },
    [navigate, lang, onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && results[selectedIndex]) {
        e.preventDefault();
        goTo(results[selectedIndex]);
      } else if (e.key === "Escape") {
        onClose();
      }
    },
    [results, selectedIndex, goTo, onClose],
  );

  useEffect(() => {
    const el = resultsRef.current?.children[selectedIndex] as
      | HTMLElement
      | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4"
      onClick={onClose}
      onKeyDown={undefined}
    >
      <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm" />
      <div
        role="none"
        className="relative w-full max-w-lg bg-paper rounded-xl shadow-2xl border border-sepia-light overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={undefined}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-sepia-light">
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-faded shrink-0"
            role="img"
            aria-label="Search"
          >
            <circle cx="7.5" cy="7.5" r="5.5" />
            <path d="M11.5 11.5L16 16" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={lang === "de" ? "Ort suchen…" : "Search places…"}
            className="flex-1 bg-transparent text-ink placeholder:text-faded/60 outline-none text-sm"
          />
          <kbd className="hidden sm:inline-block text-[10px] text-faded border border-sepia-light rounded px-1.5 py-0.5">
            ESC
          </kbd>
        </div>

        {query.trim() && (
          <div
            ref={resultsRef}
            className="max-h-80 overflow-y-auto overscroll-contain"
          >
            {results.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-faded">
                {lang === "de" ? "Keine Ergebnisse" : "No results"}
              </div>
            ) : (
              results.map((poi, i) => (
                <button
                  key={`${poi.theme}-${poi.slug}`}
                  type="button"
                  onClick={() => goTo(poi)}
                  className={`w-full flex items-start gap-3 px-4 py-2.5 text-left cursor-pointer transition-colors ${
                    i === selectedIndex
                      ? "bg-sepia-light/30"
                      : "hover:bg-sepia-light/15"
                  }`}
                >
                  <span
                    className="mt-1.5 w-2.5 h-2.5 rounded-full shrink-0 border border-paper"
                    style={{
                      backgroundColor: THEME_COLORS[poi.theme] || "#8B7355",
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-ink truncate">{poi.title}</div>
                    {poi.subtitle && (
                      <div className="text-xs text-faded truncate">
                        {poi.subtitle}
                      </div>
                    )}
                  </div>
                  <span className="text-[10px] text-faded/70 uppercase tracking-wider shrink-0 mt-1">
                    {poi.themeTitle.split(" ").slice(0, 2).join(" ")}
                  </span>
                </button>
              ))
            )}
          </div>
        )}

        {!query.trim() && (
          <div className="px-4 py-6 text-center text-xs text-faded">
            {lang === "de"
              ? "Tippe, um nach Orten zu suchen"
              : "Type to search for places"}
          </div>
        )}
      </div>
    </div>
  );
}
