import { useState } from "react";
import { Button, Label } from "../../components/ui";
import { useShrutiIngest, youtubeVideoId } from "../../lib/shruti";
import s from "./ShrutiIngest.module.css";

/* Paste a class recording's YouTube link, watch it while Shruti extracts
 * what was taught. This talks to a real backend endpoint (backend/app/
 * shruti_routes.py) that shells out to the actual Shruti pipeline — nothing
 * here is a mock. A run genuinely takes 10-20 minutes and can genuinely
 * fail (Shruti needs its own Postgres + Gemini credentials configured,
 * separately from this app's), so every state below is the real one, not
 * a staged demo. */
export default function ShrutiIngest() {
  const [url, setUrl] = useState("");
  const { run, error, start, reset } = useShrutiIngest();
  const videoId = youtubeVideoId(url);

  const busy = run?.status === "running";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!videoId) return;
    start({ youtube_url: url.trim() });
  }

  return (
    <section className={s.panel}>
      <div className={s.head}>
        <Label>Add a class recording</Label>
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
        <Button type="submit" variant="primary" disabled={busy || !videoId}>
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
            Reading the recording — transcript, board, and concepts. This runs
            10-20 minutes; you can leave this page and come back.
          </p>
        </div>
      )}

      {run?.status === "done" && (
        <div className={s.done}>
          <p className={s.doneText}>
            Done. What was taught is now saved — citations back to this
            recording will start showing up the next time you ask about it.
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
    </section>
  );
}
