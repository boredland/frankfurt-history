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

function parseFrontmatter(text: string): {
  attrs: Record<string, string>;
  body: string;
} {
  if (!text.startsWith("---")) return { attrs: {}, body: text };
  const end = text.indexOf("---", 3);
  if (end === -1) return { attrs: {}, body: text };
  const fmBlock = text.slice(3, end);
  const attrs: Record<string, string> = {};
  for (const line of fmBlock.split("\n")) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const val = line
      .slice(idx + 1)
      .trim()
      .replace(/^["']|["']$/g, "");
    attrs[key] = val;
  }
  return { attrs, body: text.slice(end + 3).trim() };
}

function markdownToHtml(md: string): string {
  let html = md;
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2" loading="lazy" />');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(
    /(?<![*])\*([^*\n]+)\*(?![*])/g,
    "<em>$1</em>",
  );
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

export function ArticlePanel({ lang, theme, slug }: ArticlePanelProps) {
  const navigate = useNavigate();
  const [article, setArticle] = useState<ArticleData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const langPath = `/content/${lang}/${theme}/${slug}.md`;
    const fallbackPath = `/content/${theme}/${slug}.md`;
    fetch(langPath)
      .then((r) => {
        if (r.ok) return r;
        return fetch(fallbackPath);
      })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.text();
      })
      .then((text) => {
        const { attrs, body } = parseFrontmatter(text);
        setArticle({
          title: attrs.title || slug,
          subtitle: attrs.subtitle,
          html: markdownToHtml(body),
        });
      })
      .catch((err) => {
        console.error("Failed to load article:", err);
        setArticle(null);
      })
      .finally(() => setLoading(false));
  }, [theme, slug, lang]);

  const handleClose = () => {
    navigate({
      to: "/$lang",
      params: { lang },
      search: (prev) => prev,
    });
  };

  return (
    <div className="absolute right-0 top-0 bottom-0 w-full sm:w-[420px] bg-paper border-l border-sepia-light shadow-lg z-20 flex flex-col overflow-hidden animate-slide-in">
      <div className="flex items-center justify-between px-4 py-3 border-b border-sepia-light">
        <span className="text-xs text-faded uppercase tracking-wider">
          {theme.replace(/-/g, " ")}
        </span>
        <button
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
          <div className="text-faded text-center py-8">
            Article not found.
          </div>
        )}
      </div>
    </div>
  );
}
