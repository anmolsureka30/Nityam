/* Unit test for the pure logic extracted out of two .tsx component files
 * (EventTimeline.tsx's groupByTrace, SessionView.tsx's REST-backlog mapping)
 * into plain .ts files under src/lib/ so it's importable from a Node script
 * via tsx, without a browser or a build step — see src/lib/groupByTrace.ts
 * and src/lib/observatoryEvent.ts for why this split exists.
 *
 * The original plan (Task 6 Step 8) assumed this was possible for the
 * component files directly; that assumption was wrong for .tsx, which is
 * why it was skipped. It IS feasible for plain .ts logic, which is what
 * this exercises.
 *
 *   npx tsx tests/observatoryEvent.test.mjs
 */
import assert from "node:assert/strict";
import { groupByTrace } from "../src/lib/groupByTrace.ts";
import { mapBacklogEvent } from "../src/lib/observatoryEvent.ts";

let passed = 0;

function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok  ${name}`);
}

function memoryEvent(event_id, trace_id) {
  return {
    kind: "memory",
    event: {
      event_id, ts: "2026-08-30T00:00:00Z", session_id: "s1", student_id: "stu1",
      tier: "workflow", operation: "write", record_type: "turn_buffer",
      source_fn: "append_turn", trace_id, span_id: trace_id ? "span-" + trace_id : null,
      payload: { buffer_length: 1 },
    },
    diff: [],
  };
}

function toolCallEvent(event_id, trace_id) {
  return {
    kind: "tool_call",
    event: {
      event_id, ts: "2026-08-30T00:00:00Z", session_id: "s1", student_id: "stu1",
      trace_id, span_id: trace_id ? "span-" + trace_id : null,
      actor: "board_agent", tool_name: "search_grounding", phase: "done",
      args_summary: null, result_summary: "3 chunks found", duration_ms: 842,
    },
  };
}

// ---- groupByTrace -----------------------------------------------------

test("groupByTrace merges consecutive events sharing one trace_id, across event kinds", () => {
  const events = [memoryEvent("e1", "t1"), toolCallEvent("e2", "t1")];
  const groups = groupByTrace(events);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].traceId, "t1");
  assert.equal(groups[0].events.length, 2);
});

test("groupByTrace starts a new group when trace_id changes, including into/out of null", () => {
  const events = [
    memoryEvent("e1", "t1"),
    toolCallEvent("e2", "t1"), // merges with e1 (same trace_id, consecutive)
    memoryEvent("e3", null), // no trace_id -> its own group
    toolCallEvent("e4", "t2"), // a different trace_id -> its own group
    memoryEvent("e5", "t1"), // back to t1, but NOT consecutive with the first t1 group -> its own group
  ];
  const groups = groupByTrace(events);
  assert.deepEqual(
    groups.map((g) => g.traceId),
    ["t1", null, "t2", "t1"],
  );
  assert.deepEqual(
    groups.map((g) => g.events.length),
    [2, 1, 1, 1],
  );
  assert.deepEqual(
    groups.map((g) => g.events.map((e) => e.event.event_id)),
    [["e1", "e2"], ["e3"], ["e4"], ["e5"]],
  );
});

test("groupByTrace returns an empty list for an empty input", () => {
  assert.deepEqual(groupByTrace([]), []);
});

// ---- mapBacklogEvent ----------------------------------------------------
//
// The exact logic the recent production fix added ("Fix session_events_
// endpoint dropping tool-call history from the REST backlog") with zero
// test coverage until now. Fixtures match the real wire shapes: a
// MemoryEvent's own JSON never carries a "kind" field (see
// app/memory/instrumentation.py); a ToolCallEvent's always does.

test("mapBacklogEvent maps a raw memory-event-shaped object (no kind field) to a memory ObservatoryEvent", () => {
  const raw = {
    event_id: "e1", ts: "2026-08-30T00:00:00Z", session_id: "s1", student_id: "stu1",
    tier: "workflow", operation: "write", record_type: "turn_buffer",
    source_fn: "append_turn", trace_id: "abc", span_id: "def",
    payload: { buffer_length: 1 },
  };
  const mapped = mapBacklogEvent(raw);
  assert.equal(mapped.kind, "memory");
  assert.equal(mapped.event, raw);
  assert.deepEqual(mapped.diff, []);
});

test("mapBacklogEvent maps a raw tool-call-event-shaped object (kind: tool_call) to a tool_call ObservatoryEvent", () => {
  const raw = {
    kind: "tool_call", event_id: "tc1", ts: "2026-08-30T00:00:00Z", session_id: "s1", student_id: "stu1",
    trace_id: "abc", span_id: "def", actor: "board_agent", tool_name: "search_grounding",
    phase: "done", args_summary: null, result_summary: "3 chunks found", duration_ms: 842,
  };
  const mapped = mapBacklogEvent(raw);
  assert.equal(mapped.kind, "tool_call");
  assert.equal(mapped.event, raw);
  assert.ok(!("diff" in mapped), "a tool_call ObservatoryEvent must not carry a memory-only diff field");
});

console.log(`observatoryEvent.test.mjs: PASS — ${passed} checks`);
