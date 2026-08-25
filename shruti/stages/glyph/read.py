import json
from shruti.config import Models
from shruti.contracts.board import BoardContent

_READ_PROMPT = """You are reading a photograph of a {surface_kind} from a
{grade} {subject} lesson on "{chapter}".

CONTEXT (use to resolve ambiguous handwriting, never to invent content)
Teacher said during this board state: {transcript_excerpt}

CRITICAL - OCCLUSION
The second image is an occlusion mask. Shaded regions were never visible in
the source video because the teacher stood there the whole time.
For any region overlapping the shaded mask: emit kind="unreadable" with a
reason. DO NOT infer, complete, or guess occluded content.

TASK
Return the board as a JSON object {{"regions": [...]}} of layout regions
with normalized coordinates (0-1). Each region: id, bbox [x,y,w,h], kind
(equation|text|figure|table|diagram|unreadable), latex (preserve the
teacher's exact form), plain_text, description, role, step_index,
derives_from, confidence, reason (for unreadable).
"""


def read_board_state(client, board_image, unfilled_mask, context: dict) -> BoardContent:
    prompt = _READ_PROMPT.format(**context)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[prompt, board_image, unfilled_mask],
    )
    data = json.loads(response.text)
    return BoardContent(**data)
