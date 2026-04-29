export interface ImageRef {
  src: string;
  alt: string;
  caption?: string;
}

export type ArticleSection =
  | { type: "html"; content: string }
  | { type: "gallery"; images: ImageRef[] }
  | { type: "before-after"; before: ImageRef; after: ImageRef }
  | { type: "timeline"; images: ImageRef[] };

function markdownBlockToHtml(md: string): string {
  let html = md;
  // Bare URLs → markdown links (before any HTML is generated)
  html = html.replace(/(?<![(["])(https?:\/\/[^\s<)\]]+)/g, "[$1]($1)");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Strip inline images — they'll be collected separately as gallery images
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)\n?(\*[^*]+\*)?/g, "");
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Require space/start before opening * to avoid matching Gendersternchen (Bürger*innen)
  html = html.replace(/(?<=^|[\s(])\*([^*\n]+)\*(?![*\w])/gm, "<em>$1</em>");
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
      return `<p>${block}</p>`;
    })
    .filter(Boolean);
  return paragraphs.join("\n");
}

function parseImageRef(line: string): ImageRef | null {
  const imgMatch = line.match(/!\[([^\]]*)\]\(([^)]+)\)/);
  if (!imgMatch) return null;
  return { src: imgMatch[2], alt: imgMatch[1] };
}

function parseCaptionLine(line: string): string | undefined {
  const match = line.match(/^\*(.+)\*$/);
  if (!match) return undefined;
  let caption = match[1].trim();
  if (caption.length > 120) return undefined; // Likely not a caption
  // Strip trailing period
  if (caption.endsWith(".") && !caption.endsWith("..")) {
    caption = caption.slice(0, -1);
  }
  return caption;
}

function extractImagesFromLines(
  lines: string[],
  fallbackCaption?: string,
  fallbackSubtitle?: string,
): ImageRef[] {
  const images: ImageRef[] = [];
  const cleanTitle = fallbackCaption
    ? fallbackCaption.replace(/^(Stolpersteine?\s*[—–-]\s*)/i, "").trim()
    : "";

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    const img = parseImageRef(line);
    if (img) {
      const nextLine = lines[i + 1];
      if (nextLine) {
        const caption = parseCaptionLine(nextLine);
        if (caption) {
          img.caption = caption;
          i++;
        }
      }

      if (!img.caption) {
        // Fallback 1: Extract from filename
        const filename = img.src.split("/").pop()?.split(".")[0] || "";
        const rawCleaned = filename
          .replace(/^[a-f0-9]{8,12}_/, "")
          .replace(/_[a-f0-9]{32}/, "")
          .replace(/_original|_medium|_small|_thumbnail/, "")
          .replace(/_/g, " ")
          .trim();

        const housePattern =
          /\b(haus|ansicht|gebaeude|fassade|strasse|straße|str|platz|allee|weg)\b/i;
        const streetSuffixPattern = /(str|strasse|straße|gasse|damm)$/i;
        const isHouse =
          housePattern.test(rawCleaned) ||
          rawCleaned.split(" ").some((w) => streetSuffixPattern.test(w));

        const genericWords = [
          "stolperstein",
          "portrait",
          "bild",
          "foto",
          "aufnahme",
        ];
        const isGeneric =
          rawCleaned.length < 3 ||
          genericWords.some((w) => rawCleaned.toLowerCase().includes(w));

        if (isHouse && fallbackSubtitle) {
          img.caption = fallbackSubtitle;
        } else if (isGeneric && cleanTitle) {
          img.caption = cleanTitle;
        } else if (rawCleaned) {
          // Fallback 2: Interpolate with title casing
          const titleWords = cleanTitle
            .split(/[\s,.;:—–-]+/)
            .filter((w) => w.length > 1);
          const captionWords = rawCleaned
            .split(/\s+/)
            .filter((w) => !/^\d+$/.test(w));

          if (captionWords.length > 0) {
            const refinedWords = captionWords.map((cWord) => {
              const match = titleWords.find(
                (tWord) => tWord.toLowerCase() === cWord.toLowerCase(),
              );
              if (match) return match;
              // Basic capitalization
              return (
                cWord.charAt(0).toUpperCase() + cWord.slice(1).toLowerCase()
              );
            });

            let caption = refinedWords.join(" ");
            if (caption.length > 80) {
              caption = cleanTitle || caption;
            }
            img.caption = caption;
          } else if (fallbackSubtitle) {
            img.caption = fallbackSubtitle;
          } else if (cleanTitle) {
            img.caption = cleanTitle;
          }
        } else if (fallbackSubtitle) {
          img.caption = fallbackSubtitle;
        } else if (cleanTitle) {
          img.caption = cleanTitle;
        }
      }
      images.push(img);
    }
  }
  return images;
}

export interface ParsedArticle {
  sections: ArticleSection[];
  allImages: ImageRef[];
}

export function parseArticleBody(
  body: string,
  fallbackCaption?: string,
  fallbackSubtitle?: string,
): ParsedArticle {
  const sections: ArticleSection[] = [];
  const allImages: ImageRef[] = [];
  const seenSrcs = new Set<string>();

  function addImages(imgs: ImageRef[]) {
    for (const img of imgs) {
      if (!seenSrcs.has(img.src)) {
        seenSrcs.add(img.src);
        allImages.push(img);
      }
    }
  }

  const galleryPattern =
    /^## (?:Gallery|Before & After|Interactive Before & After|Timeline)\s*$/;
  const galleryTypePattern = /^<!-- gallery:([\w-]+) -->$/;
  const skipSectionPattern = /^## (?:Audio|Video|Links)\s*$/;

  const lines = body.split("\n");
  let currentTextLines: string[] = [];
  let inGallery = false;
  let inSkipSection = false;
  let galleryType = "standard";
  let galleryLines: string[] = [];

  function flushText() {
    const raw = currentTextLines.join("\n").trim();
    if (raw) {
      const images = extractImagesFromLines(
        currentTextLines,
        fallbackCaption,
        fallbackSubtitle,
      );
      if (images.length > 0) {
        addImages(images);
        sections.push({ type: "gallery", images });
      }
      const html = markdownBlockToHtml(raw);
      if (html.trim()) {
        sections.push({ type: "html", content: html });
      }
    }
    currentTextLines = [];
  }

  function flushGallery() {
    const images = extractImagesFromLines(
      galleryLines,
      fallbackCaption,
      fallbackSubtitle,
    );
    if (images.length === 0) {
      inGallery = false;
      galleryLines = [];
      return;
    }

    addImages(images);

    if (galleryType === "standard") {
      sections.push({ type: "gallery", images });
    } else if (
      galleryType === "before-after" &&
      images.length >= 2 &&
      images[0] &&
      images[1]
    ) {
      sections.push({
        type: "before-after",
        before: images[0],
        after: images[1],
      });
    } else if (galleryType === "timeline") {
      sections.push({ type: "timeline", images });
    }
    inGallery = false;
    galleryLines = [];
  }

  for (const line of lines) {
    if (skipSectionPattern.test(line)) {
      if (inGallery) flushGallery();
      flushText();
      inSkipSection = true;
      continue;
    }

    if (galleryPattern.test(line)) {
      if (inGallery) flushGallery();
      flushText();
      inGallery = true;
      inSkipSection = false;
      galleryType = "standard";
      galleryLines = [];
      continue;
    }

    if (inSkipSection) {
      if (line.startsWith("## ")) {
        inSkipSection = false;
        currentTextLines.push(line);
      }
      continue;
    }

    if (inGallery) {
      const typeMatch = galleryTypePattern.exec(line);
      if (typeMatch?.[1]) {
        galleryType = typeMatch[1];
        continue;
      }
      if (line.startsWith("## ")) {
        flushGallery();
        currentTextLines.push(line);
        continue;
      }
      galleryLines.push(line);
      continue;
    }

    currentTextLines.push(line);
  }

  if (inGallery) flushGallery();
  flushText();

  return { sections, allImages };
}
