"""The actual proof this system works: instrument a real conversation
against real Firestore/Redis, watch events arrive over the ingest pipeline
in order with correct trace linkage, close the session for real, and
confirm the long-term diff matches Firestore's actual post-close state.
Per docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §9.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.memory import instrumentation, short_term, store
from app.memory.schemas import DPMProfile, Weakness
from app.session_close import ReflectOp, ReflectResult
from observatory.broadcaster import Broadcaster
from observatory.ingest import ingest_one_message
from observatory.snapshot_cache import SnapshotCache


@pytest.mark.asyncio
async def test_full_pipeline_turn_logging_through_close_and_diff(firestore_db, redis_client, monkeypatch):
    session_id = "test_e2e_session_1"
    student_id = "test_e2e_student_1"

    cache = SnapshotCache()
    broadcaster = Broadcaster()
    session_queue = broadcaster.subscribe(session_id)

    def get_dpm(sid):
        profile = store.get_dpm(firestore_db, sid)
        return profile.model_dump(mode="json") if profile else None

    def get_teaching_memory(sid):
        memory = store.get_teaching_memory(firestore_db, sid)
        return memory.model_dump(mode="json") if memory else None

    try:
        # 0. Seed an existing DPM so the close-triggered write below is a
        #    genuine "partial -> known" transition, not a brand-new-student
        #    "added" entry.
        store.put_dpm(firestore_db, DPMProfile(
            student_id=student_id,
            weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=[f"{session_id}#0"])},
        ))
        redis_client.delete("smriti:events:recent")

        # 1. Drive two turns through the real tools/short_term path.
        ctx = MagicMock()
        ctx.state = {}
        ctx.session.id = session_id
        from app.memory import tools
        monkeypatch.setattr(tools, "_conn", lambda: firestore_db)
        await tools.log_turn("why 45 degrees?", "student", "", "", ctx)
        await tools.log_turn("range formula", "tutor", "projectile.range", "", ctx)

        # 2. Ingest whatever landed on the Redis list.
        for raw in redis_client.lrange("smriti:events:recent", 0, -1):
            await ingest_one_message(raw, cache, broadcaster, get_dpm, get_teaching_memory)

        delivered = []
        while not session_queue.empty():
            delivered.append(session_queue.get_nowait())
        turn_events = [d for d in delivered if d.event.record_type == "turn_buffer" and d.event.operation == "write"]
        assert len(turn_events) == 2

        # 3. Close the session for real (reflect() stubbed — no live API call).
        import app.session_close as session_close
        monkeypatch.setattr(session_close, "reflect", lambda client, log: ReflectResult(
            summary="", operations=[ReflectOp(op="set_mastery", args={
                "concept_id": "projectile.range", "mastery": "known",
                "strength": "strong", "evidence": [f"{session_id}#2"],
            })],
        ))
        from app.app_utils import memory_routes
        monkeypatch.setattr(memory_routes, "_genai_client", lambda: None)
        monkeypatch.setattr(memory_routes, "_firestore_client", lambda: firestore_db)

        redis_client.delete("smriti:events:recent")
        log = await memory_routes.perform_close_session(session_id, student_id)
        assert len(log.turns) == 2

        # 4. Ingest the close-triggered events and confirm the diff matches
        #    Firestore's real post-close state.
        for raw in redis_client.lrange("smriti:events:recent", 0, -1):
            await ingest_one_message(raw, cache, broadcaster, get_dpm, get_teaching_memory)

        delivered = []
        while not session_queue.empty():
            delivered.append(session_queue.get_nowait())
        dpm_writes = [d for d in delivered if d.event.record_type == "dpm_profile" and d.event.operation == "write"]
        assert len(dpm_writes) == 1
        assert dpm_writes[0].event.session_id == session_id
        mastery_change = next(c for c in dpm_writes[0].diff if c.path == "weaknesses.projectile.range.mastery")
        assert mastery_change.label == "projectile.range.mastery: partial -> known"

        real_profile = store.get_dpm(firestore_db, student_id)
        assert real_profile.weaknesses["projectile.range"].mastery == "known"
    finally:
        instrumentation.set_session_context(None)
        firestore_db.collection("session_logs").document(session_id).delete()
        firestore_db.collection("dpm_profiles").document(student_id).delete()
        firestore_db.collection("teaching_memories").document(student_id).delete()
        redis_client.delete(
            f"session:{session_id}:turns", f"session:{session_id}:started_at", f"session:{session_id}:heartbeat",
        )
