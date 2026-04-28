import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "~/lib/i18n";
import type { Theme } from "~/lib/themes";
import { themeColor, themeTitle } from "~/lib/themes";

interface FilterPanelProps {
  theme: Theme;
  activeFilters: Set<string>;
  onSetFilters: (filters: Set<string>) => void;
  onBack: () => void;
  lang: string;
}

const PIN_COLORS = [
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

export function FilterPanel({
  theme,
  activeFilters,
  onSetFilters,
  onBack,
  lang,
}: FilterPanelProps) {
  const [filters, setFilters] = useState<string[]>([]);
  const [filterLabels, setFilterLabels] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(true);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/data/${theme.slug}.geojson`)
      .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
      .then((gj) => {
        const set = new Set<string>();
        const labels: Record<string, string> = {};
        for (const f of gj.features) {
          const p = f.properties as Record<string, unknown>;
          const de = (p.filters as string[] | undefined) ?? [];
          const en = (p.filters_en as string[] | undefined) ?? [];
          for (let i = 0; i < de.length; i++) {
            set.add(de[i]);
            if (en[i] && !labels[de[i]]) labels[de[i]] = en[i];
          }
        }
        setFilters([...set].sort());
        setFilterLabels(labels);
      })
      .catch(console.error);
  }, [theme.slug]);

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
      setOpen(false);
    }
  }, []);

  useEffect(() => {
    document.addEventListener("pointerdown", handleClickOutside);
    return () =>
      document.removeEventListener("pointerdown", handleClickOutside);
  }, [handleClickOutside]);

  function handleToggle(filter: string) {
    if (activeFilters.size === 0) {
      onSetFilters(new Set(filters.filter((f) => f !== filter)));
    } else if (activeFilters.has(filter)) {
      const next = new Set(activeFilters);
      next.delete(filter);
      onSetFilters(
        next.size === 0 || filters.every((f) => next.has(f)) ? new Set() : next,
      );
    } else {
      const next = new Set(activeFilters);
      next.add(filter);
      onSetFilters(filters.every((f) => next.has(f)) ? new Set() : next);
    }
  }

  if (!open) {
    return (
      <div className="absolute top-3 left-3 z-20" ref={panelRef}>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="bg-paper border border-sepia-light rounded-lg px-3 py-2 shadow-md hover:shadow-lg transition-shadow cursor-pointer flex items-center gap-2 text-sm"
        >
          <span
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: themeColor(theme.slug) }}
          />
          <span className="text-ink font-medium">
            {themeTitle(theme, lang)}
          </span>
        </button>
      </div>
    );
  }

  return (
    <div
      ref={panelRef}
      className="absolute top-3 left-3 z-20 bg-paper border border-sepia-light rounded-lg shadow-lg w-72 overflow-hidden"
    >
      <div className="px-3 py-2.5 border-b border-sepia-light">
        <div className="flex items-center justify-between mb-1.5">
          <button
            type="button"
            onClick={onBack}
            className="text-xs text-sepia hover:text-ink flex items-center gap-1 cursor-pointer transition-colors"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              role="img"
              aria-label="Back"
            >
              <path d="M8 2L4 6l4 4" />
            </svg>
            {t("themes", lang)}
          </button>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="w-5 h-5 flex items-center justify-center rounded-full text-faded hover:text-ink hover:bg-sepia-light/30 cursor-pointer transition-colors"
            aria-label={t("close", lang)}
          >
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              role="img"
              aria-label="Close"
            >
              <path d="M2 2l6 6M8 2l-6 6" />
            </svg>
          </button>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: themeColor(theme.slug) }}
          />
          <span className="font-serif font-bold text-ink">
            {themeTitle(theme, lang)}
          </span>
        </div>
      </div>

      {filters.length > 0 && (
        <>
          <div className="px-3 py-2 border-b border-sepia-light flex items-center justify-between">
            <span className="text-xs text-faded uppercase tracking-wider">
              Filter
            </span>
            {activeFilters.size > 0 && (
              <button
                type="button"
                onClick={() => onSetFilters(new Set())}
                className="text-xs text-sepia hover:text-ink cursor-pointer transition-colors"
              >
                {t("showAll", lang)}
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto py-1">
            {filters.map((filter, i) => {
              const isActive =
                activeFilters.size === 0 || activeFilters.has(filter);
              const pinColor = PIN_COLORS[i % PIN_COLORS.length];
              const label =
                lang === "en" && filterLabels[filter]
                  ? filterLabels[filter]
                  : filter;

              return (
                <button
                  key={filter}
                  type="button"
                  onClick={() => handleToggle(filter)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 hover:bg-sepia-light/30 transition-colors cursor-pointer text-left ${
                    isActive ? "bg-sepia-light/15" : ""
                  }`}
                >
                  <svg
                    width="18"
                    height="22"
                    viewBox="0 0 18 26"
                    fill="none"
                    className="shrink-0"
                    role="img"
                    aria-label={filter}
                  >
                    <path
                      d="M9 0C4.03 0 0 4.03 0 9c0 6.75 9 16.5 9 16.5s9-9.75 9-16.5C18 4.03 13.97 0 9 0z"
                      fill={pinColor}
                      opacity={isActive ? 1 : 0.25}
                    />
                    <circle
                      cx="9"
                      cy="9"
                      r="3.5"
                      fill="white"
                      opacity={isActive ? 0.5 : 0.15}
                    />
                  </svg>
                  <span
                    className={`text-sm flex-1 ${isActive ? "text-ink" : "text-faded"}`}
                  >
                    {label}
                  </span>
                  {isActive && (
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      className="shrink-0 text-sepia"
                      role="img"
                      aria-label="Selected"
                    >
                      <path
                        d="M3 8l3 3 7-7"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
