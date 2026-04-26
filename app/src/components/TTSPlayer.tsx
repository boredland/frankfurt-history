import { useCallback, useEffect, useState } from "react";
import {
  getState,
  isSupported,
  pause,
  resume,
  speak,
  stop,
  subscribe,
} from "~/lib/tts";

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

  const handleToggle = useCallback(() => {
    if (state === "idle") {
      speak(text, lang, rate);
    } else if (state === "speaking") {
      pause();
    } else if (state === "paused") {
      resume();
    }
  }, [state, text, lang, rate]);

  const handleStop = useCallback(() => {
    stop();
  }, []);

  const handleRateChange = useCallback(
    (newRate: number) => {
      setRate(newRate);
      if (state === "speaking" || state === "paused") {
        speak(text, lang, newRate);
      }
    },
    [state, text, lang],
  );

  if (!isSupported() || !ready) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-t border-sepia-light bg-paper/80 backdrop-blur-sm">
      <button
        type="button"
        onClick={handleToggle}
        className="w-8 h-8 flex items-center justify-center rounded-full bg-sepia text-paper hover:bg-sepia/80 cursor-pointer"
        aria-label={
          state === "speaking"
            ? "Pause"
            : state === "paused"
              ? "Resume"
              : "Read aloud"
        }
        title={
          state === "speaking"
            ? "Pause"
            : state === "paused"
              ? "Resume"
              : "Read aloud"
        }
      >
        {state === "speaking" ? (
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="currentColor"
            role="img"
            aria-label="Pause"
          >
            <rect x="2" y="1" width="3.5" height="12" rx="1" />
            <rect x="8.5" y="1" width="3.5" height="12" rx="1" />
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

      {(state === "speaking" || state === "paused") && (
        <button
          type="button"
          onClick={handleStop}
          className="w-6 h-6 flex items-center justify-center rounded text-faded hover:text-ink cursor-pointer"
          aria-label="Stop"
          title="Stop"
        >
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
        </button>
      )}

      <span className="text-xs text-faded flex-1">
        {state === "speaking"
          ? "Reading..."
          : state === "paused"
            ? "Paused"
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
