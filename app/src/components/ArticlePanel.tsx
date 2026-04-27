import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "~/lib/i18n";
import { imageUrl } from "~/lib/imageUrl";
import { useNavigation } from "~/lib/NavigationContext";
import {
  type ArticleSection,
  type ImageRef,
  parseArticleBody,
} from "~/lib/parseArticle";
import { prefetchNearbyContent } from "~/lib/prefetch";
import { SNAP_TOLERANCE, THEME_SLUGS } from "~/lib/themes";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { Lightbox } from "./Lightbox";
import { Navigation } from "./Navigation";
import { PoiCard } from "./PoiCard";
import { TTSPlayer } from "./TTSPlayer";

interface ArticlePanelProps {
  lang: string;
  theme: string;
  slug: string;
}

interface ArticleData {
  title: string;
  subtitle?: string;
  sections: ArticleSection[];
  allImages: ImageRef[];
  plainText: string;
  coordinates?: [number, number];
}

interface ArticleJson {
  frontmatter: Record<string, string>;
  body: string;
}

async function fetchJson(url: string): Promise<ArticleJson | null> {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return (await r.json()) as ArticleJson;
  } catch {
    return null;
  }
}

async function fetchArticle(
  lang: string,
  theme: string,
  slug: string,
): Promise<ArticleJson | null> {
  const poiId = slug.match(/^(\d+)/)?.[1];

  const exact = await fetchJson(`/data/content/${lang}/${theme}/${slug}.json`);
  if (exact) return exact;

  if (poiId) {
    const indexResp = await fetchJson(
      `/data/content/${lang}/${theme}/_index.json`,
    );
    if (indexResp) {
      const index = indexResp as unknown as Record<string, string>;
      const filename = index[poiId];
      if (filename) {
        const byId = await fetchJson(
          `/data/content/${lang}/${theme}/${filename}`,
        );
        if (byId) return byId;
      }
    }
  }

  return fetchJson(`/data/content/${theme}/${slug}.json`);
}

function handleShare(lang: string, theme: string, slug: string, title: string) {
  const url = `${window.location.origin}/${lang}/${theme}/${slug}`;
  if (navigator.share) {
    navigator.share({ title, url }).catch(() => {});
  } else {
    navigator.clipboard.writeText(url).then(() => {
      alert("Link copied to clipboard");
    });
  }
}

function handlePrint() {
  window.print();
}

interface SiblingPoi {
  title: string;
  subtitle: string;
  theme: string;
  slug: string;
  thumb: string;
}

function SiblingsAtLocation({
  lang,
  slug,
  lat,
  lng,
}: {
  lang: string;
  slug: string;
  lat: number;
  lng: number;
}) {
  const search = useSearch({ strict: false }) as { layers?: string };
  const [siblings, setSiblings] = useState<SiblingPoi[]>([]);

  useEffect(() => {
    const { lat: TOLERANCE_LAT, lng: TOLERANCE_LNG } = SNAP_TOLERANCE;

    // Parse active layer IDs from URL; undefined = all active
    const layersParam = search.layers;
    const activeLayerIds =
      layersParam === "none"
        ? new Set<number>()
        : layersParam
          ? new Set(
              layersParam
                .split(",")
                .map((s) => Number.parseInt(s, 10))
                .filter((n) => !Number.isNaN(n)),
            )
          : null;

    Promise.all([
      fetch("/data/themes.json")
        .then((r) => r.json() as Promise<{ id: number; slug: string }[]>)
        .catch(() => [] as { id: number; slug: string }[]),
      ...THEME_SLUGS.map((s) =>
        fetch(`/data/${s}.geojson`)
          .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
          .then((gj) => ({ themeSlug: s, features: gj.features }))
          .catch(() => ({ themeSlug: s, features: [] as GeoJSON.Feature[] })),
      ),
    ]).then(([themes, ...results]) => {
      const themeIdBySlug = new Map(
        (themes as { id: number; slug: string }[]).map((t) => [t.slug, t.id]),
      );
      const visibleSlugs = new Set(
        activeLayerIds
          ? [...themeIdBySlug.entries()]
              .filter(([, id]) => activeLayerIds.has(id))
              .map(([slug]) => slug)
          : themeIdBySlug.keys(),
      );
      // Find the clicked POI's address for address-based matching
      let myAddress = "";
      for (const { features } of results) {
        for (const f of features) {
          const p = f.properties as Record<string, unknown>;
          if (p.slug === slug) {
            myAddress = (p.address as string) || "";
            break;
          }
        }
        if (myAddress) break;
      }

      const found: SiblingPoi[] = [];
      for (const { themeSlug, features } of results as {
        themeSlug: string;
        features: GeoJSON.Feature[];
      }[]) {
        if (!visibleSlugs.has(themeSlug)) continue;
        for (const f of features) {
          const p = f.properties as Record<string, unknown>;
          const coords = (f.geometry as GeoJSON.Point).coordinates;
          const poiSlug = p.slug as string;
          if (poiSlug === slug) continue;

          const poiAddress = (p.address as string) || "";
          const hasNum = (a: string) => /\d/.test(a);
          const addressMatch =
            myAddress &&
            poiAddress &&
            hasNum(myAddress) &&
            hasNum(poiAddress) &&
            myAddress === poiAddress;
          const coordMatch =
            Math.abs((coords[0] ?? 0) - lng) < TOLERANCE_LNG &&
            Math.abs((coords[1] ?? 0) - lat) < TOLERANCE_LAT;

          if (addressMatch || coordMatch) {
            found.push({
              title: (p.title as string) || "",
              subtitle: (p.subtitle as string) || "",
              theme: themeSlug,
              slug: poiSlug,
              thumb: (p.thumb as string) || "",
            });
          }
        }
      }
      setSiblings(found);
    });
  }, [slug, lat, lng, search.layers]);

  if (siblings.length === 0) return null;

  return (
    <div className="border-t border-sepia-light px-4 py-3">
      <h3 className="text-xs uppercase tracking-wider text-faded mb-2">
        {t("alsoAtThisLocation", lang)}
      </h3>
      <div className="space-y-1">
        {siblings.map((poi) => (
          <PoiCard
            key={`${poi.theme}-${poi.slug}`}
            lang={lang}
            title={poi.title}
            subtitle={poi.subtitle}
            theme={poi.theme}
            slug={poi.slug}
            thumb={poi.thumb}
          />
        ))}
      </div>
    </div>
  );
}

type SheetSnap = "peek" | "half" | "full";

function GalleryThumbs({
  images,
  onOpen,
}: {
  images: ImageRef[];
  onOpen: (index: number) => void;
}) {
  return (
    <div className="my-3">
      <div className="flex gap-2 overflow-x-auto pb-2 snap-x">
        {images.map((img, i) => (
          <button
            type="button"
            key={img.src}
            onClick={() => onOpen(i)}
            className="snap-start shrink-0 cursor-pointer rounded overflow-hidden border border-sepia-light hover:border-sepia transition-colors"
          >
            <img
              src={imageUrl(img.src, "thumbnail")}
              alt={img.alt}
              className="w-24 h-18 object-cover"
              loading="lazy"
            />
          </button>
        ))}
      </div>
    </div>
  );
}

function ArticleContent({
  sections,
  allImages,
}: {
  sections: ArticleSection[];
  allImages: ImageRef[];
}) {
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const hero = allImages[0];
  const galleryImages = allImages.slice(1);

  return (
    <>
      {hero && (
        <div className="-mx-5 -mt-4 mb-4">
          <button
            type="button"
            onClick={() => setLightboxIdx(galleryImages.length > 0 ? 0 : -1)}
            className="w-full cursor-pointer relative group"
          >
            <img
              src={imageUrl(hero.src, "article")}
              alt={hero.alt}
              className="w-full max-h-64 object-cover"
            />
            {galleryImages.length > 1 && (
              <span className="absolute bottom-2 right-2 bg-ink/60 text-paper text-xs px-2 py-0.5 rounded-full opacity-80 group-hover:opacity-100 transition-opacity print:hidden">
                +{galleryImages.length}
              </span>
            )}
          </button>
          {hero.caption && (
            <p className="text-xs text-faded px-5 mt-1">{hero.caption}</p>
          )}
          {galleryImages.length > 1 && (
            <div className="print:hidden">
              <GalleryThumbs
                images={galleryImages}
                onOpen={(idx) => setLightboxIdx(idx)}
              />
            </div>
          )}
        </div>
      )}

      {sections.map((section, i) => {
        const key = `s-${i}`;
        switch (section.type) {
          case "html":
            return (
              <div
                key={key}
                className="article-body"
                dangerouslySetInnerHTML={{ __html: section.content }}
              />
            );
          case "before-after":
            return (
              <div key={key} className="gallery-section">
                <h2 className="font-serif text-lg text-sepia mt-6 mb-2">
                  Before & After
                </h2>
                <BeforeAfterSlider
                  beforeSrc={imageUrl(section.before.src, "article")}
                  afterSrc={imageUrl(section.after.src, "article")}
                  beforeAlt={section.before.alt}
                  afterAlt={section.after.alt}
                  beforeCaption={section.before.caption}
                  afterCaption={section.after.caption}
                />
              </div>
            );
          case "timeline":
            return (
              <div key={key} className="gallery-section">
                <h2 className="font-serif text-lg text-sepia mt-6 mb-2">
                  Timeline
                </h2>
                <GalleryThumbs
                  images={section.images}
                  onOpen={(idx) => setLightboxIdx(idx)}
                />
              </div>
            );
          default:
            return null;
        }
      })}

      {lightboxIdx !== null && lightboxIdx >= 0 && (
        <Lightbox
          images={galleryImages.map((img) => ({
            src: imageUrl(img.src, "lightbox"),
            alt: img.alt,
            caption: img.caption,
          }))}
          startIndex={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
        />
      )}
      {lightboxIdx === -1 && hero && (
        <Lightbox
          images={[
            {
              src: imageUrl(hero.src, "lightbox"),
              alt: hero.alt,
              caption: hero.caption,
            },
          ]}
          startIndex={0}
          onClose={() => setLightboxIdx(null)}
        />
      )}
    </>
  );
}

export function ArticlePanel({ lang, theme, slug }: ArticlePanelProps) {
  const navigate = useNavigate();
  const { setRouteGeometry, setActivePoiCoords } = useNavigation();
  const [article, setArticle] = useState<ArticleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [snap, setSnap] = useState<SheetSnap>("half");
  const sheetRef = useRef<HTMLDivElement>(null);
  const dragStartY = useRef(0);
  const dragStartSnap = useRef<SheetSnap>("half");

  useEffect(() => {
    setLoading(true);
    setSnap("half");
    fetchArticle(lang, theme, slug)
      .then((json) => {
        if (!json) {
          setArticle(null);
          return;
        }
        const plainText = json.body
          .replace(/^#+\s.+$/gm, "")
          .replace(/!\[[^\]]*\]\([^)]+\)/g, "")
          .replace(/^\*[^*]+\*$/gm, "")
          .replace(/^.*(?:Author|License|Description|Copyright):.*$/gm, "")
          .replace(/^<!-- gallery:\S+ -->$/gm, "")
          .replace(/<!--[^>]+-->/g, "")
          .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
          .replace(/\*\*([^*]+)\*\*/g, "$1")
          .replace(/\n{2,}/g, "\n")
          .trim();
        let coordinates: [number, number] | undefined;
        const coordsRaw = json.frontmatter.coordinates;
        if (coordsRaw) {
          const match = String(coordsRaw).match(
            /\[?\s*([\d.]+)\s*,\s*([\d.]+)\s*\]?/,
          );
          if (match?.[1] && match?.[2]) {
            coordinates = [
              Number.parseFloat(match[1]),
              Number.parseFloat(match[2]),
            ];
          }
        }
        if (coordinates) {
          setActivePoiCoords(coordinates);
          prefetchNearbyContent(
            lang,
            theme,
            slug,
            coordinates[0],
            coordinates[1],
          );
        }
        const parsed = parseArticleBody(json.body);
        setArticle({
          title: json.frontmatter.title || slug,
          subtitle: json.frontmatter.subtitle,
          sections: parsed.sections,
          allImages: parsed.allImages,
          plainText,
          coordinates,
        });
      })
      .catch(() => setArticle(null))
      .finally(() => setLoading(false));
  }, [theme, slug, lang, setActivePoiCoords]);

  const handleClose = useCallback(() => {
    setRouteGeometry(null);
    setActivePoiCoords(null);
    navigate({
      to: "/$lang",
      params: { lang: lang as "de" | "en" },
      search: (prev: Record<string, unknown>) => prev,
    });
  }, [navigate, lang, setRouteGeometry, setActivePoiCoords]);

  const snapHeights: Record<SheetSnap, string> = {
    peek: "120px",
    half: "50vh",
    full: "calc(100vh - 48px)",
  };

  const onDragStart = useCallback(
    (clientY: number) => {
      dragStartY.current = clientY;
      dragStartSnap.current = snap;
    },
    [snap],
  );

  const onDragEnd = useCallback(
    (clientY: number) => {
      const delta = clientY - dragStartY.current;
      const threshold = 60;
      const snaps: SheetSnap[] = ["full", "half", "peek"];
      const currentIdx = snaps.indexOf(dragStartSnap.current);

      if (delta > threshold && currentIdx < snaps.length - 1) {
        const next = snaps[currentIdx + 1];
        if (next === "peek" && delta > 150) {
          handleClose();
        } else if (next) {
          setSnap(next);
        }
      } else if (delta < -threshold && currentIdx > 0) {
        const next = snaps[currentIdx - 1];
        if (next) {
          setSnap(next);
        }
      }
    },
    [handleClose],
  );

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      const touch = e.touches[0];
      if (touch) onDragStart(touch.clientY);
    },
    [onDragStart],
  );

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const touch = e.changedTouches[0];
      if (touch) onDragEnd(touch.clientY);
    },
    [onDragEnd],
  );

  const toolbarButtons = article ? (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => handleShare(lang, theme, slug, article.title)}
        className="p-1.5 text-faded hover:text-sepia rounded cursor-pointer"
        aria-label="Share"
        title="Share"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          role="img"
          aria-label="Share"
        >
          <path d="M6 9l4-4M10 5v4h4M10 5H6M2 8v5a1 1 0 001 1h10a1 1 0 001-1V8" />
        </svg>
      </button>
      <button
        type="button"
        onClick={handlePrint}
        className="p-1.5 text-faded hover:text-sepia rounded cursor-pointer"
        aria-label="Print"
        title="Print"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          role="img"
          aria-label="Print"
        >
          <path d="M4 6V2h8v4M4 12H2V8h12v4h-2M4 10h8v4H4z" />
        </svg>
      </button>
      <button
        type="button"
        onClick={handleClose}
        className="p-1.5 text-faded hover:text-ink rounded cursor-pointer"
        aria-label="Close"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          role="img"
          aria-label="Close"
        >
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      </button>
    </div>
  ) : (
    <button
      type="button"
      onClick={handleClose}
      className="text-faded hover:text-ink text-xl leading-none cursor-pointer"
      aria-label="Close"
    >
      &times;
    </button>
  );

  const content = (
    <>
      <div className="flex items-center justify-between px-4 py-3 border-b border-sepia-light shrink-0">
        <span className="text-xs text-faded uppercase tracking-wider">
          {theme.replace(/-/g, " ")}
        </span>
        {toolbarButtons}
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="px-5 py-4">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-faded">
              Loading...
            </div>
          ) : article ? (
            <ArticleContent
              sections={article.sections}
              allImages={article.allImages}
            />
          ) : (
            <div className="text-faded text-center py-8">
              Article not found.
            </div>
          )}
        </div>
        {article?.coordinates && (
          <SiblingsAtLocation
            lang={lang}
            slug={slug}
            lat={article.coordinates[0]}
            lng={article.coordinates[1]}
          />
        )}
        {article?.coordinates && (
          <Navigation
            lang={lang}
            theme={theme}
            slug={slug}
            poiLng={article.coordinates[1]}
            poiLat={article.coordinates[0]}
            onRouteGeometry={setRouteGeometry}
          />
        )}
      </div>
      {article?.plainText && <TTSPlayer text={article.plainText} lang={lang} />}
    </>
  );

  return (
    <>
      {/* Desktop: side panel */}
      <div className="print-article hidden sm:flex absolute right-0 top-0 bottom-0 w-[420px] bg-paper border-l border-sepia-light shadow-lg z-20 flex-col overflow-hidden animate-slide-in">
        {content}
      </div>

      {/* Mobile: bottom sheet */}
      <div
        ref={sheetRef}
        className="sm:hidden fixed left-0 right-0 bottom-0 z-20 bg-paper rounded-t-2xl shadow-[0_-4px_20px_rgba(0,0,0,0.15)] flex flex-col overflow-hidden transition-[height] duration-200 ease-out"
        style={{ height: snapHeights[snap] }}
      >
        <div
          role="slider"
          tabIndex={0}
          aria-label="Resize panel"
          aria-valuenow={snap === "peek" ? 0 : snap === "half" ? 50 : 100}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={snap}
          className="flex justify-center py-2 cursor-grab active:cursor-grabbing shrink-0"
          onTouchStart={onTouchStart}
          onTouchEnd={onTouchEnd}
          onMouseDown={(e) => onDragStart(e.clientY)}
          onMouseUp={(e) => onDragEnd(e.clientY)}
        >
          <div className="w-10 h-1 rounded-full bg-sepia-light" />
        </div>
        {content}
      </div>
    </>
  );
}
