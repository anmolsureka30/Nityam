import { useEffect, useMemo, useRef, useState } from "react";
import { AgentToolGraph } from "../../components/AgentToolGraph";
import { EventTimeline } from "../../components/EventTimeline";
import { Inspector } from "../../components/Inspector";
import { SessionDrawer, type SessionSummary } from "../../components/SessionDrawer";
import { SidePanel } from "../../components/SidePanel";
import { StateOverview } from "../../components/StateOverview";
import { StatusChips } from "../../components/StatusChips";
import { adkWebUrl } from "../../lib/traceLinks";
import type { EnrichedEvent, SessionState, Tier } from "../../lib/types";
import { connectSessionSocket } from "../../lib/ws";

const BACKEND_URL = import.meta.env.VITE_OBSERVATORY_BACKEND_URL ?? "http://localhost:8100";
const TUTOR_BASE_URL = import.meta.env.VITE_TUTOR_BASE_URL ?? "http://localhost:8000";
const GCP_PROJECT = import.meta.env.VITE_GCP_PROJECT ?? "nityam-506707";

const EMPTY_COUNTS: Record<Tier, number> = { workflow: 0, episodic: 0, long_term: 0 };

export function SessionView() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [events, setEvents] = useState<EnrichedEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EnrichedEvent | null>(null);
  const [activeTier, setActiveTier] = useState<Tier | null>(null);
  const sessionsRef = useRef<SessionSummary[]>([]);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/sessions`)
      .then((r) => r.json())
      .then((body) => setSessions(body.sessions ?? []))
      .catch(() => setSessions([]));
  }, []);

  // Kept out of the effect below on purpose: `sessions` is refetched (and
  // gets a new array reference) independently of session selection — e.g.
  // React StrictMode's dev double-invoke, or a future periodic refresh —
  // and including it in that effect's deps would restart the events/state
  // fetch and websocket every time, discarding whatever had just loaded.
  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  useEffect(() => {
    if (!selectedId) return;
    setEvents([]);
    setSelectedEvent(null);
    setActiveTier(null);
    const studentId = sessionsRef.current.find((s) => s.session_id === selectedId)?.student_id ?? "demo_student";
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
  }, [selectedId]);

  const counts = useMemo(() => {
    const c: Record<Tier, number> = { ...EMPTY_COUNTS };
    for (const e of events) c[e.event.tier] += 1;
    return c;
  }, [events]);

  const pulsing = useMemo(() => {
    const p: Record<Tier, boolean> = { workflow: false, episodic: false, long_term: false };
    const now = Date.now();
    for (const e of events) {
      if (now - new Date(e.event.ts).getTime() < 1500) p[e.event.tier] = true;
    }
    return p;
  }, [events]);

  const filteredEvents = activeTier ? events.filter((e) => e.event.tier === activeTier) : events;
  const selectedSession = sessions.find((s) => s.session_id === selectedId);

  // The agent/tool graph highlights whichever trace the selected event
  // belongs to — every operation that trace performed, not just the one
  // clicked, since one turn can touch several memory tiers in one call.
  // An event with no trace_id (nothing was in an active OpenTelemetry span
  // when it fired — shown as "untraced operation" in the timeline) can't be
  // grouped with siblings, so it falls back to highlighting just itself.
  const activeSourceFns = useMemo(() => {
    const map = new Map<string, Set<Tier>>();
    if (!selectedEvent) return map;
    const traceId = selectedEvent.event.trace_id;
    const matching = traceId ? events.filter((e) => e.event.trace_id === traceId) : [selectedEvent];
    for (const e of matching) {
      const tiers = map.get(e.event.source_fn) ?? new Set<Tier>();
      tiers.add(e.event.tier);
      map.set(e.event.source_fn, tiers);
    }
    return map;
  }, [events, selectedEvent]);

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <SessionDrawer sessions={sessions} selectedId={selectedId} onSelect={setSelectedId} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {selectedId ? (
          <>
            <header style={{ padding: "12px 16px", display: "flex", gap: 12, alignItems: "center", borderBottom: "1px solid var(--outline-variant)" }}>
              <strong style={{ fontFamily: "var(--font-mono)", fontSize: "0.9rem" }}>{selectedId}</strong>
              {selectedSession && (
                <span style={{ fontSize: "0.75rem", color: "var(--outline)" }}>
                  {selectedSession.student_id} · {selectedSession.status}
                </span>
              )}
              <a href={adkWebUrl(TUTOR_BASE_URL)} target="_blank" rel="noreferrer" style={{ marginLeft: "auto", fontSize: "0.8rem" }}>
                Open in ADK web ↗
              </a>
            </header>
            <StatusChips counts={counts} pulsing={pulsing} activeTier={activeTier} onSelectTier={setActiveTier} />
            <AgentToolGraph backendUrl={BACKEND_URL} activeSourceFns={activeSourceFns} />
            <EventTimeline
              events={filteredEvents}
              gcpProject={GCP_PROJECT}
              selectedEventId={selectedEvent?.event.event_id ?? null}
              onSelect={setSelectedEvent}
            />
          </>
        ) : (
          <div style={{ margin: "auto", color: "var(--outline)", fontSize: "0.9rem" }}>
            Select a session on the left to watch its memory change in real time.
          </div>
        )}
      </main>
      <SidePanel
        tabs={[
          {
            id: "state",
            label: "State",
            content: <StateOverview state={state} />,
          },
          {
            id: "inspector",
            label: "Inspector",
            content: <Inspector selected={selectedEvent} gcpProject={GCP_PROJECT} />,
          },
        ]}
      />
    </div>
  );
}
