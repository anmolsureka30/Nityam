"""LLM-as-judge checks (L1-L4). Same pattern as the scaffolded
tests/eval/response_quality.py: google.genai, temperature=0, a Pydantic
response_schema for guaranteed-valid JSON.

L1 is deliberately a PAIRWISE comparison against a no-memory baseline, not
an absolute score - the eval design's research pass found that LLM tutor
responses often look personalized without actually being causally driven by
the injected context (adaptivity only emerged when specific context was
removed, in the one controlled ablation study found). An absolute "does
this look personalized" score can't catch that; a side-by-side comparison
against the same prompt with no memory can. This mirrors a pairwise
Win-Rate-style protocol the research also found used for judging tutoring
personalization specifically (target vs. baseline, same student context).
"""
from __future__ import annotations

import asyncio
import dataclasses

from google import genai
from pydantic import BaseModel

from tests.eval.memory_eval.harness import PersonaResult


@dataclasses.dataclass
class JudgeResult:
    check_id: str
    persona: str
    score: int | None
    passed: bool
    rationale: str


class _AbsoluteVerdict(BaseModel):
    score: int  # 1-5
    rationale: str


class _PairwiseVerdict(BaseModel):
    winner: str  # "with_memory" | "no_memory" | "tie"
    rationale: str


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Root cause of every earlier judging-phase failure, found via
    googleapis/python-genai#1489 and #1763 (and the matching aiohttp variant,
    #1453): calling `genai.Client()` as a temporary inline object - construct,
    call, discard, repeat - breaks starting in google-genai>=1.39.0, because
    the SDK's own cleanup can close the underlying transport while a request
    on a DIFFERENT temporary instance is still in flight. The fix documented
    in those issues: hold one persistent Client and reuse it - exactly the
    pattern session_close.py's reflect() already uses (a client passed in
    once per persona, in harness.py's run_persona_scenario) and exactly what
    every earlier attempt here got wrong by writing `genai.Client().models....`
    inline on every call. A process-wide singleton, not a fresh instance per
    call, per persona, or per judge."""
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


async def _generate(prompt: str, response_schema):
    """Sync client (matches session_close.py's reflect() exactly), called
    directly on the running thread - not via asyncio.to_thread, and not the
    async client. Neither of those was actually the bug (see _get_client's
    docstring); they were incidental across attempts that all still
    constructed a fresh Client() per call."""
    last_exc = None
    for attempt in range(3):
        try:
            return _get_client().models.generate_content(
                model="gemini-3.7-flash", contents=prompt,
                config={"temperature": 0, "response_mime_type": "application/json", "response_schema": response_schema},
            )
        except Exception as exc:  # noqa: BLE001 - retry any transient failure, not just the one we've seen
            last_exc = exc
            await asyncio.sleep(2 * (attempt + 1))
    raise last_exc


async def _judge_absolute(prompt: str) -> _AbsoluteVerdict:
    response = await _generate(prompt, _AbsoluteVerdict)
    verdict = response.parsed
    if verdict is None:
        return _AbsoluteVerdict(score=0, rationale=response.text or "no parseable verdict")
    return verdict


def _transcript(result: PersonaResult, up_to_session: int | None = None) -> str:
    traces = result.session_traces if up_to_session is None else result.session_traces[:up_to_session]
    lines = []
    for trace in traces:
        lines.append(f"--- {trace.label} ---")
        for turn in trace.turns:
            lines.append(f"[{turn.role}] {turn.text}")
    return "\n".join(lines)


async def judge_l1_memory_causality(result: PersonaResult) -> JudgeResult | None:
    """Pairwise: session 2's opening tutor reply (with real memory loaded)
    vs. the same opening line run against a fresh, unseeded, same-persona
    student with zero history. If a judge can't tell them apart, or prefers
    the no-memory version, memory isn't actually shaping output.

    The baseline (no-memory) reply is pre-computed in harness.py's
    run_persona_scenario, in the same agent-execution phase as everything
    else - not here. See PersonaResult.baseline_reply's docstring for why:
    running an agent turn and a raw genai call in the same async context
    broke the genai SDK's connector lifecycle, confirmed live three times
    with three different symptoms."""
    if len(result.session_traces) < 2 or result.baseline_reply is None:
        return None

    session_2 = result.session_traces[1]
    opening_line = next(t.text for t in session_2.turns if t.role == "student")
    with_memory_reply = next(t.text for t in session_2.turns if t.role == "tutor")

    prompt = f"""You are comparing two tutor responses to the SAME opening question.
Response A (with_memory) came from a tutor with access to this student's real
prior-session history. Response B (no_memory) came from a tutor talking to a
brand-new student asking the identical question, with zero history.

Student's opening question: {opening_line!r}

Response A (with_memory): {with_memory_reply!r}

Response B (no_memory): {result.baseline_reply!r}

Does Response A show clear evidence of actually using the student's prior
history (referencing a specific earlier topic, adjusting pace/depth based on
demonstrated mastery, not re-explaining something already covered) in a way
Response B could not, since B has no history to draw on? Pick "with_memory"
only if A shows concrete, specific evidence of this - not just a generally
more polished answer. Pick "tie" if A doesn't clearly demonstrate using memory.
Return JSON: {{"winner": "with_memory"|"no_memory"|"tie", "rationale": "..."}}"""

    response = await _generate(prompt, _PairwiseVerdict)
    verdict = response.parsed or _PairwiseVerdict(winner="tie", rationale=response.text or "unparseable")
    return JudgeResult(
        "L1", result.persona.student_id, score=None,
        passed=verdict.winner == "with_memory",
        rationale=verdict.rationale,
    )


async def judge_l2_personalization(result: PersonaResult) -> JudgeResult:
    persona = result.persona
    prompt = f"""Rate 1-5 how well the tutor adapted to this student's stated
traits across the WHOLE multi-session transcript below (1 = ignored the
traits entirely, 5 = consistently and specifically adapted to them).

Student traits: pace={persona.preferred_pace!r}, interests={persona.interests!r}

Full transcript across all sessions:
{_transcript(result)}

Look for: pace matching (terse vs. step-by-step), examples tied to stated
interests, and whether adaptation is consistent across sessions, not just
one turn. Return JSON: {{"score": 1-5, "rationale": "..."}}"""
    verdict = await _judge_absolute(prompt)
    return JudgeResult("L2", persona.student_id, score=verdict.score, passed=verdict.score >= 3, rationale=verdict.rationale)


async def judge_l3_citation_faithfulness(result: PersonaResult) -> JudgeResult:
    grounded_turns = []
    for trace in result.session_traces:
        for turn in trace.turns:
            for tc in turn.tool_calls:
                if tc.name == "search_grounding" and tc.result and tc.result.get("chunks"):
                    grounded_turns.append((turn.text, tc.result["chunks"]))
    if not grounded_turns:
        return JudgeResult("L3", result.persona.student_id, score=None, passed=False, rationale="no grounded turns found to check")

    excerpts = "\n\n".join(
        f"Tutor said: {text!r}\nRetrieved source text: {[c.get('text', '') for c in chunks]!r}"
        for text, chunks in grounded_turns
    )
    prompt = f"""For each pair below, does the tutor's statement stay faithful
to the retrieved source text (same facts, no invented numbers or claims
beyond what the source says)? Rate the WORST pair 1-5 (1 = clear
hallucination/distortion, 5 = fully faithful).

{excerpts}

Return JSON: {{"score": 1-5, "rationale": "..."}}"""
    verdict = await _judge_absolute(prompt)
    return JudgeResult("L3", result.persona.student_id, score=verdict.score, passed=verdict.score >= 3, rationale=verdict.rationale)


async def judge_l4_doubt_handling(result: PersonaResult) -> JudgeResult | None:
    has_doubts = any(t.post_close_teaching_memory.open_doubts for t in result.session_traces)
    if not has_doubts:
        return None
    prompt = f"""This student had a misconception surface during tutoring.
Given the full transcript below, was the misconception correctly identified
(not misdiagnosed), and if a re-check happened in a LATER session, was it a
genuine re-test (student re-derives/re-answers) rather than the tutor just
restating the correct answer for them? Rate 1-5.

{_transcript(result)}

Return JSON: {{"score": 1-5, "rationale": "..."}}"""
    verdict = await _judge_absolute(prompt)
    return JudgeResult("L4", result.persona.student_id, score=verdict.score, passed=verdict.score >= 3, rationale=verdict.rationale)


async def _safe(check_id: str, student_id: str, coro):
    """Isolates one judge call's failure from the rest of the run. Real
    agent execution (15+ sessions, dozens of successful model calls) takes
    many minutes; a single flaky genai call - confirmed live to fail
    intermittently and unpredictably in this environment, for reasons that
    resisted five full-run diagnostic attempts (sync/async client, same-
    process retry, structural phase separation, a fresh event loop, a
    genuinely separate subprocess, and backoff retry all still hit it at
    least once) - should never discard that work. Recorded as an explicit
    ERROR result, not silently dropped and not allowed to crash the run."""
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001 - a judge call failing is data (report it), not a reason to crash the eval
        return JudgeResult(check_id, student_id, score=None, passed=False, rationale=f"JUDGE CALL FAILED: {exc!r}")


async def run_all_judges(result: PersonaResult) -> list[JudgeResult]:
    student_id = result.persona.student_id
    judges: list[JudgeResult] = []
    if len(result.session_traces) >= 2 and result.baseline_reply is not None:
        l1 = await _safe("L1", student_id, judge_l1_memory_causality(result))
        if l1:
            judges.append(l1)
    await asyncio.sleep(3)  # space out back-to-back raw genai calls - see _generate's docstring
    judges.append(await _safe("L2", student_id, judge_l2_personalization(result)))
    await asyncio.sleep(3)
    judges.append(await _safe("L3", student_id, judge_l3_citation_faithfulness(result)))
    if any(t.post_close_teaching_memory.open_doubts for t in result.session_traces):
        await asyncio.sleep(3)
        l4 = await _safe("L4", student_id, judge_l4_doubt_handling(result))
        if l4:
            judges.append(l4)
    return judges
