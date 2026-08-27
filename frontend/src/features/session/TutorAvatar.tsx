import { useEffect, useRef } from "react";
import NS from "../../lib/avatar";
import type { AvatarHandle } from "../../lib/avatar";
import type { TutorMood } from "../../lib/types";
import s from "./TutorAvatar.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* The tutor, floating over the page.
 *
 * This is a thin wrapper: all the drawing, springing and lip sync live in the
 * ported rig. The wrapper's only job is to keep the rig's imperative handle in
 * step with React state, and to make sure the RAF loop is torn down.
 *
 * The rig maps our four moods onto its own conversational states, and adds an
 * emotion on top for the moment the student gets something right. */
const MOOD_STATE: Record<TutorMood, "idle" | "listening" | "thinking" | "speaking"> = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  pleased: "speaking",
};

export default function TutorAvatar({
  mood, caption, speakKey, voice,
}: {
  mood: TutorMood;
  /** What she is saying. Drives the mouth via the rig's syllable engine. */
  caption: string;
  /** Changes whenever a NEW line should be spoken, so repeating the same
   *  caption does not restart the mouth and a re-render never does either. */
  speakKey: number;
  /** The model's actual voice. When present the rig reads the waveform, which
   *  is real lip sync; the syllable engine is only the fallback for mock mode,
   *  where there is no model audio to read. */
  voice?: MediaStream | null;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const avatarRef = useRef<AvatarHandle | null>(null);
  const spokenRef = useRef(-1);

  // Mount once. The rig owns its own animation loop from here.
  useEffect(() => {
    if (!hostRef.current) return;
    const handle = NS.mountAvatar(hostRef.current);
    avatarRef.current = handle;
    return () => {
      handle.destroy();
      avatarRef.current = null;
    };
  }, []);

  // Conversational state follows the session's mood.
  useEffect(() => {
    const a = avatarRef.current;
    if (!a) return;
    if (mood === "pleased") a.react("delighted", 2.4);
    else a.setState(MOOD_STATE[mood]);
  }, [mood]);

  // Real audio when there is any: the rig's attachAudio reads the waveform and
  // drives the mouth off actual energy, which no syllable estimate matches.
  const audioRef = useRef<MediaStream | null>(null);
  useEffect(() => {
    const a = avatarRef.current;
    if (!a || !voice || audioRef.current === voice) return;
    audioRef.current = voice;
    a.attachAudio(voice);
  }, [voice]);

  // Fallback for mock mode, where nothing is actually played: drive the mouth
  // from the syllables of the caption. Skipped once real audio is attached, or
  // the two would fight over the same mouth parameters.
  useEffect(() => {
    const a = avatarRef.current;
    if (!a || audioRef.current) return;
    if (speakKey === spokenRef.current) return;
    spokenRef.current = speakKey;
    if (caption) a.say(caption);
  }, [speakKey, caption]);

  const live = mood === "listening";
  const speaking = mood === "speaking" || mood === "pleased";

  return (
    <div className={s.dock}>
      <div className={s.stand}>
        <div className={s.canvasHost} ref={hostRef} />
        <span
          className={cx(
            s.aura,
            (live || speaking) && s.auraOn,
            live && s.auraListening,
            speaking && s.auraSpeaking,
          )}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
