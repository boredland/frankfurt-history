declare module "piper-tts-web" {
  export class PiperWebEngine {
    generate(
      text: string,
      voiceId: string,
      speakerId: number,
    ): Promise<{ file: Blob }>;
  }
}
