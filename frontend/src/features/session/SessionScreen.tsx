import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SessionBriefing from "./SessionBriefing";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { UserChip } from "../../components/Shell";
import { Label, MasteryBar } from "../../components/ui";
import { useAuth } from "../../lib/auth/AuthContext";
import { concepts, intensities, student } from "../../lib/data";
import { useLiveSession } from "../../lib/live/useLiveSession";
import { SPECIALIST_COPY } from "../../lib/live/specialists";
import type { ContextPacket, MarkTool } from "../../lib/types";
import type { Stroke } from "./AnnotationLayer";
import CheckpointModal from "./CheckpointModal";
import MicToggle from "./MicToggle";
import Notebook from "./Notebook";
import SessionControls from "./SessionControls";
import SpeechBubble from "./SpeechBubble";
import TextbookDrawer, { type Clip } from "./TextbookDrawer";
import PointerStick from "./PointerStick";
import TextbookPeek from "./TextbookPeek";
import { useTextbookPlace } from "../../lib/textbookPlace";
import TutorAvatar from "./TutorAvatar";
import s from "./SessionScreen.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* What tonight covers.
   STUB: hardcoded. The agent will emit this from the intensity the student
   picked plus the class recap. See backend/INTEGRATION.md. */
const PLAN = ["Find why 45° wins", "Say why", "Two throws, one spot"];

export default function SessionScreen() {
  const nav = useNavigate();
  const hostRef = useRef<HTMLDivElement>(null);

  // ProtectedRoute guarantees a signed-in user by the time this screen mounts.
  const { user } = useAuth();
  const userId = user!.uid;

  /* One live session per mount. The id must be stable across renders, or every
     render opens a new socket and a new board. A lazy useState initialiser, not
     useMemo: a memo is a performance hint React is free to discard and
     StrictMode double-invokes it, so neither guarantees identity — and identity
     is the whole requirement here. */
  const [sessionId] = useState(() => `s_${crypto.randomUUID().slice(0, 8)}`);
  /* What this session is for, from the URL — so "Revise today's class",
     "Ask a doubt" and "Exam readiness" are genuinely different sessions
     rather than three buttons that open the same blank conversation. */
  const [params] = useSearchParams();
  const mode = (["revision", "doubt", "exam"] as const).find(
    (m) => m === params.get("mode"),
  ) ?? "doubt";
  const plannedConcept = concepts.find((c) => c.id === params.get("concept"));
  const intensity = params.get("intensity") ?? undefined;
  const plan = useMemo(
    () => ({
      type: "start" as const,
      mode,
      concept: plannedConcept?.id,
      conceptName: plannedConcept?.name,
      intensity,
      minutes: intensities.find((i) => i.id === intensity)?.minutes,
    }),
    [mode, plannedConcept?.id, plannedConcept?.name, intensity],
  );

  const tutor = useLiveSession(userId, sessionId, plan, () => user!.getIdToken());
  const { board, dispatch, send, sendScreen } = tutor;

  const [tool, setTool] = useState<MarkTool | null>(null);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [bookOpen, setBookOpen] = useState(false);
  const [place, goToPlace] = useTextbookPlace();

  /* The book follows the tutor — ONCE PER PAGE SHE SHOWS, not on every board
     change.
     
     The first version re-ran on any `board.doc` identity change and re-applied
     the newest textbook block it found. So the moment she had put one page on
     the board, every subsequent patch — another block, a strike, a point_at —
     yanked the student's book back to her page while they were reading their
     own. From the student's side that is the drawer refusing to stay where they
     put it, which reads as the PDF being broken. Keyed on the block id, so a
     given page is followed exactly once. */
  const followed = useRef<string | null>(null);
  useEffect(() => {
    const blocks = board.doc.pages.flatMap((pg) => pg.blocks);
    for (let i = blocks.length - 1; i >= 0; i--) {
      const block = blocks[i] as { id?: string; kind?: string; pdf?: string; page?: number };
      if (block.kind === "pulled" && block.pdf && block.page) {
        if (followed.current !== block.id) {
          followed.current = block.id ?? null;
          goToPlace({ chapter: block.pdf, page: block.page });
        }
        return;
      }
    }
  }, [board.doc, goToPlace]);

  /* Mastery is still local: the tutor writes it at session close, which is
     after this screen is gone. STUB — see backend/INTEGRATION.md. */
  const concept =
    plannedConcept ?? concepts.find((c) => c.id === board.doc.conceptId) ?? concepts[0];
  const [mastery, setMastery] = useState(concept.mastery);
  const [delta, setDelta] = useState<number | null>(null);

  const clock = new Date().toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });

  /* The overlay lifts on her FIRST word and never returns. A plain
     `!tutor.connected` would flash it back up on every reconnect mid-lesson,
     and a plain `mood !== "speaking"` would put it back every time she
     pauses for breath. */
  const [heardHer, setHeardHer] = useState(false);
  useEffect(() => {
    if (tutor.mood === "speaking") setHeardHer(true);
  }, [tutor.mood]);

  const checkpoint = board.quizQueue[0] ?? null;

  /* Resolved locally so the highlight is instant, then sent upstream the moment
     the stroke ends — not on a button press.
     
     Marking something IS the question's subject: a student highlights a term
     and says "what does this mean", and expects the two to arrive together.
     Requiring "Ask about this" first meant the spoken question landed with no
     referent and she answered about the topic in general. The backend takes it
     as context for whatever they say next rather than as a turn of its own. */
  const onPacket = useCallback(
    (p: ContextPacket) => {
      send({ type: "gesture", packet: p });
    },
    [send],
  );


  const clearMarks = useCallback(() => {
    setStrokes([]);
  }, []);

  /* The tutor cannot see the page, so tell it: which blocks are on screen,
     where the simulation is set, whether a checkpoint is open. read_screen
     serves this back to the model. */
  const reportScreen = useCallback(
    (extra: { simulation?: Record<string, number> } = {}) => {
      const host = hostRef.current;
      const visible: string[] = [];
      if (host) {
        const view = host.getBoundingClientRect();
        host.querySelectorAll<HTMLElement>("[data-block]").forEach((el) => {
          const r = el.getBoundingClientRect();
          if (r.bottom > view.top && r.top < view.bottom) {
            const id = el.dataset.block;
            if (id && !visible.includes(id)) visible.push(id);
          }
        });
      }
      sendScreen({
        visibleBlockIds: visible,
        quiz: checkpoint
          ? { checkpointId: checkpoint.id, open: true, answered: false }
          : { open: false },
        ...extra,
      });
    },
    [checkpoint, sendScreen],
  );

  // Report on scroll and whenever the board changes under the student.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    reportScreen();
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => reportScreen());
    };
    host.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      host.removeEventListener("scroll", onScroll);
    };
  }, [reportScreen, board.revision]);

  /* Follow the writing.
   *
   * She writes several blocks over ~20 seconds and they land below the fold, so
   * without this the student watches a still page while the answer accumulates
   * off screen.
   *
   * "Unless they have scrolled up" is the important half: yanking the page down
   * while someone is re-reading an earlier line is worse than not following at
   * all. Once they scroll back to the bottom, following resumes — the same
   * contract as a chat log. */
  const following = useRef(true);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onScroll = () => {
      const fromBottom = host.scrollHeight - host.scrollTop - host.clientHeight;
      // The notebook reserves avatar-height of bottom padding, so "at the
      // bottom" is generous rather than exact.
      following.current = fromBottom < 340;
    };
    host.addEventListener("scroll", onScroll, { passive: true });
    return () => host.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (board.revision === 0 || !following.current) return;
    const host = hostRef.current;
    if (!host) return;
    const blocks = host.querySelectorAll<HTMLElement>("[data-block]");
    const last = blocks[blocks.length - 1];
    if (!last) return;
    /* Scroll so the newest block sits just above her head rather than behind
       it — the page reserves that space, so aim at it explicitly instead of
       scrolling to the true bottom and landing under the avatar. */
    const avatar = parseInt(
      getComputedStyle(host).getPropertyValue("--avatar-h") || "288", 10,
    );
    const target =
      last.offsetTop + last.offsetHeight - host.clientHeight + avatar + 28;
    host.scrollTo({
      top: Math.max(0, Math.min(target, host.scrollHeight - host.clientHeight)),
      behavior: "smooth",
    });
  }, [board.revision]);

  // The tutor asked to bring an earlier block back into view.
  useEffect(() => {
    if (!board.scrollTo) return;
    const el = hostRef.current?.querySelector<HTMLElement>(
      `[data-block="${board.scrollTo}"]`,
    );
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    dispatch({ type: "scrolled" });
  }, [board.scrollTo, dispatch]);

  // Fires the instant an option is picked, so the tutor's spoken reaction
  // doesn't wait on the student also clicking "Show me why"/"Keep going" —
  // see CheckpointModal's own doc comment for why that delay mattered.
  const onCheckpointAnswer = useCallback(
    (correct: boolean, optionId: string, optionText: string) => {
      if (!checkpoint) return;
      send({
        type: "quiz_answer",
        checkpointId: checkpoint.id,
        optionId,
        optionText,
        correct,
      });
    },
    [checkpoint, send],
  );

  // Fires when the student is done reading (any rebuttal, if wrong) and
  // continues — closes the modal and updates mastery. Deliberately not
  // where the backend gets told the answer; see onCheckpointAnswer above.
  const onCheckpointDone = useCallback(
    (correct: boolean) => {
      dispatch({ type: "quiz_done" });
      if (correct) {
        setMastery((m) => Math.min(100, m + 8));
        setDelta((d) => (d ?? 0) + 8);
      }
    },
    [dispatch],
  );

  const planIndex = Math.min(
    PLAN.length - 1,
    board.doc.pages.reduce((n, p) => n + p.blocks.length, 0) > 6 ? 2 : checkpoint ? 1 : 0,
  );

  return (
    <div className={s.screen}>
      <header className={s.bar}>
        <div className={s.left}>
          <Link to="/" className={s.brand} aria-label="Leave session">
            <span className={s.mark} />
            <span className={s.word}>Nityam</span>
          </Link>
          <span className={s.mode}>
            {mode === "revision" ? "Revision" : mode === "exam" ? "Exam prep" : "Doubt"}
          </span>
          {tutor.mode === "mock" && <Label tone="warn">Mock mode</Label>}
          {!tutor.connected && <Label tone="warn">Reconnecting…</Label>}
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
          <UserChip />
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
              <span className={s.planDot}>
                {i < planIndex ? "✓" : i === planIndex ? "●" : i + 1}
              </span>
              {step}
            </span>
          ))}
        </div>

        {tutor.specialist === "quiz" && (
          <span className={s.quizPrep}>
            {SPECIALIST_COPY.quiz.glyph} {SPECIALIST_COPY.quiz.verb}
          </span>
        )}
      </div>

      <main
        className={cx(
          s.stage,
          tutor.specialist === "board" && s.stageBoardActive,
          tutor.specialist === "artifact" && s.stageArtifactActive,
        )}
      >
        <Notebook
          doc={board.doc}
          hostRef={hostRef}
          tool={tool}
          strokes={strokes}
          onStroke={(st) => setStrokes((prev) => [...prev, st])}
          onPacket={onPacket}
          hot={board.hot}
          waiting={board.revision === 0}
          interest="cricket"
          onEvidence={(event) =>
            send({
              type: "artifact_evidence",
              artifactId: event.artifactId,
              event: event.event,
              detail: event.detail,
            })
          }
          onSimulation={(sim) => reportScreen({ simulation: sim })}
        />
      </main>

      <SpeechBubble
        caption={tutor.caption}
        error={tutor.error}
        agent={tutor.mood === "speaking" ? "tutor" : "tutor"}
      />
      <MicToggle
        muted={tutor.muted}
        listening={tutor.listening}
        level={tutor.level}
        onToggle={tutor.toggleMute}
      />
      {/* The book, open on the desk beside her. Top of her rail, above the
          speech bubble's slot, so the column reads: your book, what she is
          saying, her. */}
      <TextbookPeek
        place={place}
        onOpen={() => setBookOpen(true)}
        active={tutor.specialist === "textbook"}
      />

      {/* She points at what she is talking about. Driven entirely by the
          existing point_at signal — no new protocol, no new tool. */}
      <PointerStick
        hot={board.hot}
        speaking={tutor.mood === "speaking"}
        revision={board.revision}
      />

      <TutorAvatar
        mood={tutor.mood}
        caption={tutor.caption}
        speakKey={tutor.speakKey}
        voice={tutor.voice}
      />

      <SessionControls
        tool={tool}
        onTool={setTool}
        onClear={clearMarks}
        hasMarks={strokes.length > 0}
        onSend={(text) => send({ type: "text", text })}
        thinking={tutor.thinking}
        specialist={tutor.specialist}
        onEnd={() => nav("/summary")}
      />

      {bookOpen && (
        <TextbookDrawer
          initialChapter={place.chapter}
          initialPage={place.page}
          onPlace={goToPlace}
          onClose={() => setBookOpen(false)}
          onClip={(clips: Clip[]) => {
            /* One message for the whole selection: a figure and the paragraph
               that explains it are one thought, and two separate interruptions
               would have her react twice to what the student did once. */
            send({
              type: "textbook_clip",
              clips: clips.map((c) => ({
                image: c.image,
                text: c.text,
                page: c.page,
              })),
              chapter: clips[0].chapter.file,
              chapterTitle: `Ch ${clips[0].chapter.number} · ${clips[0].chapter.title}`,
            });
            setBookOpen(false);
          }}
        />
      )}

      <SessionBriefing
        studentId={userId}
        topic={plannedConcept?.name ?? ""}
        mode={mode}
        open={!heardHer}
      />

      {checkpoint && (
        <CheckpointModal
          checkpoint={checkpoint}
          onAnswer={onCheckpointAnswer}
          onDone={onCheckpointDone}
        />
      )}
    </div>
  );
}
