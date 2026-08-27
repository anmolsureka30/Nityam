/* The browser half of the pipeline.
 *
 *   mic  -> AudioWorklet -> PCM16@16k -> WebSocket (binary)
 *   WebSocket (JSON) -> base64 -> PCM16@24k -> AudioWorklet -> speaker
 *
 * Framework-free on purpose: React sits on top of this in useLiveSession, and
 * audio must never wait on a render. Ported from
 * sub_modules_examples/adk/frontend/src/liveSession.js, which was written to be
 * lifted; the additions here are the typed client messages and `voiceStream`.
 *
 * Two AudioContexts, because input and output run at different sample rates
 * (16k in, 24k out) and a context has exactly one rate.
 */
import { base64ToArrayBuffer, floatToPCM16, rms } from "./audio";
import type { ClientMessage, ServerFrame } from "./protocol";

const INPUT_RATE = 16000;
const OUTPUT_RATE = 24000;

export interface SessionStatus {
  connected?: boolean;
  listening?: boolean;
  control?: unknown;
}

export class LiveSession {
  readonly userId: string;
  readonly sessionId: string;

  private onFrame: (frame: ServerFrame) => void;
  private onStatus: (status: SessionStatus) => void;

  private ws: WebSocket | null = null;
  private micContext: AudioContext | null = null;
  private micNode: AudioWorkletNode | null = null;
  private micStream: MediaStream | null = null;
  private playerContext: AudioContext | null = null;
  private playerNode: AudioWorkletNode | null = null;

  /** The model's own voice as a MediaStream, so the avatar rig can drive its
   *  mouth from real audio instead of guessing from syllables.
   *  lib/avatar/speech.js:attachAudio takes exactly this. */
  voiceStream: MediaStream | null = null;

  /** Mic level, for the meter. Read on a frame, not subscribed to. */
  level = 0;
  /** HER level, read the same way. Used to pace the captions: transcription
   *  arrives before any audio does (measured — the whole settled transcript can
   *  land before the first PCM frame), so nothing about the text can tell you
   *  how far through saying it she is. Her waveform can. */
  private voiceAnalyser: AnalyserNode | null = null;
  /* Typed as Float32Array<ArrayBuffer> rather than the default
     Float32Array<ArrayBufferLike>: getFloatTimeDomainData will not accept a
     view that might be backed by a SharedArrayBuffer. */
  private voiceBuffer: Float32Array<ArrayBuffer> | null = null;

  private rateChecked = false;

  constructor(opts: {
    userId: string;
    sessionId: string;
    onFrame?: (frame: ServerFrame) => void;
    onStatus?: (status: SessionStatus) => void;
  }) {
    this.userId = opts.userId;
    this.sessionId = opts.sessionId;
    this.onFrame = opts.onFrame ?? (() => {});
    this.onStatus = opts.onStatus ?? (() => {});
  }

  // ------------------------------------------------------------- socket

  async connect(): Promise<void> {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const url = `${scheme}://${location.host}/ws/${this.userId}/${this.sessionId}`;

    await new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(url);
      this.ws.binaryType = "arraybuffer";
      this.ws.onopen = () => {
        this.onStatus({ connected: true });
        resolve();
      };
      this.ws.onerror = () => reject(new Error(`cannot reach ${url}`));
      this.ws.onclose = () => this.onStatus({ connected: false });
      this.ws.onmessage = (message) => this.handleMessage(message.data);
    });

    await this.startPlayer();
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== "string") return;
    let payload: ServerFrame;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }

    if ("nityam" in payload && payload.nityam) {
      this.onFrame(payload);
      return;
    }

    // Audio is played here rather than in React: it must not wait on a render.
    for (const part of payload.content?.parts ?? []) {
      const inline = part.inlineData;
      if (inline?.mimeType?.startsWith("audio/pcm") && inline.data && this.playerNode) {
        this.checkRate(inline.mimeType);
        this.playerNode.port.postMessage(base64ToArrayBuffer(inline.data));
      }
    }

    // The student talked over the model: bin whatever is still queued, or she
    // keeps speaking her old sentence for another two seconds.
    if (payload.interrupted && this.playerNode) {
      this.playerNode.port.postMessage({ command: "endOfAudio" });
    }

    this.onFrame(payload);
  }

  /** AI Studio labels audio `audio/pcm;rate=24000`; Vertex sends a bare
   *  `audio/pcm` and leaves the rate implicit. So the player context is built
   *  at the documented 24kHz rather than from the header — but if a model ever
   *  says otherwise, playback would be pitch-shifted with no error anywhere,
   *  so say so once instead of silently sounding wrong. */
  private checkRate(mimeType: string): void {
    if (this.rateChecked) return;
    this.rateChecked = true;
    const declared = /rate=(\d+)/.exec(mimeType);
    if (declared && Number(declared[1]) !== OUTPUT_RATE) {
      console.warn(
        `[nityam] model audio is ${declared[1]}Hz but playback is ${OUTPUT_RATE}Hz — ` +
          "voice will be pitch-shifted. Update OUTPUT_RATE in lib/live/session.ts.",
      );
    }
  }

  send(message: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  sendText(text: string): void {
    this.send({ type: "text", text });
  }

  greet(): void {
    this.send({ type: "greet" });
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // ------------------------------------------------------------- output

  private async startPlayer(): Promise<void> {
    this.playerContext = new AudioContext({ sampleRate: OUTPUT_RATE });
    await this.playerContext.audioWorklet.addModule("/pcm-player-processor.js");
    this.playerNode = new AudioWorkletNode(this.playerContext, "pcm-player-processor");

    // Tap the voice on its way to the speakers. A MediaStreamDestination gives
    // a MediaStream, which is what the avatar's attachAudio accepts — an
    // AnalyserNode would have meant reimplementing its viseme mapping here.
    const tap = this.playerContext.createMediaStreamDestination();
    this.playerNode.connect(tap);
    this.voiceStream = tap.stream;

    /* A second tap, for measuring rather than for the avatar. The comment above
       is still true — the rig wants a MediaStream — but pacing captions needs a
       number, and an analyser is the cheap way to get one without decoding the
       PCM twice. */
    this.voiceAnalyser = this.playerContext.createAnalyser();
    this.voiceAnalyser.fftSize = 512;
    this.voiceBuffer = new Float32Array(
      new ArrayBuffer(this.voiceAnalyser.fftSize * 4),
    );
    this.playerNode.connect(this.voiceAnalyser);

    this.playerNode.connect(this.playerContext.destination);
  }

  /** Is she making sound right now, and how much?
   *
   *  Sampled on demand rather than pushed, exactly like `level`: the caller
   *  polls at whatever rate it needs and no render depends on the intermediate
   *  values. */
  get voiceLevel(): number {
    const analyser = this.voiceAnalyser;
    const buffer = this.voiceBuffer;
    if (!analyser || !buffer) return 0;
    analyser.getFloatTimeDomainData(buffer);
    return rms(buffer);
  }

  /** Resume any context the autoplay policy left suspended.
   *
   *  An AudioContext constructed outside a user gesture starts `suspended`, and
   *  a suspended context plays nothing and reports no error. The player context
   *  is created when the socket opens — on mount — so this has to be called
   *  from the first real click, or the tutor is inaudible for the whole session.
   *  Safe to call repeatedly. */
  async resumeAudio(): Promise<void> {
    for (const ctx of [this.playerContext, this.micContext]) {
      if (ctx && ctx.state === "suspended") {
        try {
          await ctx.resume();
        } catch {
          /* Nothing to do about it, and it must not stop the mic opening. */
        }
      }
    }
  }

  // ------------------------------------------------------------- input

  async startMic(): Promise<void> {
    if (this.micNode) return;

    // Ask the browser for 16kHz directly instead of resampling ourselves.
    this.micContext = new AudioContext({ sampleRate: INPUT_RATE });
    await this.micContext.audioWorklet.addModule("/pcm-recorder-processor.js");

    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true, // or the model hears itself and interrupts itself
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const source = this.micContext.createMediaStreamSource(this.micStream);
    this.micNode = new AudioWorkletNode(this.micContext, "pcm-recorder-processor");
    source.connect(this.micNode);

    this.micNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
      this.level = rms(event.data);
      if (this.ws?.readyState === WebSocket.OPEN) {
        // Binary frame, not base64 JSON: ~33% less bandwidth and no encode
        // step on a buffer that arrives 80 times a second.
        this.ws.send(floatToPCM16(event.data).buffer as ArrayBuffer);
      }
    };

    this.onStatus({ listening: true });
  }

  stopMic(): void {
    this.micNode?.port.close();
    this.micNode?.disconnect();
    this.micStream?.getTracks().forEach((track) => track.stop());
    void this.micContext?.close();
    this.micNode = null;
    this.micStream = null;
    this.micContext = null;
    this.level = 0;
    this.onStatus({ listening: false });
  }

  disconnect(): void {
    this.stopMic();
    void this.playerContext?.close();
    this.playerContext = null;
    this.playerNode = null;
    this.voiceStream = null;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close();
    this.ws = null;
  }
}
