"""Orchestrates the full memory-layer eval: runs all 5 personas' multi-session
scenarios against the real TutorAgent, runs deterministic checks (D1-D7) and
LLM-judge checks (L1-L4), writes a report, cleans up.

Run: uv run python -m tests.eval.memory_eval.run_eval

Agent execution and LLM judging run in TWO SEPARATE PROCESSES, not just two
event loops. Confirmed live, five times, across four fix attempts (a
same-process retry, a sync-to-async client switch, structurally separating
agent-vs-judge code within one process, and a second asyncio.run() for a
fresh event loop): none of them stopped a direct genai.Client() call from
failing immediately - on the FIRST judging call, in a brand-new event loop,
with zero prior aiohttp activity in that loop - after ADK agent execution
had run earlier in the SAME PROCESS. A minimal isolated script with no ADK
involvement at all succeeded immediately. That combination (fails only
after ADK ran earlier in the process; a fresh event loop doesn't help; a
fresh process does) points at process-wide module-level state in
google-genai or google-adk, not anything loop-scoped - see
judge_subprocess.py for the actual isolation.

Agent-phase results are cached to disk (pickle) so the judging phase can be
retried without re-running the expensive, LLM-heavy agent phase - useful
during development, and cheap insurance against a judging-phase failure in
a real run.
"""
from __future__ import annotations

import asyncio
import json
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.memory import store
from tests.eval.memory_eval.deterministic_checks import run_all_deterministic_checks
from tests.eval.memory_eval.harness import PersonaResult, cleanup_persona, run_persona_scenario
from tests.eval.memory_eval.personas import PERSONAS

REPORT_DIR = Path(__file__).parent / "report"
CACHE_PATH = REPORT_DIR / "_agent_phase_cache.pkl"


async def run_agent_phase() -> list[PersonaResult]:
    print(f"Running memory-layer eval across {len(PERSONAS)} personas...")
    results = []
    for persona in PERSONAS:
        print(f"\n=== {persona.display_name} ({persona.student_id}) ===")
        result = await run_persona_scenario(persona)
        results.append(result)
        for trace in result.session_traces:
            n_tool_calls = sum(len(t.tool_calls) for t in trace.turns)
            print(f"  {trace.label}: {len(trace.turns)} turns, {n_tool_calls} tool calls")
    return results


def run_judging_phase(results: list[PersonaResult]):
    print("Running LLM-as-judge checks (L1-L4) in a separate process...")
    in_path = REPORT_DIR / "_judge_phase_in.pkl"
    out_path = REPORT_DIR / "_judge_phase_out.pkl"
    REPORT_DIR.mkdir(exist_ok=True)
    in_path.write_bytes(pickle.dumps(results))
    subprocess.run(
        [sys.executable, "-m", "tests.eval.memory_eval.judge_subprocess", str(in_path), str(out_path)],
        check=True,
    )
    judge_results = pickle.loads(out_path.read_bytes())
    in_path.unlink(missing_ok=True)
    out_path.unlink(missing_ok=True)
    return judge_results


async def do_cleanup() -> None:
    print("\nCleaning up eval data...")
    db = store.connect()
    for persona in PERSONAS:
        await cleanup_persona(persona, db)
    print("Done.")


def _summarize_tool_result(tc) -> str:
    """Full tool results (especially search_grounding's chunk text) are too
    large for a readable report - a short summary is enough to diagnose
    D1-style failures (e.g. "0 chunks" immediately shows a retrieval miss)
    without dumping every retrieved chunk's full text into the JSON."""
    if tc.result is None:
        return "(no result captured)"
    if tc.name == "search_grounding" or tc.name == "search_grounding_semantic":
        chunks = tc.result.get("chunks", [])
        return f"{len(chunks)} chunk(s): {[c.get('chunk_id') for c in chunks]}"
    if tc.name in ("get_dpm", "get_teaching_memory"):
        return f"found={tc.result.get('found')}"
    return str(tc.result)[:200]


def write_report(results: list[PersonaResult], det_checks, judge_results) -> Path:
    timestamp = datetime.now(timezone.utc).isoformat()
    report = {
        "timestamp": timestamp,
        "personas": [p.student_id for p in PERSONAS],
        "deterministic_checks": [
            {"check_id": c.check_id, "persona": c.persona, "passed": c.passed, "detail": c.detail}
            for c in det_checks
        ],
        "judge_checks": [
            {"check_id": j.check_id, "persona": j.persona, "score": j.score, "passed": j.passed, "rationale": j.rationale}
            for j in judge_results
        ],
        "transcripts": {
            result.persona.student_id: [
                {
                    "session": trace.label,
                    "turns": [
                        {
                            "role": t.role, "text": t.text,
                            "tool_calls": [
                                {"name": tc.name, "args": tc.args, "result_summary": _summarize_tool_result(tc)}
                                for tc in t.tool_calls
                            ],
                        }
                        for t in trace.turns
                    ],
                }
                for trace in result.session_traces
            ]
            for result in results
        },
    }
    REPORT_DIR.mkdir(exist_ok=True)
    json_path = REPORT_DIR / f"results_{timestamp.replace(':', '-')}.json"
    json_path.write_text(json.dumps(report, indent=2))
    return json_path


def print_summary(det_checks, judge_results, json_path: Path) -> None:
    n_det_pass = sum(1 for c in det_checks if c.passed)
    n_judge_pass = sum(1 for j in judge_results if j.passed)
    print(f"\n=== SUMMARY ===")
    print(f"Deterministic: {n_det_pass}/{len(det_checks)} passed")
    print(f"Judge: {n_judge_pass}/{len(judge_results)} passed")
    print(f"Full report: {json_path}")

    print("\nFailures:")
    for c in det_checks:
        if not c.passed:
            print(f"  FAIL [{c.check_id}] {c.persona}: {c.detail}")
    for j in judge_results:
        if not j.passed:
            print(f"  FAIL [{j.check_id}] {j.persona} (score={j.score}): {j.rationale[:150]}")


def main() -> None:
    if CACHE_PATH.exists():
        print(f"Reusing cached agent-phase results from {CACHE_PATH} (delete it to force a fresh agent run)")
        results: list[PersonaResult] = pickle.loads(CACHE_PATH.read_bytes())
    else:
        results = asyncio.run(run_agent_phase())
        REPORT_DIR.mkdir(exist_ok=True)
        CACHE_PATH.write_bytes(pickle.dumps(results))

    print("\nRunning deterministic checks (D1-D7)...")
    det_checks = run_all_deterministic_checks(results)

    judge_results = run_judging_phase(results)

    json_path = write_report(results, det_checks, judge_results)
    print_summary(det_checks, judge_results, json_path)

    asyncio.run(do_cleanup())
    CACHE_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
