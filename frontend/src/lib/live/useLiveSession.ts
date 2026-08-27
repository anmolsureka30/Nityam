/* One hook: the tutor's voice, her captions, and everything she writes.
 *
 * The transcription handling is the fiddly part and it is not guesswork — it
 * reproduces what the adk sub-module's own useLiveSession.js had to learn
 * against the real API:
 *
 *   * Every sentence arrives TWICE. First as `partial: true` fragments, then
 *     as a `partial: false` frame repeating the whole thing. Appending both
 *     prints everything twice, so a settled frame REPLACES the fragments it
 *     was assembled from.
 *   * A multi-sentence turn settles once per sentence, so sentences accumulate
 *     into one caption per turn rather than one bubble per sentence.
 *   * `interrupted` means the student talked over her: stop, and drop what was
 *     queued.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { BoardAction, BoardState } from "../notebookReducer";
import { boardReducer, emptyBoard } from "../notebookReducer";
import type { TutorMood } from "../types";
import { LiveSession } from "./session";
import type { ClientMessage, ScreenState, ServerFrame } from "./protocol";

export interface LiveTutor {
  /** The model's voice, once the player is running. State rather than a ref
   *  read: a ref assigned after connect() resolves is invisible to the memo
   *  below, so consumers saw null forever and the avatar never lip-synced. */
  voice: MediaStream | null;
  connected: boolean;
  mode: string;
  error: string | null;
  listening: boolean;
  /** The mic is live from the moment the session opens, so the control is a
   *  MUTE, not a "start talking". Muted means she cannot hear you. */
  muted: boolean;
  /** True while she has delegated and is waiting on the reasoning layer. That
   *  wait is 15-20s of real time, so the UI has to say so or the page reads as
   *  dead and the student concludes they were not heard. */
  thinking: boolean;
  /** The holding line she gave when she delegated — what she is working on,
   *  in her words. Empty when she is not thinking. */
  bridge: string;
  mood: TutorMood;
  /** What she is saying, as it arrives. */
  caption: string;
  /** Bumped when a NEW line starts, so the avatar's mouth restarts only then. */
  speakKey: number;
  /** The last thing the student was heard to say. Rendering this is the only
   *  unambiguous proof, from the student's side, that the mic is working. */
  heard: string;
  /** Mic input level, 0-1, sampled off the audio thread. Zero while she is not
   *  listening. The other half of that proof: it moves when they talk. */
  level: number;
  board: BoardState;
  dispatch: (action: BoardAction) => void;
  toggleMute: () => void;
  send: (message: ClientMessage) => void;
  sendScreen: (state: ScreenState) => void;
}

const SCREEN_THROTTLE_MS = 700;

export function useLiveSession(
  userId: string,
  sessionId: string,
  /** What this session is for. Sent before the greeting so her opening line is
   *  about the thing they clicked, not a blank "what shall we do". */
  plan: ClientMessage & { type: "start" },
  enabled = true,
): LiveTutor {
  const [board, dispatch] = useReducer(boardReducer, undefined, () => emptyBoard());
  const [connected, setConnected] = useState(false);
  const [mode, setMode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [caption, setCaption] = useState("");
  const [heard, setHeard] = useState("");
  const [speakKey, setSpeakKey] = useState(0);
  const [voice, setVoice] = useState<MediaStream | null>(null);
  const [thinking, setThinking] = useState(false);
  const [bridge, setBridge] = useState("");
  const [muted, setMuted] = useState(false);
  /* Read inside the connect callback, which closes over the first render.
     Assigned in an effect rather than during render: a render can be discarded,
     and the callback fires a tick later at the earliest, so this is always in
     time. */
  const mutedRef = useRef(muted);
  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);
  const [level, setLevel] = useState(0);

  const sessionRef = useRef<LiveSession | null>(null);
  /* Confirmed sentences this turn, and the fragment still being assembled.
     Kept in a ref, not state: they update several times a second and no render
     should depend on the intermediate values. */
  const turn = useRef({ settled: "", fragment: "" });
  const screenSentAt = useRef(0);
  const screenPending = useRef<ScreenState | null>(null);

  const publish = useCallback(() => {
    const { settled, fragment } = turn.current;
    setCaption((settled + fragment).trim());
  }, []);

  const newTurn = useCallback(() => {
    turn.current = { settled: "", fragment: "" };
    setSpeakKey((k) => k + 1);
  }, []);

  const onFrame = useCallback(
    (frame: ServerFrame) => {
      if ("nityam" in frame && frame.nityam) {
        const control = frame.nityam;
        if (control.kind === "session") {
          setMode(control.mode);
          dispatch({ type: "reset", wire: control.board });
        } else if (control.kind === "canvas_patch") {
          dispatch({ type: "patch", patch: control.patch });
        } else if (control.kind === "error") {
          setError(control.message);
        }
        return;
      }

      const event = frame;

      if (event.inputTranscription?.text) {
        setHeard(event.inputTranscription.text);
      }

      const out = event.outputTranscription?.text;
      if (out) {
        // A new turn begins the moment she speaks after being silent.
        if (!speaking) {
          newTurn();
          setSpeaking(true);
        }
        if (event.partial) {
          turn.current.fragment = out;
        } else {
          // Settled: this frame repeats the whole sentence the fragments were
          // building, so replace rather than append, then start the next one.
          turn.current.settled = (turn.current.settled + " " + out).trim() + " ";
          turn.current.fragment = "";
        }
        publish();
      }

      /* The reasoning layer is reached by a tool call, so its start and end are
         visible right here in the stream — no extra protocol needed.

         The call also carries her holding line. `bridge` is a required argument
         of ask_tutor precisely so it arrives here: the Live model would either
         speak a bridge OR make the call, never both, so the line it wanted to
         say is now part of the call and lands in the bubble the instant the
         reasoning starts. Ten seconds of thinking with "achha, ek second" on
         screen is a tutor working; ten seconds blank is a tutor who did not
         hear you. */
      for (const part of event.content?.parts ?? []) {
        if (part.functionCall?.name === "ask_tutor") {
          setThinking(true);
          const line = (part.functionCall.args as { bridge?: string } | undefined)
            ?.bridge?.trim();
          if (line) {
            setBridge(line);
            newTurn();
            turn.current.settled = line + " ";
            publish();
          }
        }
        if (part.functionResponse?.name === "ask_tutor") {
          setThinking(false);
          setBridge("");
        }
      }

      if (event.interrupted) {
        setSpeaking(false);
        turn.current.fragment = "";
        publish();
      }
      if (event.turnComplete) {
        setSpeaking(false);
        turn.current.fragment = "";
        publish();
      }
      if (event.interrupted || event.turnComplete) {
        // Belt and braces: a dropped functionResponse must not leave the UI
        // claiming she is still thinking forever.
        if (event.turnComplete) {
          setThinking(false);
          setBridge("");
        }
      }
    },
    [newTurn, publish, speaking],
  );

  /* Keep the frame handler current without reconnecting on every render: the
     socket is built once, and reading it through a ref means a stale closure
     can never silently swallow patches. Assigned in an effect rather than
     during render — a render can be thrown away, and the socket must not be
     left pointing at a handler from a render that never committed. */
  const handlerRef = useRef(onFrame);
  useEffect(() => {
    handlerRef.current = onFrame;
  }, [onFrame]);

  /* StrictMode double-invokes effects in dev: mount, clean up, mount again. For
     a media app that means two WebSockets on the same session id and two sets
     of AudioContexts. The backend accepts the second connection and can still
     send_content on it — which is why the greeting still arrived — but the
     realtime audio channel belongs to a Live session that the overlapping
     teardown has already broken, so the tutor talks and never hears anything.
     That is the whole "it is not hearing me" bug.
     (sub_modules_examples/adk avoids it by not using StrictMode at all; this
     keeps StrictMode and makes the connect safe under it instead.)

     Deferring the connect by a tick is what fixes it: StrictMode's cleanup runs
     synchronously before the second mount, so the first attempt is cancelled
     before a socket is ever opened, and exactly one connection survives. */
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let session: LiveSession | null = null;

    const timer = window.setTimeout(() => {
      if (cancelled) return;
      session = open();
    }, 60);

    function open() {
      const live = new LiveSession({
        userId,
        sessionId,
        onFrame: (frame) => handlerRef.current(frame),
        onStatus: (status) => {
          if (status.connected !== undefined) setConnected(status.connected);
          if (status.listening !== undefined) setListening(status.listening);
        },
      });

      live
        .connect()
        .then(() => {
          if (cancelled) {
            live.disconnect();
            return;
          }
          sessionRef.current = live;
          setVoice(live.voiceStream);
          // Nothing makes the Live model take the first turn on its own — it
          // waits for input. Ask it to open the lesson.
          live.send(plan);
          live.greet();
          /* Live by default: this is a voice tutor, and a student who has to
             find and press a button before being heard will conclude it is
             broken — which is exactly what happened. getUserMedia prompts for
             permission on its own; it does not need a gesture. */
          if (!mutedRef.current) {
            live.startMic().catch((e: Error) => setError(`microphone: ${e.message}`));
          }
        })
        .catch((e: Error) => {
          if (!cancelled) setError(e.message);
        });

      return live;
    }

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      session?.disconnect();
      sessionRef.current = null;
      setVoice(null);
    };
    // `plan` is deliberately not a dependency: it is fixed for the life of a
    // session, and including it would reconnect on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, userId, sessionId]);

  // Sweep expired point_at highlights, so "look at this" does not leave the
  // page lit up for the rest of the session.
  useEffect(() => {
    if (!Object.keys(board.hot).length) return;
    const timer = window.setInterval(
      () => dispatch({ type: "expire_hot", now: Date.now() }),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [board.hot]);

  /* An AudioContext built outside a user gesture starts suspended, and a
     suspended context plays nothing and reports no error. Now that nothing
     requires a click to begin, the first gesture ANYWHERE has to be the one
     that unblocks audio — otherwise she is silently inaudible for a student who
     never happens to click. */
  useEffect(() => {
    const wake = () => void sessionRef.current?.resumeAudio();
    for (const type of ["pointerdown", "keydown"] as const) {
      window.addEventListener(type, wake, { once: false, passive: true });
    }
    return () => {
      for (const type of ["pointerdown", "keydown"] as const) {
        window.removeEventListener(type, wake);
      }
    };
  }, []);

  /* Polled rather than pushed: the level updates ~80 times a second on the
     audio thread, and re-rendering React at that rate to animate one ring is
     not a trade worth making. 10 fps is plenty for a meter. */
  useEffect(() => {
    if (!listening) return;
    const timer = window.setInterval(() => {
      setLevel(sessionRef.current?.level ?? 0);
    }, 100);
    return () => window.clearInterval(timer);
  }, [listening]);

  const send = useCallback((message: ClientMessage) => {
    sessionRef.current?.send(message);
  }, []);

  /* Screen snapshots are throttled rather than debounced: dragging a slider
     fires continuously, and the tutor wants the CURRENT value promptly, not
     the final value eventually. The trailing send catches the last position. */
  const sendScreen = useCallback((state: ScreenState) => {
    screenPending.current = state;
    const since = Date.now() - screenSentAt.current;
    if (since >= SCREEN_THROTTLE_MS) {
      screenSentAt.current = Date.now();
      sessionRef.current?.send({ type: "screen", state });
      screenPending.current = null;
      return;
    }
    window.setTimeout(() => {
      if (!screenPending.current) return;
      screenSentAt.current = Date.now();
      sessionRef.current?.send({ type: "screen", state: screenPending.current });
      screenPending.current = null;
    }, SCREEN_THROTTLE_MS - since);
  }, []);

  const toggleMute = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    void session.resumeAudio();
    if (listening) {
      session.stopMic();
      setMuted(true);
    } else {
      setMuted(false);
      session.startMic().catch((e: Error) => setError(`microphone: ${e.message}`));
    }
  }, [listening]);

  /* Order matters: thinking outranks listening, because "she is working on it"
     is what the student needs to know during the 15-20s wait, and the mic being
     open is already shown by the meter. */
  const mood: TutorMood = speaking
    ? "speaking"
    : thinking
      ? "thinking"
      : listening
        ? "listening"
        : "idle";

  return useMemo(
    () => ({
      voice,
      connected,
      mode,
      error,
      listening,
      muted,
      thinking,
      bridge,
      mood,
      caption,
      speakKey,
      heard,
      // Derived, not stored: a muted mic has no level, and zeroing it from an
      // effect would be a second render for a value already known here.
      level: listening ? level : 0,
      board,
      dispatch,
      toggleMute,
      send,
      sendScreen,
    }),
    [voice, connected, mode, error, listening, muted, thinking, bridge, mood, caption,
     speakKey, heard, level, board, toggleMute, send, sendScreen],
  );
}
