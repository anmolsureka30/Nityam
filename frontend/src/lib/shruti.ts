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
}

export interface IngestRequest {
  youtube_url: string;
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

/** Starts a run and polls it until it finishes, entirely client-driven — the
 *  backend has no push channel for this (it's a background subprocess, not
 *  a websocket participant), so polling is the honest mechanism rather than
 *  a workaround. */
export function useShrutiIngest() {
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

  const start = useCallback(
    (req: IngestRequest) => {
      setError(null);
      setRun(null);
      startIngest(req)
        .then((info) => {
          setRun(info);
          if (info.status === "running") {
            timer.current = window.setTimeout(() => poll(info.run_id), POLL_MS);
          }
        })
        .catch((e: Error) => setError(e.message));
    },
    [poll],
  );

  const reset = useCallback(() => {
    stopPolling();
    setRun(null);
    setError(null);
  }, [stopPolling]);

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
