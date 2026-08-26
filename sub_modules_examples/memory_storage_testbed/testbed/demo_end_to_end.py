from __future__ import annotations

import random

from google.cloud import firestore as firestore_module

from testbed import firestore_store, gcs_artifacts, redis_shortterm
from testbed.schemas import Chunk, Profile, SessionLog, Turn


def _dummy_embedding(seed: int, dim: int = 1536) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(dim)]


async def run_demo(
    session_id: str,
    student_id: str,
    firestore_db: firestore_module.Client,
    gcs_bucket_name: str,
    redis_host: str,
    redis_port: int,
) -> dict:
    # 0. Seed a grounding chunk and retrieve it, simulating TutorAgent's search_grounding
    #    call before it answers the student's question.
    chunk_id = f"{session_id}_chunk_1"
    firestore_store.put_chunk(
        firestore_db,
        Chunk(chunk_id=chunk_id, concept_ids=["kinematics.projectile_range"], text="Range = u^2 sin(2 theta) / g"),
        _dummy_embedding(seed=7),
    )
    grounding_chunks = firestore_store.search_chunks(firestore_db, ["kinematics.projectile_range"])

    # 1. Live turns land in Redis, exactly like log_turn's write-through would.
    await redis_shortterm.clear_session(session_id, redis_host, redis_port)
    await redis_shortterm.append_turn(
        session_id, {"turn": 1, "role": "student", "text": "What is projectile range?"}, redis_host, redis_port
    )
    await redis_shortterm.append_turn(
        session_id, {"turn": 2, "role": "tutor", "text": "Range = u^2 sin(2 theta) / g."}, redis_host, redis_port
    )

    # 2. close_session reads the buffer back and builds the durable session_log.
    buffer = await redis_shortterm.get_turn_buffer(session_id, redis_host, redis_port)
    log = SessionLog(
        session_id=session_id,
        student_id=student_id,
        turns=[Turn(**t) for t in buffer],
    )
    firestore_store.put_session_log(firestore_db, log)

    # 3. The Reflect-equivalent step updates the student's long-term profile.
    profile = Profile(student_id=student_id, note="asked about projectile range")
    firestore_store.put_dpm(firestore_db, profile)

    # 4. ArtifactAgent's output gets saved to GCS.
    artifact_service = gcs_artifacts.make_service(gcs_bucket_name)
    artifact_text = f"demo artifact for {session_id}"
    await gcs_artifacts.save_text_artifact(
        artifact_service,
        app_name="memory_storage_testbed",
        user_id=student_id,
        session_id=session_id,
        filename="demo_artifact.txt",
        text=artifact_text,
    )

    # 5. Read everything back, proving the round trip end to end.
    read_back_log = firestore_store.get_session_log(firestore_db, session_id)
    read_back_dpm = firestore_store.get_dpm(firestore_db, student_id)
    read_back_artifact = await gcs_artifacts.load_text_artifact(
        artifact_service,
        app_name="memory_storage_testbed",
        user_id=student_id,
        session_id=session_id,
        filename="demo_artifact.txt",
    )

    await redis_shortterm.clear_session(session_id, redis_host, redis_port)

    return {
        "grounding_chunks": grounding_chunks,
        "session_log": read_back_log,
        "dpm": read_back_dpm,
        "artifact_text": read_back_artifact,
    }


if __name__ == "__main__":
    import asyncio

    from testbed import firestore_store as _fs
    from testbed.config import FIRESTORE_DATABASE, GCS_BUCKET, PROJECT_ID, REDIS_HOST, REDIS_PORT

    async def _main() -> None:
        db = _fs.connect(PROJECT_ID, FIRESTORE_DATABASE)
        result = await run_demo(
            session_id="manual_demo_session",
            student_id="manual_demo_student",
            firestore_db=db,
            gcs_bucket_name=GCS_BUCKET,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT,
        )
        print("session_log:", result["session_log"].model_dump_json(indent=2))
        print("dpm:", result["dpm"].model_dump_json(indent=2))
        print("artifact_text:", result["artifact_text"])

    asyncio.run(_main())
