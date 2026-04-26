import { useState } from "react";
import { t } from "~/lib/i18n";
import { type Theme, themeColor } from "~/lib/themes";

interface LayerPickerProps {
  themes: Theme[];
  activeLayers: Set<number>;
  onToggle: (themeId: number) => void;
  onSetAll: (ids: Set<number>) => void;
  lang: string;
}

export function LayerPicker({
  themes,
  activeLayers,
  onToggle,
  onSetAll,
  lang,
}: LayerPickerProps) {
  const [open, setOpen] = useState(true);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="absolute top-3 left-3 z-20 bg-paper border border-sepia-light rounded-lg px-3 py-2 shadow-md hover:shadow-lg transition-shadow cursor-pointer flex items-center gap-2 text-sm"
        aria-label="Toggle layers"
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
                  onSetAll(new Set(themes.map((t) => t.id)));
                }
              }}
              className="text-xs text-sepia hover:text-ink cursor-pointer"
            >
              {activeLayers.size === themes.length
                ? t("hideAll", lang)
                : t("showAll", lang)}
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {themes.map((theme) => {
              const active = activeLayers.has(theme.id);
              return (
                <button
                  type="button"
                  key={theme.id}
                  onClick={() => onToggle(theme.id)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-sepia-light/30 transition-colors cursor-pointer text-left"
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
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
