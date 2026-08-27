from __future__ import annotations

from google.adk.artifacts import GcsArtifactService
from google.genai.types import Blob, Part


def make_service(bucket_name: str) -> GcsArtifactService:
    return GcsArtifactService(bucket_name=bucket_name)


async def save_text_artifact(
    service: GcsArtifactService,
    app_name: str,
    user_id: str,
    session_id: str,
    filename: str,
    text: str,
) -> int:
    part = Part(inline_data=Blob(mime_type="text/plain", data=text.encode("utf-8")))
    return await service.save_artifact(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        artifact=part,
    )


async def load_text_artifact(
    service: GcsArtifactService,
    app_name: str,
    user_id: str,
    session_id: str,
    filename: str,
) -> str:
    part = await service.load_artifact(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
    )
    if part is None or part.inline_data is None:
        raise ValueError(f"No artifact found for {filename!r}")
    return part.inline_data.data.decode("utf-8")
