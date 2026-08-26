import { useCallback, useEffect, useRef, useState } from "react";
import { LiveSession } from "./liveSession.js";

const VOICES = { tutor: "Leda", quiz_master: "Puck" };

// Turns the raw ADK event stream into the handful of things a UI actually
// renders: a transcript, who is speaking, and whatever the tools returned.
export function useLiveSession() {
  const sessionRef = useRef(null);

  const [connected, setConnected] = useState(false);
  const [listening, setListening] = useState(false);
  const [mode, setMode] = useState(null);
  const [error, setError] = useState(null);
  const [speaking, setSpeaking] = useState(false);
  const [agent, setAgent] = useState("tutor");
  const [turns, setTurns] = useState([]);
  const [formula, setFormula] = useState(null);
  const [score, setScore] = useState(null);
  const [level, setLevel] = useState(0);

  // Transcription arrives in two layers, and conflating them is the classic
  // bug here. `partial` events spell a sentence out as it is spoken; then one
  // consolidated event repeats that entire sentence with partial=false. So a
  // turn is tracked as confirmed text plus a trailing in-flight fragment, and
  // the caption shown is the two concatenated.
  const draft = useRef({
    user: { settled: "", partial: "" },
    model: { settled: "", partial: "" },
    author: "tutor",
  });
  const [drafts, setDrafts] = useState({ user: "", model: "" });

  const show = useCallback((who) => {
    const { settled, partial } = draft.current[who];
    const text = `${settled} ${partial}`.trim();
    setDrafts((prev) => (prev[who] === text ? prev : { ...prev, [who]: text }));
  }, []);

  // A fragment of a sentence still being spoken.
  const grow = useCallback(
    (who, fragment) => {
      draft.current[who].partial += fragment;
      show(who);
    },
    [show]
  );

  // A finished sentence. It REPLACES the fragments rather than extending them,
  // and joins the turn's confirmed text so one turn stays one bubble.
  const settle = useCallback(
    (who, text) => {
      const state = draft.current[who];
      state.settled = `${state.settled} ${text}`.trim();
      state.partial = "";
      show(who);
    },
    [show]
  );

  // End of turn: the confirmed text becomes a permanent bubble.
  const flush = useCallback(
    (who) => {
      const state = draft.current[who];
      const text = `${state.settled} ${state.partial}`.trim();
      state.settled = "";
      state.partial = "";
      show(who);
      if (!text) return;
      const author = who === "user" ? "user" : draft.current.author;
      setTurns((prev) => [...prev, { who, author, text, id: `${Date.now()}-${who}` }]);
    },
    [show]
  );

  const handleEvent = useCallback(
    (event) => {
      if (event.author && event.author !== "user" && event.author !== draft.current.author) {
        // A transfer happened. Close whatever the previous agent was mid-way
        // through saying, so the two agents never share one bubble.
        flush("model");
        draft.current.author = event.author;
        setAgent(event.author);
      }

      if (event.inputTranscription?.text) {
        // The model starting to answer means the student's turn is over.
        flush("model");
        if (event.partial) grow("user", event.inputTranscription.text);
        else settle("user", event.inputTranscription.text);
      }

      if (event.outputTranscription?.text) {
        flush("user");
        if (event.partial) grow("model", event.outputTranscription.text);
        else settle("model", event.outputTranscription.text);
        setSpeaking(true);
      }

      for (const part of event.content?.parts ?? []) {
        if (part.inlineData?.mimeType?.startsWith("audio/pcm")) setSpeaking(true);

        const call = part.functionCall;
        if (call?.name === "transfer_to_agent") {
          setTurns((prev) => [
            ...prev,
            {
              who: "system",
              text: `handing off to ${call.args?.agent_name ?? "another agent"}`,
              id: `${Date.now()}-transfer`,
            },
          ]);
        }

        const response = part.functionResponse;
        if (response?.name === "show_formula" && response.response?.formula) {
          setFormula({
            label: response.response.label,
            formula: response.response.formula,
          });
        }
        if (response?.name === "record_answer") {
          setScore({
            asked: response.response?.asked ?? 0,
            correct: response.response?.correct ?? 0,
          });
        }
      }

      if (event.interrupted) {
        flush("model");
        setSpeaking(false);
      }
      if (event.turnComplete) {
        flush("user");
        flush("model");
        setSpeaking(false);
      }
    },
    [flush, grow, settle]
  );

  const handleStatus = useCallback((status) => {
    if ("connected" in status) setConnected(status.connected);
    if ("listening" in status) setListening(status.listening);
    if (status.control?.kind === "session") setMode(status.control);
    if (status.control?.kind === "error") setError(status.control.message);
  }, []);

  const connect = useCallback(async () => {
    if (sessionRef.current) return;
    setError(null);
    const session = new LiveSession({
      userId: "demo-student",
      sessionId: `s-${Date.now()}`,
      onEvent: handleEvent,
      onStatus: handleStatus,
    });
    sessionRef.current = session;
    try {
      await session.connect();
      session.greet();
    } catch (err) {
      sessionRef.current = null;
      setError(err.message);
    }
  }, [handleEvent, handleStatus]);

  const toggleMic = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    if (session.micNode) {
      session.stopMic();
    } else {
      try {
        await session.startMic();
      } catch (err) {
        setError(`microphone: ${err.message}`);
      }
    }
  }, []);

  const sendText = useCallback((text) => {
    sessionRef.current?.sendText(text);
    setTurns((prev) => [
      ...prev,
      { who: "user", text, id: `${Date.now()}-typed`, typed: true },
    ]);
  }, []);

  // Poll the mic level off the React clock. A 20Hz meter does not need a
  // re-render per audio frame.
  useEffect(() => {
    if (!listening) {
      setLevel(0);
      return;
    }
    const id = setInterval(() => setLevel(sessionRef.current?.level ?? 0), 50);
    return () => clearInterval(id);
  }, [listening]);

  useEffect(() => () => sessionRef.current?.disconnect(), []);

  // Returned as a plain object rather than a useMemo: memoising it here saves
  // nothing (the consumer re-renders on these values changing anyway) and a
  // dependency list that falls out of date silently drops updates, which is a
  // bug you debug by staring at a UI that is simply not moving.
  return {
    connect,
    toggleMic,
    sendText,
    connected,
    listening,
    speaking,
    mode,
    error,
    agent,
    voice: VOICES[agent] ?? "—",
    turns,
    drafts,
    formula,
    score,
    level,
  };
}
