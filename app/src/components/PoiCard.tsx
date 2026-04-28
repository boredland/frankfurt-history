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
      className="w-full flex items-center gap-0 rounded-lg overflow-hidden bg-paper border border-sepia-light/60 hover:border-sepia hover:shadow-sm cursor-pointer transition-all text-left group"
    >
      <div
        className="self-stretch w-1 shrink-0 rounded-l-lg"
        style={{ backgroundColor: THEME_COLORS[theme] || "#8B7355" }}
      />
      <div className="relative shrink-0 ml-1.5 my-1.5">
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
          >
            <svg
              width="16"
              height="20"
              viewBox="0 0 18 26"
              fill="none"
              role="img"
              aria-label={theme}
            >
              <path
                d="M9 0C4.03 0 0 4.03 0 9c0 6.75 9 16.5 9 16.5s9-9.75 9-16.5C18 4.03 13.97 0 9 0z"
                fill={THEME_COLORS[theme] || "#8B7355"}
                opacity={0.6}
              />
              <circle cx="9" cy="9" r="3.5" fill="white" opacity={0.5} />
            </svg>
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1 ml-2.5 py-1.5">
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
        className="shrink-0 text-sepia-light group-hover:text-sepia transition-colors mr-1.5"
        role="img"
        aria-label="Open"
      >
        <path d="M5 3l4 4-4 4" />
      </svg>
    </button>
  );
}
