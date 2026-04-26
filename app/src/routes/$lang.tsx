import {
  createFileRoute,
  Outlet,
  useMatch,
  useNavigate,
  useRouter,
} from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";
import { MapView } from "~/components/MapView";
import { NearbyPanel } from "~/components/NearbyPanel";
import { SearchDialog } from "~/components/SearchDialog";
import { NavigationProvider } from "~/lib/NavigationContext";
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
    .filter((n) => !Number.isNaN(n));
  return ids.length > 0 ? new Set(ids) : null;
}

function serializeLayers(
  active: Set<number>,
  allIds: number[],
): string | undefined {
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
        type="button"
        onClick={() => switchLang("de")}
        className={`px-2 py-1 rounded cursor-pointer ${lang === "de" ? "bg-sepia text-paper" : "text-faded hover:text-ink"}`}
      >
        DE
      </button>
      <button
        type="button"
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
  const articleMatch = useMatch({
    from: "/$lang/$theme/$slug",
    shouldThrow: false,
  });
  const activeSlug = articleMatch?.params?.slug;

  const [searchOpen, setSearchOpen] = useState(false);
  const [nearbyOpen, setNearbyOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const [allThemeIds, setAllThemeIds] = useState<number[]>([]);
  const layersFromUrl = useMemo(
    () => parseLayersParam(search.layers),
    [search.layers],
  );

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
        to: ".",
        search: (prev: object) => ({
          ...prev,
          layers: serializeLayers(next, allThemeIds),
        }),
        replace: true,
      });
    },
    [activeLayers, allThemeIds, navigate],
  );

  return (
    <NavigationProvider>
      <div className="h-full flex flex-col">
        <header className="flex items-center justify-between px-4 py-2 border-b border-sepia-light bg-paper z-10">
          <h1 className="font-serif text-lg font-bold tracking-tight text-ink">
            Frankfurt History
          </h1>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="flex items-center gap-1.5 px-2 py-1 text-faded hover:text-ink rounded cursor-pointer transition-colors"
              aria-label={lang === "de" ? "Suche" : "Search"}
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 18 18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                role="img"
                aria-label="Search"
              >
                <circle cx="7.5" cy="7.5" r="5.5" />
                <path d="M11.5 11.5L16 16" />
              </svg>
              <kbd className="hidden sm:inline-block text-[10px] border border-sepia-light rounded px-1 py-0.5 text-faded/70">
                /K
              </kbd>
            </button>
            <button
              type="button"
              onClick={() => setNearbyOpen(true)}
              className="p-1.5 text-faded hover:text-red-oxide rounded cursor-pointer transition-colors"
              aria-label={lang === "de" ? "In der Nähe" : "Nearby"}
              title={lang === "de" ? "In der Nähe" : "Nearby"}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                role="img"
                aria-label="Nearby"
              >
                <path d="M8 1C5.24 1 3 3.24 3 6c0 3.75 5 9 5 9s5-5.25 5-9c0-2.76-2.24-5-5-5z" />
                <circle cx="8" cy="6" r="1.5" />
              </svg>
            </button>
            <LanguageToggle lang={lang} />
          </div>
        </header>
        <div className="flex-1 flex overflow-hidden relative">
          <MapView
            lat={search.lat}
            lng={search.lng}
            zoom={search.z}
            lang={lang}
            activeLayers={activeLayers}
            onToggleLayer={handleToggleLayer}
            activeSlug={activeSlug}
          />
          <Outlet />
        </div>
      </div>
      <SearchDialog
        lang={lang}
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
      />
      <NearbyPanel
        lang={lang}
        open={nearbyOpen}
        onClose={() => setNearbyOpen(false)}
      />
    </NavigationProvider>
  );
}
