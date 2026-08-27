import pytest

from testbed import demo_end_to_end, gcs_artifacts
from testbed.config import GCS_BUCKET, REDIS_HOST, REDIS_PORT


@pytest.mark.asyncio
async def test_full_sequence(firestore_db, gcs_bucket, redis_client):
    try:
        result = await demo_end_to_end.run_demo(
            session_id="test_e2e_session_1",
            student_id="test_e2e_student_1",
            firestore_db=firestore_db,
            gcs_bucket_name=GCS_BUCKET,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT,
        )
        assert any(c.chunk_id == "test_e2e_session_1_chunk_1" for c in result["grounding_chunks"])
        assert result["session_log"].turns[0].text == "What is projectile range?"
        assert result["dpm"].note == "asked about projectile range"
        assert result["artifact_text"] == "demo artifact for test_e2e_session_1"
    finally:
        firestore_db.collection("grounding_chunks").document("test_e2e_session_1_chunk_1").delete()
        firestore_db.collection("session_logs").document("test_e2e_session_1").delete()
        firestore_db.collection("dpm_profiles").document("test_e2e_student_1").delete()
        await gcs_artifacts.make_service(GCS_BUCKET).delete_artifact(
            app_name="memory_storage_testbed",
            user_id="test_e2e_student_1",
            session_id="test_e2e_session_1",
            filename="demo_artifact.txt",
        )
