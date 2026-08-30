import { useEffect, useState } from "react";
import { Button, Label } from "../../components/ui";
import { useAuth } from "../../lib/auth/AuthContext";
import { selectTopic, useCurrentTopic, useTopicHistory } from "../../lib/memory";
import { useShrutiIngest, youtubeVideoId } from "../../lib/shruti";
import s from "./ShrutiIngest.module.css";

/* Paste a class recording's YouTube link, watch it while Shruti extracts
 * what was taught. This talks to a real backend endpoint (backend/app/
 * shruti_routes.py) that shells out to the actual Shruti pipeline — nothing
 * here is a mock. A run genuinely takes 10-20 minutes and can genuinely
 * fail (Shruti needs its own Postgres + Gemini credentials configured,
 * separately from this app's), so every state below is the real one, not
 * a staged demo.
 *
 * Runs in the background on the server the moment it starts (a detached
 * thread, not this request) — so submitting a link and then going straight
 * into a session works; the extraction keeps going either way and the next
 * "revise today's class" card picks it up whenever it finishes. */
export default function ShrutiIngest() {
  const [url, setUrl] = useState("");
  const { user } = useAuth();
  const { run, error, start, reset } = useShrutiIngest(user?.uid);
  const history = useTopicHistory(user?.uid);
  const currentTopic = useCurrentTopic(user?.uid);
  const [switching, setSwitching] = useState<string | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const videoId = youtubeVideoId(url);

  const busy = run?.status === "running";
  const activeSlug = currentTopic.status === "ready" ? currentTopic.data.recording_slug : "";

  // A run finishing is exactly when a new entry exists to pick from — the
  // history list otherwise only loads once, on mount, and would miss an
  // upload that completed during this same visit.
  useEffect(() => {
    if (run?.status === "done") history.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!videoId || !user?.uid) return;
    start({ youtube_url: url.trim(), student_id: user.uid });
  }

  function studyThis(recordingSlug: string) {
    if (!user) return;
    setSwitching(recordingSlug);
    setSwitchError(null);
    selectTopic(user, recordingSlug)
      // A full reload rather than re-fetching each piece separately: the
      // "revise today's class" card, this list's own active marker, and
      // whatever a new session opens on all read current_topic independently
      // — reloading is the one change that is obviously correct everywhere
      // at once (same call AccountMenu's own reset already makes).
      .then(() => window.location.reload())
      .catch((e: Error) => {
        setSwitching(null);
        setSwitchError(e.message);
      });
  }

  return (
    <section className={s.panel}>
      <div className={s.head}>
        <Label>Add a class recording (takes a few minutes)</Label>
      </div>

      <form className={s.form} onSubmit={submit}>
        <input
          type="url"
          inputMode="url"
          placeholder="Paste a YouTube link to today's class"
          value={url}
          disabled={busy}
          onChange={(e) => setUrl(e.target.value)}
          className={s.input}
        />
        <Button type="submit" variant="primary" disabled={busy || !videoId || !user?.uid}>
          {busy ? "Extracting…" : "Extract what was taught"}
        </Button>
      </form>

      {videoId && (
        <div className={s.preview}>
          <iframe
            className={s.frame}
            src={`https://www.youtube.com/embed/${videoId}`}
            title="Class recording preview"
            allow="accelerate-compute; encrypted-media; picture-in-picture"
            allowFullScreen
          />
        </div>
      )}

      {run?.status === "running" && (
        <div className={s.status}>
          <span className={s.spinner} aria-hidden="true" />
          <p className={s.statusText}>
            {run.video_title ? `Reading "${run.video_title}"` : "Reading the recording"}
            {" "}— transcript, board, and concepts. This runs 10-20 minutes; you can leave this
            page and come back.
          </p>
        </div>
      )}

      {run?.status === "done" && (
        <div className={s.done}>
          <p className={s.doneText}>
            Done. What was taught{run.video_title ? ` in "${run.video_title}"` : ""} is now
            saved — your next session opens on it, and citations back to this recording will
            start showing up the next time you ask about it.
          </p>
          <Button onClick={reset}>Add another</Button>
        </div>
      )}

      {run?.status === "failed" && (
        <div className={s.failed}>
          <p className={s.failedText}>
            The extraction didn't finish. The details below are the real
            reason, for whoever's setting this up:
          </p>
          <pre className={s.log}>{run.log_tail || "(no output captured)"}</pre>
          <Button onClick={reset}>Try again</Button>
        </div>
      )}

      {run?.status === "running" && run.log_tail && (
        <details className={s.details}>
          <summary className={s.summary}>What Shruti is finding so far</summary>
          <pre className={s.log}>{run.log_tail}</pre>
        </details>
      )}

      {error && <p className={s.errorText}>{error}</p>}

      {history.status === "ready" && history.data.length > 1 && (
        <div className={s.history}>
          <Label>Study from</Label>
          <ul className={s.historyList}>
            {history.data.map((topic) => {
              const active = topic.recording_slug === activeSlug;
              return (
                <li key={topic.recording_slug} className={s.historyRow}>
                  <span className={s.historyTitle} title={topic.video_title || topic.heading}>
                    {topic.video_title || topic.heading}
                  </span>
                  {active ? (
                    <span className={s.historyActive}>Studying now</span>
                  ) : (
                    <Button
                      onClick={() => studyThis(topic.recording_slug)}
                      disabled={switching !== null}
                    >
                      {switching === topic.recording_slug ? "Switching…" : "Study this"}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
          {switchError && <p className={s.errorText}>{switchError}</p>}
        </div>
      )}
    </section>
  );
}
