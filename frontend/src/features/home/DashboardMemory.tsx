import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Label, Panel } from "../../components/ui";
import { conceptName } from "../../lib/conceptCatalog";
import { useAuth } from "../../lib/auth/AuthContext";
import {
  MASTERY,
  fetchSessions,
  useStudentMemory,
  type SessionListItem,
} from "../../lib/memory";
import s from "./DashboardMemory.module.css";

/* What I remember, on the dashboard.
 *
 * Both of these already had their own screens, and nothing on the way in
 * pointed at either — so a student (or a judge) had to know to go looking
 * before the memory layer existed for them at all. This is the pointer: the
 * last session with enough of its summary to recognise it, and the shape of
 * the record, each linking to the full thing. */

function when(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return "Earlier today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString([], { day: "numeric", month: "short" });
}

export default function DashboardMemory() {
  const { user } = useAuth();
  const memory = useStudentMemory(user?.uid);
  const [sessions, setSessions] = useState<SessionListItem[] | null>(null);

  useEffect(() => {
    if (!user?.uid) return;
    let live = true;
    fetchSessions(user.uid)
      .then((d) => live && setSessions(d.sessions))
      .catch(() => live && setSessions([]));
    return () => {
      live = false;
    };
  }, [user?.uid]);

  const last = sessions?.[0] ?? null;
  const profile = memory.status === "ready" ? memory.data.long_term.dpm_profile : null;
  const teaching = memory.status === "ready" ? memory.data.long_term.teaching_memory : null;

  const weakest = profile
    ? Object.entries(profile.weaknesses)
        .sort(
          (a, b) =>
            (MASTERY[a[1].mastery]?.rank ?? 9) - (MASTERY[b[1].mastery]?.rank ?? 9),
        )
        .slice(0, 3)
    : [];
  const openDoubts =
    teaching?.open_doubts.filter((d) => d.status !== "resolved").length ?? 0;

  return (
    <section className={`ruled ${s.band}`}>
      <div className="margin">
        <Label>What I remember</Label>
      </div>

      <div className={`body ${s.grid}`}>
        {/* ── the last session ──────────────────────────────────────────── */}
        <Panel as="aside" style={{ padding: 0 }}>
          <div className={s.head}>
            <Label>Last session</Label>
            <Link to="/sessions" className={s.more}>All sessions →</Link>
          </div>

          {sessions === null ? (
            <p className={s.empty}>Loading…</p>
          ) : !last ? (
            <p className={s.empty}>
              Nothing yet. Your first session will show up here the moment it
              ends, along with everything it changed.
            </p>
          ) : (
            <Link to={`/sessions/${last.session_id}`} className={s.session}>
              <div className={s.sessionHead}>
                <span className={s.topic}>{last.topic || "Untitled session"}</span>
                <span className={s.when}>{when(last.ended_at)}</span>
              </div>
              {last.summary && <p className={s.summary}>{last.summary}</p>}
              {/* A session with no snapshots is not one that changed nothing —
                  it closed before recaps were kept, and those are different
                  facts. */}
              {last.has_recap && last.changed > 0 && (
                <span className={s.changed}>
                  {last.changed} {last.changed === 1 ? "change" : "changes"} to what I know
                </span>
              )}
            </Link>
          )}
        </Panel>

        {/* ── the record itself ─────────────────────────────────────────── */}
        <Panel as="aside" style={{ padding: 0 }}>
          <div className={s.head}>
            <Label>Your profile</Label>
            <Link to="/profile" className={s.more}>See all →</Link>
          </div>

          {memory.status !== "ready" ? (
            <p className={s.empty}>
              {memory.status === "loading" ? "Loading…" : "Couldn't reach your memory."}
            </p>
          ) : weakest.length === 0 ? (
            <p className={s.empty}>
              I haven't formed a view on anything yet — that starts after your
              first session.
            </p>
          ) : (
            <>
              <ul className={s.weak}>
                {weakest.map(([cid, w]) => (
                  <li key={cid}>
                    <span className={s.weakName}>{conceptName(cid)}</span>
                    <span className={s.weakState}>
                      {MASTERY[w.mastery]?.label ?? w.mastery}
                    </span>
                  </li>
                ))}
              </ul>
              <p className={s.foot}>
                {Object.keys(profile?.weaknesses ?? {}).length} concepts tracked
                {openDoubts > 0 && ` · ${openDoubts} open doubt${openDoubts === 1 ? "" : "s"}`}
              </p>
            </>
          )}
        </Panel>
      </div>
    </section>
  );
}
