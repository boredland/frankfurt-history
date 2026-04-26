import { useCallback, useEffect, useState } from "react";
import { getState, isSupported, speak, stop, subscribe } from "~/lib/tts";

interface TTSPlayerProps {
  text: string;
  lang: string;
}

export function TTSPlayer({ text, lang }: TTSPlayerProps) {
  const [state, setState] = useState<"idle" | "speaking" | "paused">("idle");
  const [rate, setRate] = useState(1);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setState(getState());
    const unsub = subscribe((s) => setState(s));

    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) {
      setReady(true);
    } else {
      speechSynthesis.onvoiceschanged = () => setReady(true);
      setTimeout(() => setReady(true), 2000);
    }

    return unsub;
  }, []);

  useEffect(() => {
    return () => stop();
  }, []);

  const playing = state === "speaking" || state === "paused";

  const handleToggle = useCallback(() => {
    if (playing) {
      stop();
    } else {
      speak(text, lang, rate);
    }
  }, [playing, text, lang, rate]);

  const handleRateChange = useCallback(
    (newRate: number) => {
      setRate(newRate);
      if (playing) {
        speak(text, lang, newRate);
      }
    },
    [playing, text, lang],
  );

  if (!isSupported() || !ready) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-t border-sepia-light bg-paper/80 backdrop-blur-sm">
      <button
        type="button"
        onClick={handleToggle}
        className="w-8 h-8 flex items-center justify-center rounded-full bg-sepia text-paper hover:bg-sepia/80 cursor-pointer"
        aria-label={playing ? "Stop" : "Read aloud"}
        title={playing ? "Stop" : "Read aloud"}
      >
        {playing ? (
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="currentColor"
            role="img"
            aria-label="Stop"
          >
            <rect x="1" y="1" width="10" height="10" rx="1" />
          </svg>
        ) : (
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="currentColor"
            role="img"
            aria-label="Play"
          >
            <path d="M3 1.5v11l9-5.5z" />
          </svg>
        )}
      </button>

      <span className="text-xs text-faded flex-1">
        {playing
          ? lang === "de"
            ? "Wird vorgelesen..."
            : "Reading..."
          : lang === "de"
            ? "Vorlesen"
            : "Read aloud"}
      </span>

      <div className="flex items-center gap-1">
        {[0.75, 1, 1.25, 1.5].map((r) => (
          <button
            type="button"
            key={r}
            onClick={() => handleRateChange(r)}
            className={`text-xs px-1.5 py-0.5 rounded cursor-pointer ${
              rate === r ? "bg-sepia text-paper" : "text-faded hover:text-ink"
            }`}
          >
            {r}x
          </button>
        ))}
      </div>
    </div>
  );
}
