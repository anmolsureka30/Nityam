import { useEffect, useMemo, useRef, useState } from "react";
import { AgentToolGraph } from "../../components/AgentToolGraph";
import { EventTimeline } from "../../components/EventTimeline";
import { Inspector } from "../../components/Inspector";
import { SessionDrawer, type SessionSummary } from "../../components/SessionDrawer";
import { SidePanel } from "../../components/SidePanel";
import { StateOverview } from "../../components/StateOverview";
import { StatusChips } from "../../components/StatusChips";
import { adkWebUrl } from "../../lib/traceLinks";
import type { EnrichedEvent, MemoryEvent, ObservatoryEvent, SessionState, Tier, ToolCallEvent } from "../../lib/types";
import { connectSessionSocket } from "../../lib/ws";

const BACKEND_URL = import.meta.env.VITE_OBSERVATORY_BACKEND_URL ?? (import.meta.env.DEV ? "http://localhost:8100" : "/observatory");
const TUTOR_BASE_URL = import.meta.env.VITE_TUTOR_BASE_URL ?? "http://localhost:8000";
const GCP_PROJECT = import.meta.env.VITE_GCP_PROJECT ?? "nityam-506707";

const EMPTY_COUNTS: Record<Tier, number> = { workflow: 0, episodic: 0, long_term: 0 };

export function SessionView() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [events, setEvents] = useState<ObservatoryEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ObservatoryEvent | null>(null);
  const [activeTier, setActiveTier] = useState<Tier | null>(null);
  const sessionsRef = useRef<SessionSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    const fetchSessions = () => {
      fetch(`${BACKEND_URL}/api/sessions`)
        .then((r) => r.json())
        .then((body) => {
          if (cancelled) return;
          setSessions(body.sessions ?? []);
        })
        .catch(() => {
          if (!cancelled) setSessions([]);
        });
    };
    fetchSessions();
    const interval = setInterval(fetchSessions, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Kept out of the effect below on purpose: `sessions` is refetched (and
  // gets a new array reference) independently of session selection — e.g.
  // React StrictMode's dev double-invoke, or the periodic refresh above —
  // and including it in that effect's deps would restart the events/state
  // fetch and websocket every time, discarding whatever had just loaded.
  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  // Auto-select the most-recently-active live session whenever there is no
  // selection yet, or the selected session just stopped being live while a
  // different one is now live -- never overrides a manual pick that's still
  // live. This is what makes the Observatory show a session with zero
  // clicks: open the page while backend/ has a live conversation, and it's
  // already there.
  useEffect(() => {
    const live = sessions.filter((s) => s.status === "live");
    if (live.length === 0) return;
    const currentlySelectedIsLive = live.some((s) => s.session_id === selectedId);
    if (selectedId && currentlySelectedIsLive) return;
    const newest = [...live].sort((a, b) => b.last_event_at.localeCompare(a.last_event_at))[0];
    setSelectedId(newest.session_id);
  }, [sessions, selectedId]);

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
      .then((body) =>
        // smriti:events:recent (what this backlog reads) holds both memory
        // and tool-call event JSON on one list -- a MemoryEvent's own JSON
        // never carries a "kind" field (see app/memory/instrumentation.py),
        // while a ToolCallEvent's does, which is exactly how ingest.py's own
        // live dispatch tells them apart too.
        setEvents(
          (body.events ?? []).map((event: MemoryEvent | ToolCallEvent): ObservatoryEvent =>
            "kind" in event && event.kind === "tool_call"
              ? { kind: "tool_call", event }
              : { kind: "memory", event: event as MemoryEvent, diff: [] },
          ),
        ),
      )
      .catch(() => {});

    return connectSessionSocket(BACKEND_URL.replace("http", "ws"), selectedId, (enriched) => {
      // The initial backlog fetch above and this live subscription start at
      // roughly the same time with no ordering coordination between them --
      // an event published in that overlap can land in both the REST
      // snapshot and the live push. Deduping by event_id (always a fresh
      // uuid4 per real event) keeps the timeline from rendering the same
      // event twice with a duplicate React key.
      setEvents((prev) => (prev.some((e) => e.event.event_id === enriched.event.event_id) ? prev : [...prev, enriched]));
    });
  }, [selectedId]);

  // Tool-call events have no tier/source_fn — they're not memory operations
  // — so the per-tier tallies, pulse indicators, and agent/tool graph
  // highlighting below (all inherited, unchanged UI) stay scoped to the
  // "memory" half of the union, exactly as before this task's change.
  const isMemoryEvent = (e: ObservatoryEvent): e is EnrichedEvent => e.kind === "memory";
  const memoryEvents = useMemo(() => events.filter(isMemoryEvent), [events]);

  const counts = useMemo(() => {
    const c: Record<Tier, number> = { ...EMPTY_COUNTS };
    for (const e of memoryEvents) c[e.event.tier] += 1;
    return c;
  }, [memoryEvents]);

  const pulsing = useMemo(() => {
    const p: Record<Tier, boolean> = { workflow: false, episodic: false, long_term: false };
    const now = Date.now();
    for (const e of memoryEvents) {
      if (now - new Date(e.event.ts).getTime() < 1500) p[e.event.tier] = true;
    }
    return p;
  }, [memoryEvents]);

  const filteredEvents = activeTier ? events.filter((e) => isMemoryEvent(e) && e.event.tier === activeTier) : events;
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
    const matching = (traceId ? events.filter((e) => e.event.trace_id === traceId) : [selectedEvent]).filter(isMemoryEvent);
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
