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

function parseImageRef(line: string): ImageRef | null {
  const imgMatch = line.match(/!\[([^\]]*)\]\(([^)]+)\)/);
  if (!imgMatch) return null;
  return { src: imgMatch[2], alt: imgMatch[1] };
}

function parseCaptionLine(line: string): string | undefined {
  const match = line.match(/^\*(.+)\*$/);
  return match ? match[1] : undefined;
}

function extractImagesFromLines(lines: string[]): ImageRef[] {
  const images: ImageRef[] = [];
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
      images.push(img);
    }
  }
  return images;
}

export interface ParsedArticle {
  sections: ArticleSection[];
  allImages: ImageRef[];
}

export function parseArticleBody(body: string): ParsedArticle {
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
      addImages(extractImagesFromLines(currentTextLines));
      const html = markdownBlockToHtml(raw);
      if (html.trim()) {
        sections.push({ type: "html", content: html });
      }
    }
    currentTextLines = [];
  }

  function flushGallery() {
    const images = extractImagesFromLines(galleryLines);
    if (images.length === 0) {
      inGallery = false;
      galleryLines = [];
      return;
    }

    addImages(images);

    if (
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
    // Standard galleries are now handled by the hero image + thumbnail strip
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
