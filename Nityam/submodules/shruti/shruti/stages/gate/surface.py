from shruti.contracts.recording import SurfaceKind
from shruti.config import Models

_PROMPT = (
    "Classify the writing surface visible in these lecture frames as exactly "
    "one of: blackboard, whiteboard, slides, mixed, talking_head. "
    "Reply with only that one word."
)


def classify_surface(client, frames: list) -> SurfaceKind:
    response = client.models.generate_content(
        model=Models().router,
        contents=[_PROMPT, *frames],
    )
    label = response.text.strip().lower()
    try:
        return SurfaceKind(label)
    except ValueError as e:
        raise ValueError(f"classify_surface: model returned unrecognized label {label!r}") from e
