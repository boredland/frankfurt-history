import { createServerFn } from "@tanstack/react-start/server";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

interface ArticleJson {
  frontmatter: Record<string, string>;
  body: string;
}

export const getArticle = createServerFn({ method: "GET" })
  .validator(
    (input: { lang: string; theme: string; slug: string }) => input,
  )
  .handler(async ({ data: { lang, theme, slug } }): Promise<ArticleJson | null> => {
    const dataDir = join(process.cwd(), "public", "data", "content");
    const poiId = slug.match(/^(\d+)/)?.[1];

    // Try exact slug match in the requested language
    const langPath = join(dataDir, lang, theme, `${slug}.json`);
    try {
      const text = await readFile(langPath, "utf-8");
      return JSON.parse(text);
    } catch {}

    // Try ID-based lookup for cross-language slug mismatches
    if (poiId) {
      const indexPath = join(dataDir, lang, theme, "_index.json");
      try {
        const indexText = await readFile(indexPath, "utf-8");
        const index: Record<string, string> = JSON.parse(indexText);
        const filename = index[poiId];
        if (filename) {
          const text = await readFile(join(dataDir, lang, theme, filename), "utf-8");
          return JSON.parse(text);
        }
      } catch {}
    }

    // Fallback to flat layout (no lang prefix)
    const flatPath = join(dataDir, theme, `${slug}.json`);
    try {
      const text = await readFile(flatPath, "utf-8");
      return JSON.parse(text);
    } catch {}

    return null;
  });
