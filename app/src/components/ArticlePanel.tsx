import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

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

  // Try exact slug in requested language
  const exact = await fetchJson(`/data/content/${lang}/${theme}/${slug}.json`);
  if (exact) return exact;

  // Try ID-based lookup (slugs differ across languages)
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

  // Fallback to flat layout (no lang prefix)
  return fetchJson(`/data/content/${theme}/${slug}.json`);
}

export function ArticlePanel({ lang, theme, slug }: ArticlePanelProps) {
  const navigate = useNavigate();
  const [article, setArticle] = useState<ArticleData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
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

  const handleClose = () => {
    navigate({
      to: "/$lang",
      params: { lang: lang as "de" | "en" },
      search: (prev: Record<string, unknown>) => prev,
    });
  };

  return (
    <div className="absolute right-0 top-0 bottom-0 w-full sm:w-[420px] bg-paper border-l border-sepia-light shadow-lg z-20 flex flex-col overflow-hidden animate-slide-in">
      <div className="flex items-center justify-between px-4 py-3 border-b border-sepia-light">
        <span className="text-xs text-faded uppercase tracking-wider">
          {theme.replace(/-/g, " ")}
        </span>
        <button
          type="button"
          onClick={handleClose}
          className="text-faded hover:text-ink text-xl leading-none cursor-pointer"
          aria-label="Close"
        >
          &times;
        </button>
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
    </div>
  );
}
