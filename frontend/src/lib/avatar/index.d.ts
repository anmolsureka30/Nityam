/** Types for the ported avatar rig. The runtime is plain JS, copied from the
 *  sub-module unchanged; this only describes the handle mountAvatar returns. */

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export interface AvatarHandle {
  setState(state: AvatarState): boolean;
  state(): AvatarState;
  setEmotion(name: string): boolean;
  /** A beat that reverts on its own — "good job", a flash of surprise. */
  react(name: string, seconds?: number): boolean;
  emotion(): string;
  emotions(): string[];
  /** Speak with no audio: the mouth is driven by the syllables of the text. */
  say(text: string, opts?: { rate?: number; thenListen?: boolean; onEnd?: () => void }): number;
  attachAudio(source: HTMLAudioElement | MediaStream): boolean;
  stopSpeaking(): void;
  isSpeaking(): boolean;
  tick(now?: number): unknown;
  destroy(): void;
}

export interface AvatarNamespace {
  mountAvatar(container: HTMLElement, opts?: { size?: number }): AvatarHandle;
  DESIGN: { w: number; h: number };
  emotionNames(): string[];
}

declare const NS: AvatarNamespace;
export default NS;
