import json
import pytest
from shruti.gemini.client import extract, CostTracker


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.last_config = None

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        async def generate_content(self, model, contents, config=None):
            self._outer.last_config = config
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


@pytest.mark.asyncio
async def test_extract_parses_json_and_sets_schema_config():
    client = FakeClient({"regions": []})
    result = await extract(client, prompt="read this", schema={"type": "object"},
                            parts=[b"img"], model="gemini-3.5-flash")
    assert result == {"regions": []}
    assert client.last_config["response_schema"] == {"type": "object"}
    assert client.last_config["response_mime_type"] == "application/json"


def test_cost_tracker_accumulates_per_invocation():
    tracker = CostTracker()
    tracker.record("inv1", 0.10)
    tracker.record("inv1", 0.05)
    tracker.record("inv2", 1.00)
    assert tracker.total_for("inv1") == pytest.approx(0.15)
    assert tracker.total_for("inv2") == pytest.approx(1.00)
    assert tracker.total_for("unknown") == 0.0
