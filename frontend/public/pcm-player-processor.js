// Plays PCM16 chunks arriving out of a WebSocket, at 24kHz.
//
// A ring buffer is not optional here: chunks arrive on network time and are
// consumed on audio time, and any gap between the two is an audible click.
// Underflow outputs silence rather than stalling; overflow drops the oldest
// samples, which only happens under extreme delay.
class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 24000 * 120; // 2 minutes of headroom
    this.buffer = new Float32Array(this.bufferSize);
    this.writeIndex = 0;
    this.readIndex = 0;

    this.port.onmessage = (event) => {
      // Interruption: drop everything queued so stale speech never plays over
      // the student. Jumping read to write is the whole operation.
      if (event.data && event.data.command === "endOfAudio") {
        this.readIndex = this.writeIndex;
        return;
      }
      this.enqueue(new Int16Array(event.data));
    };
  }

  enqueue(samples) {
    for (let i = 0; i < samples.length; i++) {
      this.buffer[this.writeIndex] = samples[i] / 32768;
      this.writeIndex = (this.writeIndex + 1) % this.bufferSize;
      if (this.writeIndex === this.readIndex) {
        this.readIndex = (this.readIndex + 1) % this.bufferSize;
      }
    }
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    const frames = output[0].length;
    for (let frame = 0; frame < frames; frame++) {
      const sample = this.buffer[this.readIndex];
      for (let ch = 0; ch < output.length; ch++) output[ch][frame] = sample;
      if (this.readIndex !== this.writeIndex) {
        this.readIndex = (this.readIndex + 1) % this.bufferSize;
      }
    }
    return true;
  }
}
registerProcessor("pcm-player-processor", PCMPlayerProcessor);
