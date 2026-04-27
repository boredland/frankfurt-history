import {
  createFileRoute,
  Outlet,
  useMatch,
  useNavigate,
  useRouter,
} from "@tanstack/react-router";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { z } from "zod";

import { t } from "~/lib/i18n";

const MapView = lazy(() =>
  import("~/components/MapView").then((m) => ({ default: m.MapView })),
);

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
  if (param === "none") return new Set();
  const ids = param
    .split(",")
    .map((s) => parseInt(s, 10))
    .filter((n) => !Number.isNaN(n));
  return ids.length > 0 ? new Set(ids) : null;
}

function serializeLayers(
  active: Set<number>,
  _allIds: number[],
): string | undefined {
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
      .then((r) => r.json() as Promise<Theme[]>)
      .then((themes) => setAllThemeIds(themes.map((t) => t.id)))
      .catch(console.error);
  }, []);

  const activeLayers = useMemo(() => {
    if (layersFromUrl) return layersFromUrl;
    // Exclude "Leichte Sprache" (id 5) from default selection
    return new Set(allThemeIds.filter((id) => id !== 5));
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

  const handleSetLayers = useCallback(
    (ids: Set<number>) => {
      navigate({
        to: ".",
        search: (prev: object) => ({
          ...prev,
          layers: serializeLayers(ids, allThemeIds),
        }),
        replace: true,
      });
    },
    [allThemeIds, navigate],
  );

  return (
    <NavigationProvider>
      <div className="h-full flex flex-col">
        <header className="flex items-center justify-between px-4 py-2 border-b border-sepia-light bg-paper z-10">
          <div className="flex items-center gap-2">
            <h1 className="font-serif text-lg font-bold tracking-tight text-ink">
              Frankfurt History
            </h1>
            <a
              href="https://github.com/boredland/frankfurt-history"
              target="_blank"
              rel="noopener"
              className="text-faded/40 hover:text-faded transition-colors"
              title="Source on GitHub"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="currentColor"
                role="img"
                aria-label="GitHub"
              >
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
              </svg>
            </a>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="flex items-center gap-1.5 px-2 py-1 text-faded hover:text-ink rounded cursor-pointer transition-colors"
              aria-label={t("search", lang)}
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
              aria-label={t("nearby", lang)}
              title={t("nearby", lang)}
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
          <Suspense
            fallback={
              <div
                className="w-full h-full"
                style={{ background: "#FAF8F5" }}
              />
            }
          >
            <MapView
              lat={search.lat}
              lng={search.lng}
              zoom={search.z}
              lang={lang}
              activeLayers={activeLayers}
              onToggleLayer={handleToggleLayer}
              onSetLayers={handleSetLayers}
              activeSlug={activeSlug}
            />
          </Suspense>
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
