from shruti.config import Models

_VALID_INTENTS = {"definition", "explanation", "prerequisite", "why_stuck",
                   "learning_path", "show_me_where", "what_did_sir_say",
                   "what_was_on_board", "other"}

_PROMPT = """Classify this student question into exactly one label: definition,
explanation, prerequisite, why_stuck, learning_path, show_me_where,
what_did_sir_say, what_was_on_board, other.

Question: {query}
Reply with only the label.
"""


def classify_intent(client, query: str) -> str:
    response = client.models.generate_content(
        model=Models().router,
        contents=[_PROMPT.format(query=query)],
    )
    label = response.text.strip().lower()
    return label if label in _VALID_INTENTS else "other"
