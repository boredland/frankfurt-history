type TTSState = "idle" | "speaking" | "paused";
type TTSListener = (state: TTSState, sentenceIndex: number) => void;

const SENTENCE_SPLIT = /(?<=[.!?。])\s+|(?<=\n)\s*/;

let currentIndex = 0;
let listeners: TTSListener[] = [];
let currentState: TTSState = "idle";

function notify(state: TTSState, index: number) {
  currentState = state;
  for (const fn of listeners) fn(state, index);
}

function ensureVoices(): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) {
      resolve(voices);
      return;
    }
    speechSynthesis.onvoiceschanged = () => {
      resolve(speechSynthesis.getVoices());
    };
    setTimeout(() => resolve(speechSynthesis.getVoices()), 1000);
  });
}

function pickVoice(
  voices: SpeechSynthesisVoice[],
  lang: string,
): SpeechSynthesisVoice | undefined {
  const prefix = lang === "de" ? "de" : "en";
  return (
    voices.find((v) => v.lang.startsWith(prefix) && v.localService) ||
    voices.find((v) => v.lang.startsWith(prefix))
  );
}

export function splitSentences(text: string): string[] {
  return text
    .split(SENTENCE_SPLIT)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export async function speak(text: string, lang: string, rate: number = 1) {
  stop();
  const sentences = splitSentences(text);
  if (sentences.length === 0) return;

  const voices = await ensureVoices();
  const voice = pickVoice(voices, lang);

  for (let i = 0; i < sentences.length; i++) {
    const sentence = sentences[i];
    if (!sentence) continue;
    const u = new SpeechSynthesisUtterance(sentence);
    if (voice) u.voice = voice;
    u.lang = lang === "de" ? "de-DE" : "en-US";
    u.rate = rate;
    u.onstart = () => {
      currentIndex = i;
      notify("speaking", i);
    };
    u.onend = () => {
      if (i === sentences.length - 1) {
        notify("idle", i);
      }
    };
    u.onerror = (e) => {
      if (e.error !== "canceled") {
        notify("idle", i);
      }
    };
    speechSynthesis.speak(u);
  }
  notify("speaking", 0);
}

export function pause() {
  if (currentState === "speaking") {
    speechSynthesis.pause();
    notify("paused", currentIndex);
  }
}

export function resume() {
  if (currentState === "paused") {
    speechSynthesis.resume();
    notify("speaking", currentIndex);
  }
}

export function stop() {
  speechSynthesis.cancel();
  currentIndex = 0;
  notify("idle", 0);
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
