import pytest
from shruti.gemini.batch import submit_batch, poll_batch, collect_batch


class FakeUpload:
    name = "files/abc"


class FakeJob:
    def __init__(self, name, state):
        self.name = name
        self.state = state


class FakeFilesApi:
    async def upload(self, jsonl, mime_type):
        return FakeUpload()


class FakeBatchesApi:
    def __init__(self, states):
        self._states = list(states)
        self._job_name = "batches/1"

    async def create(self, model, src):
        return FakeJob(self._job_name, self._states[0])

    async def get(self, job_name):
        state = self._states.pop(0) if len(self._states) > 1 else self._states[0]
        return FakeJob(job_name, state)

    async def collect(self, job):
        return [{"result": "ok"}]


class FakeClient:
    def __init__(self, states):
        self.files = FakeFilesApi()
        self.batches = FakeBatchesApi(states)


@pytest.mark.asyncio
async def test_submit_batch_returns_job_name():
    client = FakeClient(states=["SUCCEEDED"])
    job_name = await submit_batch(client, requests=[{"a": 1}], model="gemini-3.5-flash")
    assert job_name == "batches/1"


@pytest.mark.asyncio
async def test_poll_batch_waits_through_pending_then_returns_final_state():
    client = FakeClient(states=["PENDING", "RUNNING", "SUCCEEDED"])
    state = await poll_batch(client, job_name="batches/1", poll_interval_s=0.01)
    assert state == "SUCCEEDED"


@pytest.mark.asyncio
async def test_collect_batch_returns_results():
    client = FakeClient(states=["SUCCEEDED"])
    results = await collect_batch(client, job_name="batches/1")
    assert results == [{"result": "ok"}]
