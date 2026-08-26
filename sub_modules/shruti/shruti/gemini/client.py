import json


async def extract(client, prompt: str, schema: dict, parts: list, model: str,
                    cached_content: str | None = None) -> dict:
    """Constrained decoding. The paper measured relation-extraction F1 collapsing
    76% -> 18% without format enforcement — schema is load-bearing, not decoration."""
    config = {"response_mime_type": "application/json", "response_schema": schema}
    if cached_content:
        config["cached_content"] = cached_content
    response = await client.models.generate_content(
        model=model, contents=[*parts, prompt], config=config,
    )
    return json.loads(response.text)


class CostTracker:
    def __init__(self):
        self._spend: dict[str, float] = {}

    def record(self, invocation_id: str, cost_usd: float) -> None:
        self._spend[invocation_id] = self._spend.get(invocation_id, 0.0) + cost_usd

    def total_for(self, invocation_id: str) -> float:
        return self._spend.get(invocation_id, 0.0)
