import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Label, MasteryBar } from "../../components/ui";
import { checkpoint, concepts, notebook, student } from "../../lib/data";
import { describePacket } from "../../lib/grounding";
import * as script from "../../lib/tutorScript";
import type { ContextPacket, MarkTool, TutorState } from "../../lib/types";
import type { Stroke } from "./AnnotationLayer";
import CheckpointModal from "./CheckpointModal";
import Notebook, { type PulledNote } from "./Notebook";
import SessionControls from "./SessionControls";
import SpeechBubble from "./SpeechBubble";
import TextbookDrawer from "./TextbookDrawer";
import TutorAvatar from "./TutorAvatar";
import s from "./SessionScreen.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* What tonight covers. Fixed for the demo; the agent will emit this from the
   intensity the student picked. */
const PLAN = [
  "Find why 45° wins",
  "Say why",
  "Two throws, one spot",
];

export default function SessionScreen() {
  const nav = useNavigate();
  const hostRef = useRef<HTMLDivElement>(null);

  const concept = concepts.find((c) => c.id === notebook.conceptId)!;

  const [tool, setTool] = useState<MarkTool | null>(null);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [packet, setPacket] = useState<ContextPacket | null>(null);
  const [pulled, setPulled] = useState<PulledNote[]>([]);
  const [tutor, setTutor] = useState<TutorState>(script.opening);
  const [listening, setListening] = useState(false);
  const [bookOpen, setBookOpen] = useState(false);
  const [quizOpen, setQuizOpen] = useState(false);
  const [finding, setFinding] = useState(false);
  const [mastery, setMastery] = useState(concept.mastery);
  const [delta, setDelta] = useState<number | null>(null);

  /* Bumped whenever a NEW line should be spoken. The avatar drives its mouth
     from this rather than from the caption text, so a re-render with the same
     words never restarts her. */
  const [speakKey, setSpeakKey] = useState(0);

  /* Anchors the tutor is currently talking about. Two-way pointing: the
     student marks a term, and the tutor lights up the same term. */
  const [hot, setHot] = useState<Set<string>>(new Set());

  const clock = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

  const say = useCallback((next: TutorState) => {
    setTutor(next);
    setSpeakKey((k) => k + 1);
  }, []);

  const onPacket = useCallback((p: ContextPacket) => {
    setPacket(p);
    setHot(new Set(p.resolved.map((r) => r.anchorId)));
  }, []);

  const askAboutMark = useCallback(() => {
    if (!packet) return;
    say(script.replyToMark(packet));
    setTool(null);
  }, [packet, say]);

  const clearMarks = useCallback(() => {
    setStrokes([]);
    setPacket(null);
    setHot(new Set());
  }, []);

  const onExplored = useCallback(() => {
    if (finding || quizOpen) return;
    say(script.foundIt);
    // A beat, so the discovery lands before the checkpoint interrupts it.
    window.setTimeout(() => setQuizOpen(true), 2600);
  }, [finding, quizOpen, say]);

  const onCheckpointDone = useCallback((correct: boolean) => {
    setQuizOpen(false);
    if (!correct) { say(script.afterCheckpointWrong); return; }
    say(script.afterCheckpointRight);
    setFinding(true);
    setMastery(84);
    setDelta(16);
  }, [say]);

  const planIndex = finding ? 2 : quizOpen ? 1 : 0;

  return (
    <div className={s.screen}>
      <header className={s.bar}>
        <div className={s.left}>
          <Link to="/" className={s.brand} aria-label="Leave session">
            <span className={s.mark} />
            <span className={s.word}>Nityam</span>
          </Link>
          <span className={s.mode}>Revision <span aria-hidden="true">▾</span></span>
        </div>
        <div className={s.right}>
          <button
            className={cx(s.chipBtn, bookOpen && s.chipBtnOn)}
            onClick={() => setBookOpen((v) => !v)}
            aria-pressed={bookOpen}
          >
            ▦ View textbook
          </button>
          <span className={s.clock}>{clock}</span>
          <span className={s.who}>{student.firstName}</span>
          <span className={s.avatarChip}>{student.initial}</span>
        </div>
      </header>

      <div className={s.concept}>
        <span className={s.conceptName}>{concept.name}</span>
        <Label>{concept.id}</Label>
        <div className={s.conceptTrack}>
          <MasteryBar pct={mastery} hideName />
        </div>
        <span className={s.conceptPct}>{mastery}%</span>
        {delta !== null && <span className={s.delta}>+{delta} tonight</span>}

        <div className={s.plan}>
          {PLAN.map((step, i) => (
            <span
              key={step}
              className={cx(
                s.planStep,
                i < planIndex && s.planDone,
                i === planIndex && s.planNow,
              )}
            >
              <span className={s.planTick} aria-hidden="true">
                {i < planIndex ? "✓" : i === planIndex ? "●" : i + 1}
              </span>
              {step}
            </span>
          ))}
        </div>
      </div>

      <main className={s.stage}>
        <Notebook
          doc={notebook}
          hostRef={hostRef}
          tool={tool}
          strokes={strokes}
          onStroke={(st) => setStrokes((prev) => [...prev, st])}
          onPacket={onPacket}
          pulled={pulled}
          finding={finding}
          hot={hot}
          onExplored={onExplored}
        />
      </main>

      <SpeechBubble tutor={tutor} />
      <TutorAvatar mood={tutor.mood} caption={tutor.caption} speakKey={speakKey} />

      <SessionControls
        tool={tool}
        onTool={setTool}
        onClear={clearMarks}
        hasMarks={strokes.length > 0}
        packet={packet}
        packetSummary={packet ? describePacket(packet) : ""}
        onAskAboutMark={askAboutMark}
        onSend={(text) => say(script.replyToText(text))}
        listening={listening}
        onToggleMic={() => {
          const next = !listening;
          setListening(next);
          setTutor((cur) => ({ ...cur, mood: next ? "listening" : "idle" }));
        }}
        onEnd={() => nav("/summary")}
      />

      {bookOpen && (
        <TextbookDrawer
          onClose={() => setBookOpen(false)}
          onPull={(sel) => {
            const label = sel.figure ? "Fig. 4.10" : "NCERT XI · p.79";
            setPulled((prev) => [
              ...prev,
              {
                id: `pull_${sel.id}_${Date.now()}`,
                label,
                source: "You pulled this in",
                body: sel.text,
                quote: sel.figure ? undefined : sel.text,
                figure: sel.figure,
              },
            ]);
            say(script.replyToPull(label));
          }}
        />
      )}

      {quizOpen && <CheckpointModal checkpoint={checkpoint} onDone={onCheckpointDone} />}
    </div>
  );
}
