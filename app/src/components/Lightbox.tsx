import { useCallback, useEffect, useState } from "react";

interface LightboxImage {
  src: string;
  alt: string;
  caption?: string;
}

interface LightboxProps {
  images: LightboxImage[];
  startIndex: number;
  onClose: () => void;
}

export function Lightbox({ images, startIndex, onClose }: LightboxProps) {
  const [index, setIndex] = useState(startIndex);
  const image = images[index];

  const prev = useCallback(() => {
    setIndex((i) => (i > 0 ? i - 1 : images.length - 1));
  }, [images.length]);

  const next = useCallback(() => {
    setIndex((i) => (i < images.length - 1 ? i + 1 : 0));
  }, [images.length]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, prev, next]);

  if (!image) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex flex-col items-center justify-center"
      onClick={onClose}
      onKeyDown={() => {}}
      role="dialog"
      aria-label="Image lightbox"
    >
      {/* biome-ignore lint/a11y/noStaticElementInteractions: stops click-through to backdrop */}
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: keyboard handled on parent dialog */}
      <div
        className="relative max-w-[90vw] max-h-[85vh] flex items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={image.src}
          alt={image.alt}
          className="max-w-full max-h-[85vh] object-contain rounded"
        />

        {images.length > 1 && (
          <>
            <button
              type="button"
              onClick={prev}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full w-10 h-10 flex items-center justify-center cursor-pointer"
              aria-label="Previous image"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                role="img"
                aria-label="Previous"
              >
                <path d="M13 4l-6 6 6 6" />
              </svg>
            </button>
            <button
              type="button"
              onClick={next}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full w-10 h-10 flex items-center justify-center cursor-pointer"
              aria-label="Next image"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                role="img"
                aria-label="Next"
              >
                <path d="M7 4l6 6-6 6" />
              </svg>
            </button>
          </>
        )}
      </div>

      {/* Caption + counter */}
      <div className="mt-3 text-center px-4 max-w-2xl">
        {image.caption && (
          <p className="text-white/80 text-sm">{image.caption}</p>
        )}
        {images.length > 1 && (
          <p className="text-white/50 text-xs mt-1">
            {index + 1} / {images.length}
          </p>
        )}
      </div>

      {/* Close button */}
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 text-white/70 hover:text-white text-2xl cursor-pointer"
        aria-label="Close lightbox"
      >
        &times;
      </button>
    </div>
  );
}
