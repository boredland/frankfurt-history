import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, createFileRoute, useNavigate, useRouter } from "@tanstack/react-router";
import { z } from "zod";
import { MapView } from "~/components/MapView";
import type { Theme } from "~/lib/themes";

const mapSearchSchema = z.object({
  layers: z.string().optional(),
  filters: z.string().optional(),
  lat: z.coerce.number().optional(),
  lng: z.coerce.number().optional(),
  z: z.coerce.number().optional(),
});

export const Route = createFileRoute("/$lang")({
  params: {
    parse: (params) => {
      if (params.lang !== "de" && params.lang !== "en") {
        throw new Error("Invalid language");
      }
      return { lang: params.lang as "de" | "en" };
    },
    stringify: (params) => ({ lang: params.lang }),
  },
  validateSearch: mapSearchSchema,
  component: LangLayout,
});

function parseLayersParam(param: string | undefined): Set<number> | null {
  if (!param) return null;
  const ids = param
    .split(",")
    .map((s) => parseInt(s, 10))
    .filter((n) => !isNaN(n));
  return ids.length > 0 ? new Set(ids) : null;
}

function serializeLayers(active: Set<number>, allIds: number[]): string | undefined {
  if (active.size === allIds.length) return undefined;
  if (active.size === 0) return "none";
  return [...active].sort((a, b) => a - b).join(",");
}

function LanguageToggle({ lang }: { lang: string }) {
  const navigate = useNavigate();
  const router = useRouter();

  function switchLang(target: "de" | "en") {
    const pathname = router.state.location.pathname;
    const rest = pathname.replace(/^\/(de|en)/, "");
    const search = router.state.location.search;
    navigate({ to: `/${target}${rest}`, search });
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      <button
        onClick={() => switchLang("de")}
        className={`px-2 py-1 rounded cursor-pointer ${lang === "de" ? "bg-sepia text-paper" : "text-faded hover:text-ink"}`}
      >
        DE
      </button>
      <button
        onClick={() => switchLang("en")}
        className={`px-2 py-1 rounded cursor-pointer ${lang === "en" ? "bg-sepia text-paper" : "text-faded hover:text-ink"}`}
      >
        EN
      </button>
    </div>
  );
}

function LangLayout() {
  const { lang } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();

  const [allThemeIds, setAllThemeIds] = useState<number[]>([]);
  const layersFromUrl = useMemo(() => parseLayersParam(search.layers), [search.layers]);

  useEffect(() => {
    fetch("/data/themes.json")
      .then((r) => r.json())
      .then((themes: Theme[]) => setAllThemeIds(themes.map((t) => t.id)))
      .catch(console.error);
  }, []);

  const activeLayers = useMemo(() => {
    if (layersFromUrl) return layersFromUrl;
    return new Set(allThemeIds);
  }, [layersFromUrl, allThemeIds]);

  const handleToggleLayer = useCallback(
    (themeId: number) => {
      const next = new Set(activeLayers);
      if (next.has(themeId)) {
        next.delete(themeId);
      } else {
        next.add(themeId);
      }
      navigate({
        search: (prev) => ({
          ...prev,
          layers: serializeLayers(next, allThemeIds),
        }),
        replace: true,
      });
    },
    [activeLayers, allThemeIds, navigate],
  );

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center justify-between px-4 py-2 border-b border-sepia-light bg-paper z-10">
        <h1 className="font-serif text-lg font-bold tracking-tight text-ink">
          Frankfurt History
        </h1>
        <LanguageToggle lang={lang} />
      </header>
      <div className="flex-1 flex overflow-hidden relative">
        <MapView
          lat={search.lat}
          lng={search.lng}
          zoom={search.z}
          lang={lang}
          activeLayers={activeLayers}
          onToggleLayer={handleToggleLayer}
        />
        <Outlet />
      </div>
    </div>
  );
}
