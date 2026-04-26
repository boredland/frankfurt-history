import { useCallback, useRef, useState } from "react";

interface BeforeAfterSliderProps {
  beforeSrc: string;
  afterSrc: string;
  beforeAlt?: string;
  afterAlt?: string;
  beforeCaption?: string;
  afterCaption?: string;
}

export function BeforeAfterSlider({
  beforeSrc,
  afterSrc,
  beforeAlt = "Before",
  afterAlt = "After",
  beforeCaption,
  afterCaption,
}: BeforeAfterSliderProps) {
  const [position, setPosition] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const updatePosition = useCallback((clientX: number) => {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setPosition(pct);
  }, []);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      isDragging.current = true;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      updatePosition(e.clientX);
    },
    [updatePosition],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return;
      updatePosition(e.clientX);
    },
    [updatePosition],
  );

  const onPointerUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  return (
    <div className="my-4">
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-lg cursor-col-resize select-none aspect-[4/3]"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {/* After image (full width, behind) */}
        <img
          src={afterSrc}
          alt={afterAlt}
          className="absolute inset-0 w-full h-full object-cover"
          draggable={false}
        />

        {/* Before image (clipped) */}
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ width: `${position}%` }}
        >
          <img
            src={beforeSrc}
            alt={beforeAlt}
            className="absolute inset-0 w-full h-full object-cover"
            style={{
              width: containerRef.current
                ? `${containerRef.current.offsetWidth}px`
                : "100vw",
              maxWidth: "none",
            }}
            draggable={false}
          />
        </div>

        {/* Divider line */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg"
          style={{ left: `${position}%`, transform: "translateX(-50%)" }}
        >
          {/* Handle */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 bg-white rounded-full shadow-md flex items-center justify-center">
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="#8B7355"
              strokeWidth="2"
              role="img"
              aria-label="Drag to compare"
            >
              <path d="M5 3L2 8l3 5M11 3l3 5-3 5" />
            </svg>
          </div>
        </div>

        {/* Labels */}
        <span className="absolute top-2 left-2 bg-black/50 text-white text-xs px-2 py-0.5 rounded">
          Before
        </span>
        <span className="absolute top-2 right-2 bg-black/50 text-white text-xs px-2 py-0.5 rounded">
          After
        </span>
      </div>

      {/* Captions */}
      {(beforeCaption || afterCaption) && (
        <div className="flex justify-between text-xs text-faded mt-1 px-1">
          <span>{beforeCaption}</span>
          <span>{afterCaption}</span>
        </div>
      )}
    </div>
  );
}
