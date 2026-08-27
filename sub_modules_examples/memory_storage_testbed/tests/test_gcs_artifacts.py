import pytest

from testbed import gcs_artifacts
from testbed.config import GCS_BUCKET


@pytest.mark.asyncio
async def test_artifact_roundtrip(gcs_bucket):
    service = gcs_artifacts.make_service(GCS_BUCKET)
    try:
        await gcs_artifacts.save_text_artifact(
            service,
            app_name="memory_storage_testbed",
            user_id="test_user_1",
            session_id="test_session_1",
            filename="test_artifact.txt",
            text="hello from the testbed",
        )
        text = await gcs_artifacts.load_text_artifact(
            service,
            app_name="memory_storage_testbed",
            user_id="test_user_1",
            session_id="test_session_1",
            filename="test_artifact.txt",
        )
        assert text == "hello from the testbed"
    finally:
        await service.delete_artifact(
            app_name="memory_storage_testbed",
            user_id="test_user_1",
            session_id="test_session_1",
            filename="test_artifact.txt",
        )
