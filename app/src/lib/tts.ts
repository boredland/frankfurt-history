type TTSState = "idle" | "speaking" | "paused" | "loading";
type TTSListener = (state: TTSState) => void;

let listeners: TTSListener[] = [];
let currentState: TTSState = "idle";
let currentAudio: HTMLAudioElement | null = null;
let piperAvailable: boolean | null = null;
let piperEngine: unknown = null;

function notify(state: TTSState) {
  currentState = state;
  for (const fn of listeners) fn(state);
}

const PIPER_VOICES: Record<string, string> = {
  de: "de_DE-thorsten-low",
  en: "en_US-hfc_female-medium",
};

function hasNeuralVoice(lang: string): boolean {
  const voices = speechSynthesis.getVoices();
  const prefix = lang === "de" ? "de" : "en";
  const neuralPatterns = /google|neural|microsoft|apple|siri|premium|enhanced/i;
  return voices.some(
    (v) => v.lang.startsWith(prefix) && neuralPatterns.test(v.name),
  );
}

function isOnWifi(): boolean {
  const conn = (navigator as unknown as Record<string, unknown>).connection as
    | { type?: string; effectiveType?: string }
    | undefined;
  if (!conn) return true;
  if (conn.type === "wifi" || conn.type === "ethernet") return true;
  if (conn.effectiveType === "4g") return true;
  return false;
}

function shouldUsePiper(lang: string): boolean {
  if (piperAvailable === false) return false;
  if (hasNeuralVoice(lang)) return false;
  if (!isOnWifi()) return false;
  return true;
}

interface PiperResponse {
  file: Blob;
}

async function speakWithPiper(text: string, lang: string): Promise<boolean> {
  try {
    const { PiperWebEngine } = await import("piper-tts-web");

    if (!piperEngine) {
      piperEngine = new PiperWebEngine();
    }

    const voiceId = PIPER_VOICES[lang] ?? PIPER_VOICES.en;
    const response = (await (
      piperEngine as InstanceType<typeof PiperWebEngine>
    ).generate(text, voiceId, 0)) as PiperResponse;

    piperAvailable = true;
    const wav = response.file;

    if (!wav || wav.size < 1000) {
      piperAvailable = false;
      return false;
    }

    const url = URL.createObjectURL(wav);
    const audio = new Audio(url);
    currentAudio = audio;

    return new Promise((resolve) => {
      audio.onended = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        notify("idle");
        resolve(true);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        resolve(false);
      };
      audio
        .play()
        .then(() => resolve(true))
        .catch(() => resolve(false));
    });
  } catch (e) {
    console.warn("[TTS] Piper failed, falling back to Web Speech:", e);
    piperAvailable = false;
    return false;
  }
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

async function speakWithWebSpeech(
  text: string,
  lang: string,
  rate: number,
): Promise<void> {
  const voices = await ensureVoices();
  const prefix = lang === "de" ? "de" : "en";
  const voice =
    voices.find((v) => v.lang.startsWith(prefix) && v.localService) ||
    voices.find((v) => v.lang.startsWith(prefix));

  const u = new SpeechSynthesisUtterance(text);
  if (voice) u.voice = voice;
  u.lang = lang === "de" ? "de-DE" : "en-US";
  u.rate = rate;
  u.onend = () => notify("idle");
  u.onerror = (e) => {
    if (e.error !== "canceled") notify("idle");
  };
  speechSynthesis.speak(u);
}

export async function speak(text: string, lang: string, rate: number = 1) {
  stop();
  if (!text.trim()) return;

  if (shouldUsePiper(lang)) {
    notify("loading");
    const ok = await speakWithPiper(text, lang);
    if (ok) {
      notify("speaking");
      return;
    }
  }

  notify("speaking");
  await speakWithWebSpeech(text, lang, rate);
}

export function pause() {
  if (currentAudio) {
    currentAudio.pause();
    notify("paused");
  } else if (currentState === "speaking") {
    speechSynthesis.pause();
    notify("paused");
  }
}

export function resume() {
  if (currentAudio) {
    currentAudio.play();
    notify("speaking");
  } else if (currentState === "paused") {
    speechSynthesis.resume();
    notify("speaking");
  }
}

export function stop() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
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
  return typeof window !== "undefined";
}
