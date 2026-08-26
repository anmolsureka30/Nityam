import { useEffect, useRef, useState } from "react";
import { useLiveSession } from "./useLiveSession.js";
import "./styles.css";

const AGENT_LABEL = { tutor: "Tutor", quiz_master: "Quiz master" };

export default function App() {
  const s = useLiveSession();

  return (
    <div className="app">
      <Header mode={s.mode} connected={s.connected} />

      <main className="stage">
        <section className="talk">
          <AgentBadge agent={s.agent} voice={s.voice} speaking={s.speaking} />
          <Orb
            connected={s.connected}
            listening={s.listening}
            speaking={s.speaking}
            level={s.level}
            onConnect={s.connect}
            onToggleMic={s.toggleMic}
          />
          <Hint connected={s.connected} listening={s.listening} mode={s.mode} />
          {s.error && <p className="error">{s.error}</p>}
        </section>

        <aside className="rail">
          <Transcript
            turns={s.turns}
            drafts={s.drafts}
            speaking={s.speaking}
            agent={s.agent}
          />
          <Composer onSend={s.sendText} disabled={!s.connected} />
        </aside>
      </main>

      <ToolStrip formula={s.formula} score={s.score} />
    </div>
  );
}

function Header({ mode, connected }) {
  return (
    <header className="header">
      <div className="brand">
        <span className="mark">नि</span>
        <div>
          <h1>Nityam</h1>
          <p>Voice tutor · Google ADK</p>
        </div>
      </div>
      <div className="badges">
        {mode && (
          <span className={`badge ${mode.mode === "mock" ? "warn" : "live"}`}>
            {mode.mode === "mock" ? "mock mode" : mode.mode}
          </span>
        )}
        {mode?.model && <span className="badge muted">{mode.model}</span>}
        <span className={`dot ${connected ? "on" : "off"}`} />
      </div>
    </header>
  );
}

function AgentBadge({ agent, voice, speaking }) {
  return (
    <div className={`agent ${speaking ? "speaking" : ""}`}>
      <span className="who">{AGENT_LABEL[agent] ?? agent}</span>
      <span className="voice">voice · {voice}</span>
    </div>
  );
}

function Orb({ connected, listening, speaking, level, onConnect, onToggleMic }) {
  // Two rings: the outer one tracks the mic, so you can see that audio really
  // is leaving the browser before you trust anything else in the pipeline.
  const ring = 1 + Math.min(level * 6, 0.45);

  if (!connected) {
    return (
      <button className="orb idle" onClick={onConnect}>
        <span className="orb-label">Start session</span>
      </button>
    );
  }

  return (
    <button
      className={`orb ${listening ? "hot" : ""} ${speaking ? "talking" : ""}`}
      onClick={onToggleMic}
    >
      <span className="orb-ring" style={{ transform: `scale(${ring})` }} />
      <span className="orb-label">{listening ? "Listening" : "Tap to talk"}</span>
    </button>
  );
}

function Hint({ connected, listening, mode }) {
  if (!connected) return <p className="hint">Click to connect, then talk.</p>;
  if (!listening)
    return <p className="hint">Tap the orb to open your microphone.</p>;
  return (
    <p className="hint">
      Speak normally — pause and it answers. Interrupt any time.
      {mode?.mode === "mock" && " Try saying “quiz me” to hear the handoff."}
    </p>
  );
}

function Transcript({ turns, drafts, speaking, agent }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, drafts]);

  return (
    <div className="transcript">
      <h2>Transcript</h2>
      {turns.length === 0 && !drafts.user && !drafts.model && (
        <p className="empty">
          Captions appear here. The response modality is audio-only, so this
          text comes from the Live API's own transcription of both voices.
        </p>
      )}
      <ul>
        {turns.map((turn) => (
          <li key={turn.id} className={`turn ${turn.who}`}>
            {turn.who === "system" ? (
              <span className="system">⇢ {turn.text}</span>
            ) : (
              <>
                <span className="turn-who">
                  {turn.who === "user"
                    ? turn.typed ? "You (typed)" : "You"
                    : AGENT_LABEL[turn.author] ?? turn.author}
                </span>
                <span className="turn-text">{turn.text}</span>
              </>
            )}
          </li>
        ))}
        {drafts.user && (
          <li className="turn user live">
            <span className="turn-who">You</span>
            <span className="turn-text">{drafts.user}</span>
          </li>
        )}
        {drafts.model && (
          <li className={`turn model live ${speaking ? "speaking" : ""}`}>
            <span className="turn-who">{AGENT_LABEL[agent] ?? agent} · speaking</span>
            <span className="turn-text">{drafts.model}</span>
          </li>
        )}
      </ul>
      <div ref={endRef} />
    </div>
  );
}

function Composer({ onSend, disabled }) {
  const [text, setText] = useState("");
  const submit = (event) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
  };
  return (
    <form className="composer" onSubmit={submit}>
      <input
        value={text}
        disabled={disabled}
        placeholder={disabled ? "Not connected" : "…or type instead"}
        onChange={(event) => setText(event.target.value)}
      />
      <button type="submit" disabled={disabled || !text.trim()}>
        Send
      </button>
    </form>
  );
}

function ToolStrip({ formula, score }) {
  if (!formula && !score) {
    return (
      <footer className="tools empty-tools">
        Tool results land here — the tutor calls <code>show_formula</code>, the
        quiz master calls <code>record_answer</code>.
      </footer>
    );
  }
  return (
    <footer className="tools">
      {formula && (
        <div className="card">
          <span className="card-label">{formula.label}</span>
          <span className="card-value formula">{formula.formula}</span>
        </div>
      )}
      {score && (
        <div className="card">
          <span className="card-label">Quiz score</span>
          <span className="card-value">
            {score.correct} / {score.asked}
          </span>
        </div>
      )}
    </footer>
  );
}
