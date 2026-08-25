import asyncio
import json


async def submit_batch(client, requests: list[dict], model: str) -> str:
    jsonl = "\n".join(json.dumps(r) for r in requests)
    upload = await client.files.upload(jsonl, mime_type="application/jsonl")
    job = await client.batches.create(model=model, src=upload.name)
    return job.name


async def poll_batch(client, job_name: str, poll_interval_s: float = 20.0) -> str:
    while True:
        job = await client.batches.get(job_name)
        if job.state not in ("PENDING", "RUNNING"):
            return job.state
        await asyncio.sleep(poll_interval_s)


async def collect_batch(client, job_name: str) -> list[dict]:
    job = await client.batches.get(job_name)
    return await client.batches.collect(job)
