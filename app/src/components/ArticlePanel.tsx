import { useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";

interface ArticlePanelProps {
  lang: string;
  theme: string;
  slug: string;
}

interface ArticleData {
  title: string;
  subtitle?: string;
  html: string;
}

interface ArticleJson {
  frontmatter: Record<string, string>;
  body: string;
}

function markdownToHtml(md: string): string {
  let html = md;
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  html = html.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    '<img alt="$1" src="$2" loading="lazy" />',
  );
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<![*])\*([^*\n]+)\*(?![*])/g, "<em>$1</em>");
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);
  const paragraphs = html
    .split(/\n{2,}/)
    .map((block) => {
      block = block.trim();
      if (!block) return "";
      if (
        block.startsWith("<h") ||
        block.startsWith("<ul") ||
        block.startsWith("<img") ||
        block.startsWith("<a ")
      )
        return block;
      return `<p>${block.replace(/\n/g, "<br/>")}</p>`;
    })
    .filter(Boolean);
  return paragraphs.join("\n");
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

type SheetSnap = "peek" | "half" | "full";

export function ArticlePanel({ lang, theme, slug }: ArticlePanelProps) {
  const navigate = useNavigate();
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
        setArticle({
          title: json.frontmatter.title || slug,
          subtitle: json.frontmatter.subtitle,
          html: markdownToHtml(json.body),
        });
      })
      .catch(() => setArticle(null))
      .finally(() => setLoading(false));
  }, [theme, slug, lang]);

  const handleClose = useCallback(() => {
    navigate({
      to: "/$lang",
      params: { lang: lang as "de" | "en" },
      search: (prev: Record<string, unknown>) => prev,
    });
  }, [navigate, lang]);

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
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-faded">
            Loading...
          </div>
        ) : article ? (
          <div className="article-body">
            <div dangerouslySetInnerHTML={{ __html: article.html }} />
          </div>
        ) : (
          <div className="text-faded text-center py-8">Article not found.</div>
        )}
      </div>
    </>
  );

  return (
    <>
      {/* Desktop: side panel */}
      <div className="hidden sm:flex absolute right-0 top-0 bottom-0 w-[420px] bg-paper border-l border-sepia-light shadow-lg z-20 flex-col overflow-hidden animate-slide-in">
        {content}
      </div>

      {/* Mobile: bottom sheet */}
      <div
        ref={sheetRef}
        className="sm:hidden fixed left-0 right-0 bottom-0 z-20 bg-paper rounded-t-2xl shadow-[0_-4px_20px_rgba(0,0,0,0.15)] flex flex-col overflow-hidden transition-[height] duration-200 ease-out"
        style={{ height: snapHeights[snap] }}
      >
        {/* Drag handle */}
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
