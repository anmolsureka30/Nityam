/* The Shruti video-ingest pipeline, from the dashboard's side.
 *
 * Backend/'s new POST /shruti/ingest and GET /shruti/runs/{id} (see
 * backend/app/shruti_routes.py) shell out to Shruti's own CLI — Shruti has
 * no HTTP surface of its own — and report progress as a raw stdout tail,
 * because that is the only signal the real pipeline produces; there is no
 * structured per-stage percentage to poll instead. This module is the
 * frontend half of that same honesty: a run can genuinely fail (missing
 * credentials, no Postgres, a billing block) and this reports that plainly
 * rather than pretending a spinner is progress.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type RunStatus = "running" | "done" | "failed";

export interface RunInfo {
  run_id: string;
  status: RunStatus;
  started_at: number;
  returncode: number | null;
  log_tail: string;
  /** Resolved server-side via YouTube's oEmbed endpoint the moment the link
   *  was submitted — empty if the lookup failed, never blocks the run. */
  video_title: string;
}

export interface IngestRequest {
  youtube_url: string;
  /** Whoever is uploading — current_topic is written per-student server-side,
   *  so without this one person's upload would change what everybody else's
   *  next session opens on. */
  student_id: string;
  subject?: string;
  grade?: number;
  chapter?: string;
}

export class ShrutiFetchError extends Error {}

export async function startIngest(req: IngestRequest): Promise<RunInfo> {
  let res: Response;
  try {
    res = await fetch("/shruti/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch (e) {
    throw new ShrutiFetchError(`could not reach the ingest service: ${(e as Error).message}`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ShrutiFetchError(body?.detail ?? `ingest service returned ${res.status}`);
  }
  return (await res.json()) as RunInfo;
}

export async function getRun(runId: string): Promise<RunInfo> {
  const res = await fetch(`/shruti/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ShrutiFetchError(body?.detail ?? `ingest service returned ${res.status}`);
  }
  return (await res.json()) as RunInfo;
}

const POLL_MS = 3000;

/** Which run (if any) this student has in flight — survives navigating away
 *  from the dashboard and back (e.g. into a session and out again), which a
 *  plain useState does not: unmounting ShrutiIngest used to forget the
 *  run_id entirely, even though the backend kept extracting the whole time.
 *  Per-student so a shared browser can't show one account's run to another. */
const runIdKey = (studentId: string) => `nityam.shruti.run.${studentId}`;

function readSavedRunId(studentId: string | undefined): string | null {
  if (!studentId) return null;
  try {
    return window.localStorage.getItem(runIdKey(studentId));
  } catch {
    return null;
  }
}

function saveRunId(studentId: string | undefined, runId: string | null): void {
  if (!studentId) return;
  try {
    if (runId) window.localStorage.setItem(runIdKey(studentId), runId);
    else window.localStorage.removeItem(runIdKey(studentId));
  } catch {
    /* Not worth surfacing: the run keeps going server-side either way, this
       only affects whether the browser remembers to keep watching it. */
  }
}

/** Starts a run and polls it until it finishes, entirely client-driven — the
 *  backend has no push channel for this (it's a background subprocess, not
 *  a websocket participant), so polling is the honest mechanism rather than
 *  a workaround. */
export function useShrutiIngest(studentId: string | undefined) {
  const [run, setRun] = useState<RunInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  /* A named function expression, not `const poll = (id) => { ...poll(id)... }`:
     the name binds inside the function's own scope from creation, so it can
     call itself with no risk of the TDZ a static analyzer (rightly) flags on
     an outer const referenced before its declaration finishes — and unlike a
     ref, nothing here is written during render. */
  const poll = useCallback(function pollRun(runId: string): void {
    getRun(runId)
      .then((info) => {
        setRun(info);
        if (info.status === "running") {
          timer.current = window.setTimeout(() => pollRun(runId), POLL_MS);
        }
      })
      .catch((e: Error) => {
        setError(e.message);
      });
  }, []);

  // Resume whatever was already running before this component mounted. The
  // extraction itself never paused — only the browser's memory of watching
  // it did — so this is a re-attach, not a restart.
  useEffect(() => {
    const savedId = readSavedRunId(studentId);
    if (!savedId) return;
    getRun(savedId)
      .then((info) => {
        setRun(info);
        if (info.status === "running") {
          timer.current = window.setTimeout(() => poll(savedId), POLL_MS);
        }
      })
      .catch(() => {
        // Backend restarted since, or this id no longer means anything —
        // forget it quietly rather than show a permanent, unfixable error.
        saveRunId(studentId, null);
      });
    // studentId only: re-attaching should happen once per signed-in student,
    // not on every re-render `poll` identity change would otherwise cause.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId]);

  const start = useCallback(
    (req: IngestRequest) => {
      setError(null);
      setRun(null);
      startIngest(req)
        .then((info) => {
          setRun(info);
          saveRunId(studentId, info.run_id);
          if (info.status === "running") {
            timer.current = window.setTimeout(() => poll(info.run_id), POLL_MS);
          }
        })
        .catch((e: Error) => setError(e.message));
    },
    [poll, studentId],
  );

  const reset = useCallback(() => {
    stopPolling();
    setRun(null);
    setError(null);
    saveRunId(studentId, null);
  }, [stopPolling, studentId]);

  return { run, error, start, reset };
}

/** Accepts a watch page, share link, youtu.be link, or Shorts link; returns
 *  null for anything that isn't recognisably a YouTube URL, so the caller
 *  can decline to show a preview rather than embed garbage. */
export function youtubeVideoId(url: string): string | null {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtube\.com\/shorts\/|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/,
  ];
  for (const re of patterns) {
    const match = re.exec(url.trim());
    if (match) return match[1];
  }
  return null;
}
