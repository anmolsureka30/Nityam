import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { Label, Panel } from "../../components/ui";
import { conceptName } from "../../lib/conceptCatalog";
import { useAuth } from "../../lib/auth/AuthContext";
import {
  MASTERY,
  fetchSessionRecap,
  movedForward,
  type MemoryChange,
  type SessionRecap,
} from "../../lib/memory";
import s from "./SessionRecapScreen.module.css";

/* One session, and what it did to what the tutor knows.
 *
 * THE ARGUMENT THIS SCREEN MAKES. "Dynamic memory" is not believable from
 * prose. It is believable when you can see `Misunderstood → Getting there`
 * against a named concept, with the session that moved it directly above.
 * So the changes come first, at full size, and everything else — the whole
 * before/after tables, the operations, the transcript — sits underneath as
 * the evidence for them.
 *
 * The rejected operations are shown deliberately. A memory layer where every
 * proposed write succeeds is indistinguishable from one with no rules at all;
 * "the model asked to close this doubt and the rules refused" is the more
 * convincing half of the demonstration. */

function label(mastery: string | null): string {
  // Null means the tutor had no view on this concept at all — a first
  // encounter. It rendered as an em dash, so a genuinely new concept read as
  // "— -> Known", which looks like missing data rather than like something
  // being taught for the first time.
  if (!mastery) return "Not seen yet";
  return MASTERY[mastery]?.label ?? mastery;
}

function ChangeRow({ change }: { change: MemoryChange }) {
  const forward = change.kind === "mastery"
    ? movedForward(change.from, change.to)
    : change.to === "resolved";
  return (
    <li className={s.change}>
      <div className={s.changeConcept}>
        {conceptName(change.concept_id) || change.concept_id}
        {change.kind === "doubt" && <span className={s.kindTag}>doubt</span>}
      </div>
      <div className={s.changeArrow}>
        <span className={s.from}>{label(change.from)}</span>
        <span className={s.arrow} aria-hidden="true">→</span>
        <span className={forward ? s.toBetter : s.toWorse}>
          {change.kind === "doubt" && change.to === "removed"
            ? "cleared"
            : label(change.to)}
        </span>
      </div>
      {change.doubt && <p className={s.changeNote}>{change.doubt}</p>}
    </li>
  );
}

export default function SessionRecapScreen() {
  const { user } = useAuth();
  const { sessionId = "" } = useParams();
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "error"; error: string }
    | { status: "ready"; recap: SessionRecap }
  >({ status: "loading" });

  useEffect(() => {
    if (!user?.uid || !sessionId) return;
    let live = true;
    fetchSessionRecap(user.uid, sessionId)
      .then((r) => live && setState({ status: "ready", recap: r }))
      .catch((e) => live && setState({ status: "error", error: (e as Error).message }));
    return () => {
      live = false;
    };
  }, [user?.uid, sessionId]);

  const back = { to: "/sessions", label: "All sessions" };

  if (state.status !== "ready") {
    return (
      <Shell back={back}>
        <section className="ruled">
          <div className="margin" />
          <div className="body">
            <Panel>
              <p className={s.muted}>
                {state.status === "loading"
                  ? "Loading this session…"
                  : `Couldn't load this session (${state.error}).`}
              </p>
            </Panel>
          </div>
        </section>
      </Shell>
    );
  }

  const r = state.recap;
  if (!r.found) {
    return (
      <Shell back={back}>
        <section className="ruled">
          <div className="margin" />
          <div className="body">
            <Panel><p className={s.muted}>No such session.</p></Panel>
          </div>
        </section>
      </Shell>
    );
  }

  const concepts = Array.from(
    new Set([...Object.keys(r.before.mastery), ...Object.keys(r.after.mastery)]),
  ).sort(
    (a, b) =>
      (MASTERY[r.after.mastery[a]?.mastery ?? ""]?.rank ?? 9)
      - (MASTERY[r.after.mastery[b]?.mastery ?? ""]?.rank ?? 9),
  );

  return (
    <Shell back={back}>
      <section className="ruled">
        <div className="margin">
          <Label>Session</Label>
        </div>
        <div className="body">
          <h1 className="display">{r.topic || "Untitled session"}</h1>
          {r.summary && <p className={`lede ${s.summary}`}>{r.summary}</p>}
        </div>
      </section>

      {/* ── what moved ─────────────────────────────────────────────────── */}
      <section className="ruled">
        <div className="margin">
          <Label tone="accent">What changed</Label>
        </div>
        <div className="body">
          {!r.has_recap ? (
            <Panel>
              <p className={s.muted}>
                This session closed before before/after records were kept, so
                there is nothing to compare. Sessions from here on will show it.
              </p>
            </Panel>
          ) : r.changes.length === 0 ? (
            <Panel>
              <p className={s.muted}>
                Nothing changed. Everything covered was already on record the
                same way.
              </p>
            </Panel>
          ) : (
            <ul className={s.changes}>
              {r.changes.map((c) => (
                <ChangeRow key={`${c.kind}:${c.concept_id}`} change={c} />
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* ── the full picture, both sides ───────────────────────────────── */}
      {r.has_recap && concepts.length > 0 && (
        <section className="ruled">
          <div className="margin">
            <Label>Before and after</Label>
          </div>
          <div className="body">
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th>Concept</th>
                    <th>Before</th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {concepts.map((cid) => {
                    const a = r.before.mastery[cid]?.mastery ?? null;
                    const b = r.after.mastery[cid]?.mastery ?? null;
                    const moved = a !== b;
                    return (
                      <tr key={cid} className={moved ? s.movedRow : undefined}>
                        <td>{conceptName(cid) || cid}</td>
                        <td className={s.cellWas}>{label(a)}</td>
                        <td className={moved ? s.cellNow : undefined}>{label(b)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* ── what the reflection asked for, including what was refused ──── */}
      {r.operations.length > 0 && (
        <section className="ruled">
          <div className="margin">
            <Label>Proposed by review</Label>
          </div>
          <div className="body">
            <p className={s.opsNote}>
              After the session an observer reads the transcript and proposes
              changes. Each one is checked before it is written — the refused
              ones are shown too.
            </p>
            <ul className={s.ops}>
              {r.operations.map((op, i) => (
                <li key={i} className={op.applied ? s.opOk : s.opDropped}>
                  <span className={s.opName}>{op.op}</span>
                  <span className={s.opConcept}>
                    {conceptName(op.concept_id) || op.concept_id || "—"}
                  </span>
                  <span className={s.opVerdict}>
                    {op.applied ? "written" : "refused"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* ── the evidence ───────────────────────────────────────────────── */}
      {r.turns.length > 0 && (
        <section className="ruled">
          <div className="margin">
            <Label>Transcript</Label>
          </div>
          <div className="body">
            <details className={s.transcript}>
              <summary className={s.transcriptToggle}>
                {r.turns.length} turns
              </summary>
              <ol className={s.turns}>
                {r.turns.map((t) => (
                  <li key={t.turn} className={t.role === "tutor" ? s.tutor : s.student}>
                    <span className={s.who}>{t.role === "tutor" ? "Nityam" : "You"}</span>
                    <span className={s.said}>{t.text}</span>
                  </li>
                ))}
              </ol>
            </details>
          </div>
        </section>
      )}
    </Shell>
  );
}
