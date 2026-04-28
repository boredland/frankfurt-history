import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { t } from "~/lib/i18n";
import type { Theme } from "~/lib/themes";
import { themeColor, themeShortTitle, themeTitle } from "~/lib/themes";

interface LandingPageProps {
  lang: string;
}

export function LandingPage({ lang }: LandingPageProps) {
  const navigate = useNavigate();
  const [themes, setThemes] = useState<Theme[]>([]);

  useEffect(() => {
    fetch("/data/themes.json")
      .then((r) => r.json() as Promise<Theme[]>)
      .then(setThemes)
      .catch(console.error);
  }, []);

  return (
    <div className="flex-1 overflow-y-auto bg-paper">
      <div className="max-w-xl mx-auto px-6 py-10">
        <h2 className="font-serif text-3xl font-bold text-ink mb-8 flex items-center gap-3">
          <span className="w-8 h-0.5 bg-ink inline-block" />
          {t("themes", lang)}
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-5">
          {themes.map((theme) => (
            <button
              key={theme.id}
              type="button"
              onClick={() =>
                navigate({
                  to: "/$lang",
                  params: { lang: lang as "de" | "en" },
                  search: { layers: String(theme.id) },
                })
              }
              className="group cursor-pointer text-left"
            >
              <div
                className="aspect-square rounded-2xl flex items-center justify-center p-4 shadow-sm transition-all duration-200 group-hover:scale-[1.03] group-hover:shadow-lg"
                style={{ backgroundColor: themeColor(theme.slug) }}
              >
                <span className="text-white/90 font-serif text-sm sm:text-base font-bold text-center leading-tight drop-shadow-sm">
                  {themeShortTitle(theme, lang)}
                </span>
              </div>
              <p className="mt-2 text-sm text-ink text-center font-medium leading-tight">
                {themeTitle(theme, lang)}
              </p>
              <p className="text-xs text-faded text-center mt-0.5">
                {theme.poi_count} {t("places", lang)}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
