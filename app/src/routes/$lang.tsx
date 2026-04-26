import { Link, Outlet, createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { MapView } from "~/components/MapView";

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

function LangLayout() {
  const { lang } = Route.useParams();
  const search = Route.useSearch();

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center justify-between px-4 py-2 border-b border-sepia-light bg-paper z-10">
        <h1 className="font-serif text-lg font-bold tracking-tight text-ink">
          Frankfurt History
        </h1>
        <div className="flex items-center gap-2 text-sm">
          <Link
            to="/$lang"
            params={{ lang: "de" }}
            search={search}
            className={`px-2 py-1 rounded ${lang === "de" ? "bg-sepia text-paper" : "text-faded hover:text-ink"}`}
          >
            DE
          </Link>
          <Link
            to="/$lang"
            params={{ lang: "en" }}
            search={search}
            className={`px-2 py-1 rounded ${lang === "en" ? "bg-sepia text-paper" : "text-faded hover:text-ink"}`}
          >
            EN
          </Link>
        </div>
      </header>
      <div className="flex-1 flex overflow-hidden relative">
        <MapView
          lat={search.lat}
          lng={search.lng}
          zoom={search.z}
          lang={lang}
        />
        <Outlet />
      </div>
    </div>
  );
}
