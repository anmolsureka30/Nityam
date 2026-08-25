import pytest
from shruti.agents.plugins import ProvenancePlugin, CostGuardPlugin
from shruti.gemini.client import CostTracker


class FakeCallbackContext:
    def __init__(self, agent_name="Glyph", invocation_id="inv1"):
        self.agent_name = agent_name
        self.invocation_id = invocation_id


class FakeLlmResponse:
    def __init__(self, model_version="gemini-3.5-flash", id="resp1"):
        self.model_version = model_version
        self.id = id


@pytest.mark.asyncio
async def test_provenance_plugin_records_every_model_call():
    recorded = []

    async def recorder(**kwargs):
        recorded.append(kwargs)

    plugin = ProvenancePlugin(recorder)
    await plugin.after_model_callback(callback_context=FakeCallbackContext(),
                                       llm_response=FakeLlmResponse())
    assert recorded[0]["stage"] == "Glyph"
    assert recorded[0]["model"] == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_cost_guard_allows_calls_under_budget():
    tracker = CostTracker()
    tracker.record("inv1", 0.50)
    plugin = CostGuardPlugin(tracker, max_cost_per_recording_usd=2.00)
    result = await plugin.before_model_callback(callback_context=FakeCallbackContext(), llm_request=None)
    assert result is None


@pytest.mark.asyncio
async def test_cost_guard_blocks_calls_over_budget():
    tracker = CostTracker()
    tracker.record("inv1", 2.50)
    plugin = CostGuardPlugin(tracker, max_cost_per_recording_usd=2.00)
    result = await plugin.before_model_callback(callback_context=FakeCallbackContext(), llm_request=None)
    assert result is not None
    assert result.error_code == "cost_ceiling_exceeded"
