// Captures microphone frames on the audio thread and posts them to the main
// thread. Runs off the UI thread so a React re-render can never glitch audio.
class PCMRecorderProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      // Copy: the runtime recycles this buffer the moment we return.
      this.port.postMessage(new Float32Array(channel));
    }
    return true;
  }
}
registerProcessor("pcm-recorder-processor", PCMRecorderProcessor);
