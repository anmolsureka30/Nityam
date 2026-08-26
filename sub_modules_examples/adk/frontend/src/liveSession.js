// The browser half of the pipeline. Framework-free on purpose: this is the
// piece to lift into the real product, where it will sit behind a React hook
// exactly as it does here.
//
//   mic  -> AudioWorklet -> PCM16@16k -> WebSocket (binary)
//   WebSocket (JSON) -> base64 -> PCM16@24k -> AudioWorklet -> speaker
//
// Two AudioContexts, because input and output run at different sample rates
// (16k in, 24k out) and a context has exactly one rate.

import { base64ToArrayBuffer, floatToPCM16, rms } from "./audio.js";

const INPUT_RATE = 16000;
const OUTPUT_RATE = 24000;

export class LiveSession {
  constructor({ userId, sessionId, onEvent, onStatus }) {
    this.userId = userId;
    this.sessionId = sessionId;
    this.onEvent = onEvent || (() => {});
    this.onStatus = onStatus || (() => {});

    this.ws = null;
    this.micContext = null;
    this.micNode = null;
    this.micStream = null;
    this.playerContext = null;
    this.playerNode = null;
    this.analyser = null; // exposed for lip-sync
    this.level = 0;
    this.rateChecked = false;
  }

  // ------------------------------------------------------------- socket

  async connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const url = `${scheme}://${location.host}/ws/${this.userId}/${this.sessionId}`;

    await new Promise((resolve, reject) => {
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

  handleMessage(raw) {
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }

    // Our own control messages are namespaced so they can never be mistaken
    // for an ADK event.
    if (payload.nityam) {
      this.onStatus({ control: payload.nityam });
      return;
    }

    // Audio is played here rather than in React: it must not wait on a render.
    for (const part of payload.content?.parts ?? []) {
      const inline = part.inlineData;
      if (inline?.mimeType?.startsWith("audio/pcm") && this.playerNode) {
        this.checkRate(inline.mimeType);
        this.playerNode.port.postMessage(base64ToArrayBuffer(inline.data));
      }
    }

    // The student talked over the model: bin whatever is still queued, or she
    // keeps speaking her old sentence for another two seconds.
    if (payload.interrupted && this.playerNode) {
      this.playerNode.port.postMessage({ command: "endOfAudio" });
    }

    this.onEvent(payload);
  }

  // AI Studio labels audio `audio/pcm;rate=24000`; Vertex sends a bare
  // `audio/pcm` and leaves the rate implicit. So the player context is built
  // at the documented 24kHz rather than from the header — but if a model ever
  // says otherwise, playback would be pitch-shifted with no error anywhere, so
  // say so once instead of silently sounding wrong.
  checkRate(mimeType) {
    if (this.rateChecked) return;
    this.rateChecked = true;
    const declared = /rate=(\d+)/.exec(mimeType);
    if (declared && Number(declared[1]) !== OUTPUT_RATE) {
      console.warn(
        `[nityam] model audio is ${declared[1]}Hz but playback is ${OUTPUT_RATE}Hz — ` +
          "voice will be pitch-shifted. Update OUTPUT_RATE in liveSession.js."
      );
    }
  }

  sendText(text) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "text", text }));
    }
  }

  greet() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "greet" }));
    }
  }

  // ------------------------------------------------------------- output

  async startPlayer() {
    this.playerContext = new AudioContext({ sampleRate: OUTPUT_RATE });
    await this.playerContext.audioWorklet.addModule("/pcm-player-processor.js");
    this.playerNode = new AudioWorkletNode(this.playerContext, "pcm-player-processor");

    // Sits between the player and the speakers so anything that needs the
    // model's voice — an avatar's mouth, a waveform — can read it. This is the
    // hook the avatar sub-module's attachAudio() was written against.
    this.analyser = this.playerContext.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.6;

    this.playerNode.connect(this.analyser);
    this.analyser.connect(this.playerContext.destination);
  }

  // ------------------------------------------------------------- input

  async startMic() {
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

    this.micNode.port.onmessage = (event) => {
      this.level = rms(event.data);
      if (this.ws?.readyState === WebSocket.OPEN) {
        // Binary frame, not base64 JSON: ~33% less bandwidth and no encode
        // step on a buffer that arrives 80 times a second.
        this.ws.send(floatToPCM16(event.data).buffer);
      }
    };

    this.onStatus({ listening: true });
  }

  stopMic() {
    this.micNode?.port.close();
    this.micNode?.disconnect();
    this.micStream?.getTracks().forEach((track) => track.stop());
    this.micContext?.close();
    this.micNode = null;
    this.micStream = null;
    this.micContext = null;
    this.level = 0;
    this.onStatus({ listening: false });
  }

  disconnect() {
    this.stopMic();
    this.playerContext?.close();
    this.playerContext = null;
    this.playerNode = null;
    this.analyser = null;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close();
    this.ws = null;
  }
}
