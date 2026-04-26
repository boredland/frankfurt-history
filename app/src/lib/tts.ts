type TTSState = "idle" | "speaking" | "paused";
type TTSListener = (state: TTSState) => void;

let listeners: TTSListener[] = [];
let currentState: TTSState = "idle";

function notify(state: TTSState) {
  currentState = state;
  for (const fn of listeners) fn(state);
}

function ensureVoices(): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) {
      resolve(voices);
      return;
    }
    speechSynthesis.onvoiceschanged = () =>
      resolve(speechSynthesis.getVoices());
    setTimeout(() => resolve(speechSynthesis.getVoices()), 1000);
  });
}

function pickVoice(
  voices: SpeechSynthesisVoice[],
  lang: string,
): SpeechSynthesisVoice | undefined {
  const prefix = lang === "de" ? "de" : "en";
  const neural = /google|neural|microsoft|apple|siri|premium|enhanced/i;
  return (
    voices.find(
      (v) => v.lang.startsWith(prefix) && neural.test(v.name) && v.localService,
    ) ||
    voices.find((v) => v.lang.startsWith(prefix) && neural.test(v.name)) ||
    voices.find((v) => v.lang.startsWith(prefix) && v.localService) ||
    voices.find((v) => v.lang.startsWith(prefix))
  );
}

export async function speak(text: string, lang: string, rate: number = 1) {
  stop();
  if (!text.trim()) return;

  const voices = await ensureVoices();
  const voice = pickVoice(voices, lang);

  const u = new SpeechSynthesisUtterance(text);
  if (voice) u.voice = voice;
  u.lang = lang === "de" ? "de-DE" : "en-US";
  u.rate = rate;
  u.onstart = () => notify("speaking");
  u.onend = () => notify("idle");
  u.onerror = (e) => {
    if (e.error !== "canceled") notify("idle");
  };
  speechSynthesis.speak(u);
  notify("speaking");
}

export function pause() {
  if (currentState === "speaking") {
    speechSynthesis.pause();
    notify("paused");
  }
}

export function resume() {
  if (currentState === "paused") {
    speechSynthesis.resume();
    notify("speaking");
  }
}

export function stop() {
  speechSynthesis.cancel();
  notify("idle");
}

export function getState(): TTSState {
  return currentState;
}

export function subscribe(fn: TTSListener): () => void {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

export function isSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}
