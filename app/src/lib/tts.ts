type TTSState = "idle" | "speaking" | "paused";
type TTSListener = (state: TTSState, sentenceIndex: number) => void;

const SENTENCE_SPLIT = /(?<=[.!?。])\s+|(?<=\n)\s*/;

let currentUtterances: SpeechSynthesisUtterance[] = [];
let currentIndex = 0;
let listeners: TTSListener[] = [];
let currentState: TTSState = "idle";

function notify(state: TTSState, index: number) {
  currentState = state;
  for (const fn of listeners) fn(state, index);
}

function pickVoice(lang: string): SpeechSynthesisVoice | undefined {
  const voices = speechSynthesis.getVoices();
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

export function speak(text: string, lang: string, rate: number = 1) {
  stop();
  const sentences = splitSentences(text);
  if (sentences.length === 0) return;

  const voice = pickVoice(lang);
  currentUtterances = sentences.map((sentence, i) => {
    const u = new SpeechSynthesisUtterance(sentence);
    if (voice) u.voice = voice;
    u.lang = lang === "de" ? "de-DE" : "en-US";
    u.rate = rate;
    u.onstart = () => notify("speaking", i);
    u.onend = () => {
      if (i === sentences.length - 1) {
        notify("idle", i);
      }
    };
    u.onerror = () => notify("idle", i);
    return u;
  });

  currentIndex = 0;
  for (const u of currentUtterances) {
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
  currentUtterances = [];
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
