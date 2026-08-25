from google.adk.plugins import BasePlugin
from shruti.config import Budget


class ProvenancePlugin(BasePlugin):
    """Every LLM call that produces a semantic object records its inputs —
    reproducibility is not optional in an education knowledge base."""

    def __init__(self, recorder):
        super().__init__(name="provenance")
        self._recorder = recorder

    async def after_model_callback(self, *, callback_context, llm_response):
        await self._recorder(
            stage=callback_context.agent_name,
            model=getattr(llm_response, "model_version", None),
            output_ref=getattr(llm_response, "id", None),
        )
        return None


class CostGuardPlugin(BasePlugin):
    """Hard ceiling per recording — the budget is finite."""

    def __init__(self, cost_tracker, max_cost_per_recording_usd: float | None = None):
        super().__init__(name="cost_guard")
        self._cost_tracker = cost_tracker
        self._max_cost = max_cost_per_recording_usd or Budget().max_cost_per_recording_usd

    async def before_model_callback(self, *, callback_context, llm_request):
        spent = self._cost_tracker.total_for(callback_context.invocation_id)
        if spent > self._max_cost:
            from google.adk.models import LlmResponse
            return LlmResponse(error_code="cost_ceiling_exceeded")
        return None
