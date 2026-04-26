import { useNavigate } from "@tanstack/react-router";
import { imageUrl } from "~/lib/imageUrl";
import { THEME_COLORS } from "~/lib/themes";

interface PoiCardProps {
  lang: string;
  title: string;
  subtitle?: string;
  theme: string;
  slug: string;
  thumb?: string;
  onBeforeNavigate?: () => void;
}

export function PoiCard({
  lang,
  title,
  subtitle,
  theme,
  slug,
  thumb,
  onBeforeNavigate,
}: PoiCardProps) {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => {
        onBeforeNavigate?.();
        navigate({
          to: "/$lang/$theme/$slug",
          params: { lang: lang as "de" | "en", theme, slug },
          search: (prev: Record<string, unknown>) => prev,
        });
      }}
      className="w-full flex items-center gap-2.5 rounded-lg overflow-hidden bg-paper border border-sepia-light/60 hover:border-sepia hover:shadow-sm cursor-pointer transition-all text-left group p-1.5"
    >
      <div className="relative shrink-0">
        {thumb ? (
          <img
            src={imageUrl(thumb, "thumbnail")}
            alt=""
            className="w-11 h-11 rounded object-cover bg-sepia-light/30"
          />
        ) : (
          <div
            className="w-11 h-11 rounded flex items-center justify-center"
            style={{
              backgroundColor: `${THEME_COLORS[theme] || "#8B7355"}20`,
            }}
          />
        )}
        <span
          className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-paper"
          style={{ backgroundColor: THEME_COLORS[theme] || "#8B7355" }}
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-ink leading-snug group-hover:text-sepia transition-colors line-clamp-2">
          {title}
        </div>
        {subtitle && subtitle !== title && (
          <div className="text-[11px] text-faded mt-0.5 leading-tight truncate">
            {subtitle}
          </div>
        )}
      </div>
      <svg
        width="14"
        height="14"
        viewBox="0 0 14 14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="shrink-0 text-sepia-light group-hover:text-sepia transition-colors"
        role="img"
        aria-label="Open"
      >
        <path d="M5 3l4 4-4 4" />
      </svg>
    </button>
  );
}
