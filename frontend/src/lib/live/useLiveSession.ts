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
import type { Specialist } from "./specialists";
import { resolveSpecialist } from "./specialists";
import { LiveSession } from "./session";
import { spokenMs, toChunks } from "./chunks";
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
  /** Which specialist she has delegated to, while `thinking` is true. `null`
   *  when she isn't thinking, or when an `ask_*` tool this app doesn't
   *  recognize was reached — see specialists.ts's resolveSpecialist(). */
  specialist: Specialist | null;
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
  /** Mints a fresh Firebase ID token right before each connect. Cheap even
   *  when nothing needs refreshing — the SDK only hits the network if the
   *  cached token is near expiry. */
  getToken: () => Promise<string>,
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
  const [specialist, setSpecialist] = useState<Specialist | null>(null);
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
  /* What she is saying, as bubble-sized pieces, and how far through them she
     is. Refs rather than state: the clock ticks ten times a second and no
     render should depend on the intermediate values — only `caption` does, and
     it is set explicitly.
     
     The bubble used to hold the whole settled transcript, which for a
     three-sentence reply was a paragraph. See lib/live/chunks.ts. */
  const turn = useRef({
    chunks: [] as string[],
    /** Index of the chunk currently in the bubble. */
    at: 0,
    /** Milliseconds of her ACTUALLY MAKING SOUND spent on the current chunk.
     *  Not wall clock: transcription arrives before any audio does, and a plain
     *  timer would race ahead through the pauses while the brain works and
     *  flash the last chunk past before she said it. */
    voiced: 0,
    /** Has this turn finished being generated?
     *
     *  Several settled transcriptions inside ONE turn are one continuous
     *  speech and should queue up behind each other. Across turns they are
     *  not: if she is still draining her greeting when the next answer
     *  arrives, appending puts the new answer behind text she is no longer
     *  saying. Seen for real — the bubble was three sentences behind. */
    closed: false,
  });
  const screenSentAt = useRef(0);
  const screenPending = useRef<ScreenState | null>(null);

  const publish = useCallback(() => {
    const { chunks, at } = turn.current;
    /* Falling back to the LAST chunk matters: `at` is allowed to run one past
       the end so that "has this drained?" can be answered, and without the
       fallback the bubble would blank the instant she finished the final
       sentence — which she has only just said and the student is still
       reading. */
    setCaption(chunks[at] ?? chunks[chunks.length - 1] ?? "");
  }, []);

  const newTurn = useCallback(() => {
    turn.current = { chunks: [], at: 0, voiced: 0, closed: false };
    setSpeakKey((k) => k + 1);
  }, []);

  /** Queue what she just said. Replaces a drained queue, appends to a live one,
   *  so several transcriptions inside one turn read as one continuous speech. */
  const say = useCallback((text: string) => {
    const next = toChunks(text);
    if (!next.length) return;
    const t = turn.current;
    const drained = t.at >= t.chunks.length;
    if (drained || t.closed) {
      turn.current = { chunks: next, at: 0, voiced: 0, closed: false };
    } else {
      t.chunks = [...t.chunks, ...next];
    }
    publish();
  }, [publish]);

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
        if (!speaking) setSpeaking(true);
        /* Partials are deliberately ignored. They arrive BEFORE any audio and
           within a few hundred milliseconds of each other, so showing them
           would build up a sentence and then visibly jump back to chunk one
           when the settled version landed. Only settled text is queued. */
        if (event.partial === false) say(out);
      }

      /* A specialist is reached by a tool call, so its start and end are
         visible right here in the stream — no extra protocol needed.

         Matched on the `ask_` prefix rather than by name. The voice layer
         delegates to four of them today (ask_board, ask_artifact, ask_quiz,
         ask_textbook) and a fifth would otherwise be invisible here until
         someone remembered to edit this line — which is exactly how this
         broke once already, when the single `ask_tutor` these checks used to
         name was split into four and neither branch matched anything again.

         Every delegate tool takes a required `bridge` argument precisely so
         it arrives here: the Live model would either speak a bridge OR make
         the call, never both, so the line it wanted to say is now part of the
         call and lands in the bubble the instant the delegation starts. Ten
         seconds of thinking with "achha, ek second" on screen is a tutor
         working; ten seconds blank is a tutor who did not hear you. */
      for (const part of event.content?.parts ?? []) {
        if (part.functionCall?.name?.startsWith("ask_")) {
          setThinking(true);
          setSpecialist(resolveSpecialist(part.functionCall.name));
          const line = (part.functionCall.args as { bridge?: string } | undefined)
            ?.bridge?.trim();
          if (line) {
            setBridge(line);
            newTurn();
            say(line);
          }
        }
        /* Belt and braces. These tools are scheduled WHEN_IDLE, and ADK does
           not yield a functionResponse event into this stream for those — so
           in practice it is the turnComplete branch below that clears the
           thinking state, when her own current utterance finishes. */
        if (part.functionResponse?.name?.startsWith("ask_")) {
          setThinking(false);
          setBridge("");
          setSpecialist(null);
        }
      }

      if (event.interrupted) {
        // Cut off: whatever was still queued is never going to be said.
        setSpeaking(false);
        newTurn();
        setCaption("");
      }
      /* turnComplete does NOT clear the queue. It arrives while the audio is
         still playing — she has finished being generated, not finished
         speaking — and clearing here wiped the last two chunks off the bubble
         mid-sentence. The queue drains on its own. */
      if (event.turnComplete) {
        setSpeaking(false);
        // Marks the boundary without clearing: the queue keeps draining, but
        // the NEXT thing she says replaces what is left rather than queueing
        // behind it.
        turn.current.closed = true;
      }
      if (event.interrupted || event.turnComplete) {
        // Belt and braces: a dropped functionResponse must not leave the UI
        // claiming she is still thinking forever.
        if (event.turnComplete) {
          setThinking(false);
          setBridge("");
          setSpecialist(null);
        }
      }
    },
    [newTurn, publish, say, speaking],
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
        getToken,
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
    // `plan` and `getToken` are deliberately not dependencies: both are fixed
    // for the life of a session (a caller passing a fresh `getToken` closure
    // every render must not reconnect the socket every render either), and
    // both are only ever read once, inside `open()`.
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

  /* Advance the bubble at the pace she is actually speaking.
  
     Ticks always — not only while `speaking` — because turnComplete arrives
     before the audio finishes and the last chunks are drained after it. The
     clock only moves when her waveform is above the noise floor, so a pause in
     her speech is a pause in the captions and the estimate cannot drift. */
  const TICK = 100;
  const VOICED = 0.008;
  useEffect(() => {
    const timer = window.setInterval(() => {
      const t = turn.current;
      if (t.at >= t.chunks.length) return;
      const loud = (sessionRef.current?.voiceLevel ?? 0) > VOICED;
      if (!loud) return;
      t.voiced += TICK;
      if (t.voiced >= spokenMs(t.chunks[t.at])) {
        t.at += 1;
        t.voiced = 0;
        // Publishes past the end too: `publish` falls back to the last chunk,
        // so the bubble holds her closing line instead of going blank.
        publish();
      }
    }, TICK);
    return () => window.clearInterval(timer);
  }, [publish]);

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
      specialist,
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
    [voice, connected, mode, error, listening, muted, thinking, bridge, specialist, mood,
     caption, speakKey, heard, level, board, toggleMute, send, sendScreen],
  );
}
