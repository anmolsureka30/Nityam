"""Read-only memory endpoints on backend/'s own FastAPI server — the same
shape as sub_modules_examples/tutor/app/app_utils/memory_routes.py's two
GET routes, so smriti-observatory/backend can proxy to either agent server
identically (see docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md).

No POST /close endpoint here: unlike the tutor scaffold, backend/'s own
_flush_session_memory (app/main.py) already calls the real close_session on
every WebSocket teardown -- there's no missing trigger to add.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from types import SimpleNamespace

import redis as redis_sync
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app import config, seeding, user_auth
from app.memory import short_term, store

log = logging.getLogger("nityam.memory_routes")

router = APIRouter(prefix="/memory")


@functools.cache
def _firestore_client():
    return store.connect()


@router.get("/sessions/{session_id}/state")
async def session_state_endpoint(session_id: str, student_id: str):
    db = _firestore_client()
    profile = store.get_dpm(db, student_id)
    memory = store.get_teaching_memory(db, student_id)
    session_log = store.get_session_log(db, session_id)
    turn_buffer = await short_term.get_turn_buffer(session_id, student_id)
    return {
        "session_id": session_id,
        "student_id": student_id,
        "workflow": {"turn_buffer": turn_buffer},
        "episodic": {"session_log": session_log.model_dump(mode="json") if session_log else None},
        "long_term": {
            "dpm_profile": profile.model_dump(mode="json") if profile else None,
            "teaching_memory": memory.model_dump(mode="json") if memory else None,
        },
    }


@router.get("/current-topic")
async def current_topic_endpoint(student_id: str):
    """Whatever THIS student's next session will open on -- the same record
    app/sessions.py._new_board() reads for them, so the dashboard's "revise
    today's class" card can never promise a topic the tutor doesn't actually
    open on. `null` means this student hasn't run a Shruti ingest yet;
    callers should fall back to their own static default (matches
    sessions.py's own fallback to NITYAM_TOPIC_* env vars). Per-student, not
    global -- one person's upload must never change what somebody else's
    session opens on."""
    topic = store.get_current_topic(_firestore_client(), student_id)
    return topic.model_dump(mode="json") if topic else None


@router.get("/topics")
async def topic_history_endpoint(student_id: str):
    """Every video this student has ever uploaded, newest first — the
    dashboard's "study this instead" picker. Read-only, like current-topic
    above; selecting one goes through the authenticated POST below."""
    topics = store.list_topic_history(_firestore_client(), student_id)
    return {"topics": [t.model_dump(mode="json") for t in topics]}


class SelectTopicRequest(BaseModel):
    recording_slug: str


@router.post("/students/{student_id}/current-topic")
async def select_topic_endpoint(
    student_id: str, req: SelectTopicRequest, authorization: str = Header(default=""),
):
    """Pick which of this student's own past uploads their next session
    opens on. Authenticated exactly like /reset and /ensure: a path
    parameter is not proof of anything, so the caller's Firebase token must
    itself belong to `student_id`, or any signed-in user could redirect
    someone else's next session."""
    claims = await _caller(authorization)
    if claims.get("uid") != student_id:
        raise HTTPException(status_code=403, detail="you can only change your own topic")

    db = _firestore_client()
    match = next(
        (t for t in store.list_topic_history(db, student_id)
         if t.recording_slug == req.recording_slug),
        None,
    )
    if match is None:
        raise HTTPException(status_code=404, detail="no upload with that recording_slug")

    store.put_current_topic(db, match)
    return match.model_dump(mode="json")


def _read_recent_events(session_id: str) -> list[dict]:
    """The raw JSON dicts of every event for this session, memory AND tool-call
    alike — smriti:events:recent holds both kinds on one list (see
    app/memory/instrumentation.py's publish_tool_call_event and
    smriti-observatory/backend/observatory/ingest.py's own kind-based
    dispatch). Returned as plain dicts rather than parsed MemoryEvent objects:
    a ToolCallEvent dict has no source_fn/record_type, so
    MemoryEvent.model_validate_json() raised on it as soon as any tool call
    had ever fired — confirmed live in production before this fix, and
    silently masked here by the caller's own try/except (see routes_rest.py's
    session_events, which degrades to {"events": []} on any exception)."""
    try:
        client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
        raw_events = client.lrange("smriti:events:recent", 0, -1)
    except Exception:
        log.exception("_read_recent_events: failed to read smriti:events:recent from Redis")
        return []
    events = []
    for raw in raw_events:
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if parsed.get("session_id") == session_id:
            events.append(parsed)
    return events


@router.get("/sessions/{session_id}/events")
async def session_events_endpoint(session_id: str, student_id: str, trace_id: str | None = None):
    events = _read_recent_events(session_id)
    if trace_id:
        events = [e for e in events if e.get("trace_id") == trace_id]
    return {"events": events}


# ─────────────────────────────────────────────── what the student can see
#
# Everything below exists so the memory layer is VISIBLE. A tutor that claims
# to remember you is not believable from prose; it is believable when you can
# open the session you had on Tuesday and see `misconceived -> partial` against
# a concept, next to the sentence that moved it.


def _mastery_map(profile) -> dict[str, dict]:
    if profile is None:
        return {}
    return {
        cid: {"mastery": w.mastery, "strength": w.strength,
              "evidence": list(w.evidence)}
        for cid, w in profile.weaknesses.items()
    }


def _doubt_map(memory) -> dict[str, dict]:
    if memory is None:
        return {}
    return {
        d.concept_id: {"doubt": d.doubt, "status": d.status,
                       "correct_understanding": d.correct_understanding}
        for d in memory.open_doubts
    }


def _changes(before, after, before_tm, after_tm) -> list[dict]:
    """What actually moved, as a flat list the UI can render without thinking.

    Computed here rather than in the browser because "what changed" is a
    property of the memory model, and two clients disagreeing about it would
    be worse than one place being wrong.
    """
    was, now = _mastery_map(before), _mastery_map(after)
    out: list[dict] = []
    for cid in sorted(set(was) | set(now)):
        a, b = was.get(cid), now.get(cid)
        if a == b:
            continue
        out.append({
            "kind": "mastery", "concept_id": cid,
            "from": a["mastery"] if a else None,
            "to": b["mastery"] if b else None,
            "strength": b["strength"] if b else None,
        })

    was_d, now_d = _doubt_map(before_tm), _doubt_map(after_tm)
    for cid in sorted(set(was_d) | set(now_d)):
        a, b = was_d.get(cid), now_d.get(cid)
        before_status = a["status"] if a else None
        after_status = b["status"] if b else "removed"
        # Only a change of STATE counts. Comparing the whole doubt meant a
        # reworded one — the tutor sharpening how it describes the same
        # misconception — rendered as "active -> active", an arrow pointing at
        # itself. That is noise on a screen whose entire job is showing what
        # actually moved.
        if before_status == after_status:
            continue
        out.append({
            "kind": "doubt", "concept_id": cid,
            "from": before_status,
            "to": after_status,
            "doubt": (b or a or {}).get("doubt", ""),
        })
    return out


@router.get("/students/{student_id}/sessions")
async def list_sessions_endpoint(student_id: str):
    """Every session this student has had — the dashboard's list."""
    conn = _firestore_client()
    logs = store.list_session_logs(conn, student_id)
    return {
        "sessions": [
            {
                "session_id": entry.session_id,
                "topic": entry.topic,
                "mode": entry.mode,
                "started_at": entry.started_at,
                "ended_at": entry.ended_at,
                "summary": entry.summary,
                "turns": len(entry.turns),
                # So the list can show "3 things changed" without shipping
                # every snapshot to render a row.
                "changed": len(_changes(entry.dpm_before, entry.dpm_after,
                                        entry.teaching_before,
                                        entry.teaching_after)),
                # Sessions that closed before recaps existed have no snapshots
                # and the UI should say so rather than render an empty diff.
                "has_recap": entry.dpm_after is not None,
            }
            for entry in logs
        ]
    }


@router.get("/students/{student_id}/sessions/{session_id}")
async def session_recap_endpoint(student_id: str, session_id: str):
    """One session in full: what was said, what changed, and what Reflect
    proposed — including the operations that were rejected."""
    conn = _firestore_client()
    entry = store.get_session_log(conn, session_id)
    if entry is None or entry.student_id != student_id:
        return {"found": False}
    return {
        "found": True,
        "session_id": entry.session_id,
        "topic": entry.topic,
        "mode": entry.mode,
        "started_at": entry.started_at,
        "ended_at": entry.ended_at,
        "summary": entry.summary,
        "turns": [t.model_dump(mode="json") for t in entry.turns],
        "board": entry.board,
        "has_recap": entry.dpm_after is not None,
        "before": {
            "mastery": _mastery_map(entry.dpm_before),
            "doubts": _doubt_map(entry.teaching_before),
        },
        "after": {
            "mastery": _mastery_map(entry.dpm_after),
            "doubts": _doubt_map(entry.teaching_after),
        },
        "changes": _changes(entry.dpm_before, entry.dpm_after,
                            entry.teaching_before, entry.teaching_after),
        "operations": entry.operations,
    }


@router.get("/students/{student_id}/briefing")
async def briefing_preview_endpoint(
    student_id: str, concept: str = "", conceptName: str = "", mode: str = "revision"
):
    """What this session is about to cover, for the overlay shown while the
    Live model connects.

    Same source as the tutor's own briefing — `briefing.resolve_concepts` and
    the real record — so the overlay cannot promise something she was never
    told. It is deliberately NOT the brief text itself: that is written for a
    model, in square brackets, and reads like stage directions.
    """
    from app import briefing as briefing_mod

    conn, dpm, memory = briefing_mod.load_record(student_id)
    plan = SimpleNamespace(concept=concept, concept_name=conceptName, mode=mode)
    concept_ids = briefing_mod.resolve_concepts(plan, conn, dpm, memory)

    weak = []
    if dpm is not None:
        order = {"misconceived": 0, "unknown": 1, "partial": 2,
                 "known": 3, "durable": 4}
        for cid, w in sorted(dpm.weaknesses.items(),
                             key=lambda kv: order.get(kv[1].mastery, 9)):
            if w.mastery in ("misconceived", "unknown", "partial"):
                weak.append({"concept_id": cid, "mastery": w.mastery})

    doubts = []
    if memory is not None:
        doubts = [
            {"concept_id": d.concept_id, "doubt": d.doubt}
            for d in memory.open_doubts if d.status != "resolved"
        ]

    last = ""
    if conn is not None and store.latest_session_log is not None:
        try:
            previous = store.latest_session_log(conn, student_id, with_summary=True)
            last = (previous.summary or "").strip() if previous else ""
        except Exception:  # noqa: BLE001 - an overlay must never block a lesson
            last = ""

    # The steps shown across the top of the session screen. They were three
    # hardcoded strings — "Find why 45° wins", "Say why", "Two throws, one
    # spot" — so every session claimed the same three regardless of what it
    # was about. Derived from the same record the tutor is briefed on, so the
    # header cannot promise a shape the lesson does not have.
    #
    # Weakest first, because that is the order she teaches in, and the topic
    # itself last: the thing the session is FOR is the thing it ends on.
    # Weakest first, because that is the order she teaches in, and the topic
    # last: the thing the session is FOR is the thing it ends on.
    #
    # A student can legitimately have no weak points — one good session moves
    # everything to known, which really happened here — so fall back to the
    # concepts this topic actually resolves to, minus the ones already
    # covered. A one-step plan is not a plan.
    plan = [w["concept_id"] for w in weak[:2]]
    if len(plan) < 2:
        already = {c for c, v in (memory.covered if memory else {}).items()
                   if v.status == "covered"}
        for cid in concept_ids:
            if len(plan) >= 2:
                break
            if cid not in plan and cid not in already:
                plan.append(cid)
    topic_label = conceptName or concept
    if topic_label:
        plan.append(topic_label)

    return {
        "topic": conceptName or concept,
        "mode": mode,
        "plan": plan[:3],
        "concepts": concept_ids[:6],
        "weak_points": weak[:4],
        "open_doubts": doubts[:3],
        "last_session": last,
        "covered": sorted(
            c for c, v in (memory.covered if memory else {}).items()
            if v.status == "covered"
        )[:6],
    }


async def _caller(authorization: str) -> dict:
    """The verified claims of whoever is calling, or a 401.

    Both write endpoints below need this and neither may trust a path
    parameter: a uid is visible in a URL, so without checking the token
    against it any signed-in user could seed or erase anyone else's record.
    Verification is app/user_auth's — Google's public certificates, no ADC.
    """
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="sign in first")
    try:
        return await asyncio.to_thread(user_auth.verify_token, token)
    except Exception as exc:  # noqa: BLE001
        log.warning("refusing a write: %s: %s", exc.__class__.__name__, exc)
        raise HTTPException(status_code=401, detail="your sign-in has expired") from None


@router.post("/students/{student_id}/ensure")
async def ensure_student_endpoint(
    student_id: str, authorization: str = Header(default=""),
):
    """Give a student the starting record if they have never had one.

    Called by the browser the moment somebody signs in, so a new account has a
    profile and a session history BEFORE they look at either. The equivalent
    check on the WebSocket runs too, but that is too late for the thing it is
    for: a judge signs in, lands on the dashboard, and sees an empty profile
    and an empty session list — which is precisely the impression this record
    exists to prevent — and only discovers otherwise if they happen to start a
    session first.

    Authenticated exactly like /reset, and idempotent: an existing student is
    left completely alone, so this is safe to call on every sign-in.
    """
    claims = await _caller(authorization)
    if claims.get("uid") != student_id:
        raise HTTPException(status_code=403, detail="you can only seed your own account")

    if not config.SEED_NEW_STUDENTS:
        return {"ok": True, "seeded": False, "reason": "seeding is switched off"}

    conn = _firestore_client()
    if await asyncio.to_thread(seeding.has_record, conn, student_id):
        return {"ok": True, "seeded": False, "reason": "already has a record"}

    outcome = await asyncio.to_thread(seeding.reset, conn, student_id)
    log.info("seeded new student %s on sign-in: %s", student_id, outcome)
    return {"ok": True, "seeded": True, **outcome}


@router.post("/students/{student_id}/reset")
async def reset_student_endpoint(
    student_id: str, authorization: str = Header(default=""),
):
    """Wipe this student's memory and lay the demo starting record back down.

    THE ONLY DESTRUCTIVE ENDPOINT IN THIS FILE, and the only one that
    authenticates. Everything else here is a read, and reads were left open
    because the Observatory proxies them. This one deletes a student's entire
    history, so it verifies the caller's Firebase ID token and refuses unless
    the token's uid IS the student being reset — a path parameter is not proof
    of anything, and without this check any signed-in user could erase anyone
    else's record by guessing a uid.

    Verification goes through the same app/user_auth path the WebSocket uses:
    Google's public certificates, no ADC, no privileged credential.
    """
    claims = await _caller(authorization)
    if claims.get("uid") != student_id:
        log.warning("reset refused: %r tried to reset %r", claims.get("uid"), student_id)
        raise HTTPException(status_code=403, detail="you can only reset your own account")

    outcome = await asyncio.to_thread(seeding.reset, _firestore_client(), student_id)
    log.info("reset %s: %s", student_id, outcome)
    return {"ok": True, **outcome}
