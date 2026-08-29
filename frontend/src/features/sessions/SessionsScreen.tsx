import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { Label, Panel } from "../../components/ui";
import { useAuth } from "../../lib/auth/AuthContext";
import { fetchSessions, type SessionListItem } from "../../lib/memory";
import s from "./SessionsScreen.module.css";

/* Every session you have had, newest first.
 *
 * This screen exists because the memory layer was invisible. It has been
 * reading and writing a real record since it was built, and none of that was
 * observable anywhere — you had to read a server log to know it had happened.
 * A row here is one session; the number beside it is how many things the tutor
 * changed its mind about because of it. */

const MODE_LABEL: Record<string, string> = {
  revision: "Revision",
  doubt: "Doubt",
  exam: "Exam prep",
};

function when(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  const time = then.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (days <= 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString([], { day: "numeric", month: "short" });
}

function minutes(a: string | null, b: string | null): string {
  if (!a || !b) return "";
  const mins = Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60_000);
  return mins > 0 ? `${mins} min` : "";
}

export default function SessionsScreen() {
  const { user } = useAuth();
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "error"; error: string }
    | { status: "ready"; sessions: SessionListItem[] }
  >({ status: "loading" });

  useEffect(() => {
    if (!user?.uid) return;
    let live = true;
    fetchSessions(user.uid)
      .then((d) => live && setState({ status: "ready", sessions: d.sessions }))
      .catch((e) => live && setState({ status: "error", error: (e as Error).message }));
    return () => {
      live = false;
    };
  }, [user?.uid]);

  return (
    <Shell back={{ to: "/", label: "Dashboard" }}>
      <section className="ruled">
        <div className="margin">
          <Label>Your sessions</Label>
        </div>
        <div className="body">
          <h1 className="display">Everything we have worked on.</h1>
          <p className={`lede ${s.subline}`}>
            Open any one to see what I understood about you before it, and what
            changed by the end.
          </p>
        </div>
      </section>

      <section className="ruled">
        <div className="margin" />
        <div className="body">
          {state.status === "loading" && (
            <Panel><p className={s.muted}>Loading your sessions…</p></Panel>
          )}

          {state.status === "error" && (
            <Panel>
              <p className={s.muted}>
                Couldn't reach your memory just now ({state.error}).
              </p>
            </Panel>
          )}

          {state.status === "ready" && state.sessions.length === 0 && (
            <Panel>
              <p className={s.muted}>
                No sessions yet. Once you finish one it will appear here, with
                everything it changed.
              </p>
            </Panel>
          )}

          {state.status === "ready" && state.sessions.length > 0 && (
            <ol className={s.list}>
              {state.sessions.map((entry) => (
                <li key={entry.session_id}>
                  <Link to={`/sessions/${entry.session_id}`} className={s.row}>
                    <div className={s.rowHead}>
                      <span className={s.topic}>
                        {entry.topic || "Untitled session"}
                      </span>
                      <span className={s.meta}>
                        {[MODE_LABEL[entry.mode] ?? entry.mode,
                          minutes(entry.started_at, entry.ended_at),
                          `${entry.turns} turns`]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>

                    {entry.summary && (
                      <p className={s.summary}>{entry.summary}</p>
                    )}

                    <div className={s.rowFoot}>
                      <span className={s.when}>{when(entry.ended_at)}</span>
                      {/* A session with no recap is not a session that changed
                          nothing — it closed before recaps were recorded, and
                          saying "0 changes" would be a lie. */}
                      {!entry.has_recap ? (
                        <span className={s.noRecap}>no record kept</span>
                      ) : entry.changed > 0 ? (
                        <span className={s.changed}>
                          {entry.changed} {entry.changed === 1 ? "change" : "changes"} to what I know
                        </span>
                      ) : (
                        <span className={s.muted}>nothing changed</span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </Shell>
  );
}
