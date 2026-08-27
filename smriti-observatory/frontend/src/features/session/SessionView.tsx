import { useEffect, useState } from "react";
import { DiffView } from "../../components/DiffView";
import { EventTimeline } from "../../components/EventTimeline";
import { SessionDrawer, type SessionSummary } from "../../components/SessionDrawer";
import { SidePanel } from "../../components/SidePanel";
import { TierPanel } from "../../components/TierPanel";
import { adkWebUrl } from "../../lib/traceLinks";
import type { EnrichedEvent, SessionState } from "../../lib/types";
import { connectSessionSocket } from "../../lib/ws";

const BACKEND_URL = import.meta.env.VITE_OBSERVATORY_BACKEND_URL ?? "http://localhost:8100";
const TUTOR_BASE_URL = import.meta.env.VITE_TUTOR_BASE_URL ?? "http://localhost:8000";
const GCP_PROJECT = import.meta.env.VITE_GCP_PROJECT ?? "nityam-506707";

export function SessionView() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [events, setEvents] = useState<EnrichedEvent[]>([]);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/sessions`)
      .then((r) => r.json())
      .then((body) => setSessions(body.sessions ?? []))
      .catch(() => setSessions([]));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setEvents([]);
    const studentId = sessions.find((s) => s.session_id === selectedId)?.student_id ?? "demo_student";
    fetch(`${BACKEND_URL}/api/sessions/${selectedId}/state?student_id=${studentId}`)
      .then((r) => r.json())
      .then(setState)
      .catch(() => setState(null));
    fetch(`${BACKEND_URL}/api/sessions/${selectedId}/events`)
      .then((r) => r.json())
      .then((body) => setEvents((body.events ?? []).map((event: EnrichedEvent["event"]) => ({ event, diff: [] }))))
      .catch(() => {});

    return connectSessionSocket(BACKEND_URL.replace("http", "ws"), selectedId, (enriched) => {
      setEvents((prev) => [...prev, enriched]);
    });
  }, [selectedId, sessions]);

  const workflowEvents = events.filter((e) => e.event.tier === "workflow");
  const episodicEvents = events.filter((e) => e.event.tier === "episodic");
  const longTermEvents = events.filter((e) => e.event.tier === "long_term" && e.event.operation === "write");
  const latestDiff = longTermEvents.at(-1)?.diff ?? [];

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <SessionDrawer sessions={sessions} selectedId={selectedId} onSelect={setSelectedId} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {selectedId && (
          <>
            <header style={{ padding: 12, display: "flex", gap: 12, alignItems: "center" }}>
              <strong>{selectedId}</strong>
              <a href={adkWebUrl(TUTOR_BASE_URL)} target="_blank" rel="noreferrer">
                Open in ADK web
              </a>
            </header>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <EventTimeline events={events} gcpProject={GCP_PROJECT} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, padding: 8 }}>
              <TierPanel
                tier="workflow"
                title="Workflow"
                events={workflowEvents}
                content={<pre>{JSON.stringify(state?.workflow.turn_buffer ?? [], null, 2)}</pre>}
              />
              <TierPanel
                tier="episodic"
                title="Episodic"
                events={episodicEvents}
                content={<pre>{JSON.stringify(state?.episodic.session_log, null, 2)}</pre>}
              />
              <TierPanel tier="long_term" title="Long-term" events={longTermEvents} content={<DiffView changes={latestDiff} />} />
            </div>
          </>
        )}
      </main>
      <SidePanel
        tabs={[
          { id: "workflow", label: "Workflow", content: <pre>{JSON.stringify(state?.workflow, null, 2)}</pre> },
          { id: "episodic", label: "Episodic", content: <pre>{JSON.stringify(state?.episodic, null, 2)}</pre> },
          { id: "long_term", label: "Long-term", content: <pre>{JSON.stringify(state?.long_term, null, 2)}</pre> },
          { id: "diff", label: "Diff", content: <DiffView changes={latestDiff} /> },
          { id: "sessions", label: "Sessions", content: <SessionDrawer sessions={sessions} selectedId={selectedId} onSelect={setSelectedId} /> },
        ]}
      />
    </div>
  );
}
