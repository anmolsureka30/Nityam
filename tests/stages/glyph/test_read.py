import json
from shruti.stages.glyph.read import read_board_state


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.last_contents = None

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            self._outer.last_contents = contents
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_read_board_state_parses_regions():
    payload = {"regions": [
        {"id": "r1", "bbox": [0.05, 0.1, 0.4, 0.2], "kind": "equation",
         "latex": "x^2 + 6x + 5", "role": "problem_statement", "confidence": 0.94},
        {"id": "r2", "bbox": [0.5, 0.6, 0.3, 0.1], "kind": "unreadable",
         "reason": "occluded throughout state"},
    ]}
    client = FakeClient(payload)
    content = read_board_state(
        client, board_image=b"fake-image", unfilled_mask=b"fake-mask",
        context={"surface_kind": "blackboard", "grade": 9, "subject": "math",
                 "chapter": "completing the square", "transcript_excerpt": "..."},
    )
    assert len(content.regions) == 2
    assert content.regions[0].latex == "x^2 + 6x + 5"
    assert content.regions[1].kind == "unreadable"
    assert content.regions[1].reason == "occluded throughout state"


def test_read_board_state_prompt_includes_no_guess_instruction():
    client = FakeClient({"regions": []})
    read_board_state(client, board_image=b"img", unfilled_mask=b"mask",
                      context={"surface_kind": "blackboard", "grade": 9, "subject": "math",
                               "chapter": "x", "transcript_excerpt": "y"})
    prompt = client.last_contents[0]
    assert "DO NOT" in prompt.upper() or "do not" in prompt
    assert "unreadable" in prompt
    # Regression guard: verify the mask actually reaches the model
    assert client.last_contents[1] == b"img"
    assert client.last_contents[2] == b"mask"
