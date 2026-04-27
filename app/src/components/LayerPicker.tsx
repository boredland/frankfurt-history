import { useEffect, useState } from "react";
import { t } from "~/lib/i18n";
import { THEME_SLUGS, type Theme, themeColor } from "~/lib/themes";

interface ThemeFilters {
  [themeSlug: string]: string[];
}

interface LayerPickerProps {
  themes: Theme[];
  activeLayers: Set<number>;
  onToggle: (themeId: number) => void;
  onSetAll: (ids: Set<number>) => void;
  activeFilters: Set<string>;
  onToggleFilter: (filter: string) => void;
  lang: string;
}

export function LayerPicker({
  themes,
  activeLayers,
  onToggle,
  onSetAll,
  activeFilters,
  onToggleFilter,
  lang,
}: LayerPickerProps) {
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [themeFilters, setThemeFilters] = useState<ThemeFilters>({});

  useEffect(() => {
    Promise.all(
      THEME_SLUGS.map((slug) =>
        fetch(`/data/${slug}.geojson`)
          .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
          .then((gj) => {
            const filters = new Set<string>();
            for (const f of gj.features) {
              for (const filt of ((f.properties as Record<string, unknown>)
                .filters as string[]) || []) {
                filters.add(filt);
              }
            }
            return { slug, filters: [...filters].sort() };
          })
          .catch(() => ({ slug, filters: [] as string[] })),
      ),
    ).then((results) => {
      const map: ThemeFilters = {};
      for (const { slug, filters } of results) {
        if (filters.length > 0) map[slug] = filters;
      }
      setThemeFilters(map);
    });
  }, []);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="absolute top-3 left-3 z-20 bg-paper border border-sepia-light rounded-lg px-3 py-2 shadow-md hover:shadow-lg transition-shadow cursor-pointer flex items-center gap-2 text-sm"
        aria-label={t("layers", lang)}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          className="text-sepia"
          role="img"
          aria-label={t("layers", lang)}
        >
          <path
            d="M8 1L1 5l7 4 7-4-7-4z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <path
            d="M1 8l7 4 7-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <path
            d="M1 11l7 4 7-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-ink font-medium">{t("layers", lang)}</span>
        <span className="text-faded">
          {activeLayers.size}/{themes.length}
        </span>
      </button>

      {open && (
        <div className="absolute top-14 left-3 z-20 bg-paper border border-sepia-light rounded-lg shadow-lg w-72 overflow-hidden">
          <div className="px-3 py-2 border-b border-sepia-light flex items-center justify-between">
            <span className="text-xs text-faded uppercase tracking-wider">
              {t("themes", lang)}
            </span>
            <button
              type="button"
              onClick={() => {
                if (activeLayers.size === themes.length) {
                  onSetAll(new Set());
                } else {
                  onSetAll(new Set(themes.map((th) => th.id)));
                }
              }}
              className="text-xs text-sepia hover:text-ink cursor-pointer"
            >
              {activeLayers.size === themes.length
                ? t("hideAll", lang)
                : t("showAll", lang)}
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {themes.map((theme) => {
              const active = activeLayers.has(theme.id);
              const filters = themeFilters[theme.slug];
              const isExpanded = expanded === theme.slug;

              return (
                <div key={theme.id}>
                  <div className="flex items-center">
                    <button
                      type="button"
                      onClick={() => onToggle(theme.id)}
                      className="flex-1 flex items-center gap-3 px-3 py-2.5 hover:bg-sepia-light/30 transition-colors cursor-pointer text-left"
                    >
                      <span
                        className="w-3 h-3 rounded-full shrink-0 border-2 transition-opacity"
                        style={{
                          backgroundColor: active
                            ? themeColor(theme.slug)
                            : "transparent",
                          borderColor: themeColor(theme.slug),
                          opacity: active ? 1 : 0.4,
                        }}
                      />
                      <span
                        className={`text-sm flex-1 ${active ? "text-ink" : "text-faded"}`}
                      >
                        {theme.title}
                      </span>
                      <span className="text-xs text-faded tabular-nums">
                        {theme.poi_count}
                      </span>
                    </button>
                    {filters && active && (
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded(isExpanded ? null : theme.slug)
                        }
                        className="px-2 py-2.5 text-faded hover:text-ink cursor-pointer transition-colors"
                        aria-label="Toggle filters"
                      >
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 12 12"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
                          role="img"
                          aria-label="Expand"
                        >
                          <path d="M3 4.5l3 3 3-3" />
                        </svg>
                      </button>
                    )}
                  </div>
                  {filters && active && isExpanded && (
                    <div className="pl-9 pr-3 pb-2 flex flex-wrap gap-1">
                      {filters.map((filter) => {
                        const filterActive =
                          activeFilters.size === 0 || activeFilters.has(filter);
                        return (
                          <button
                            type="button"
                            key={filter}
                            onClick={() => onToggleFilter(filter)}
                            className={`text-[11px] px-2 py-0.5 rounded-full border cursor-pointer transition-colors ${
                              filterActive
                                ? "border-sepia bg-sepia/10 text-ink"
                                : "border-sepia-light/60 text-faded"
                            }`}
                          >
                            {filter}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
