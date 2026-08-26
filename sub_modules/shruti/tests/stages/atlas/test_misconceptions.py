import json
from shruti.stages.atlas.misconceptions import mine_misconceptions
from shruti.contracts.beat import Beat


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_mine_misconceptions_preserves_teacher_phrasing():
    payload = [{"concept_id": "completing_the_square",
                "statement": "treats (a+b)^2 as a^2+b^2",
                "teacher_phrasing": "yeh sabse common galti hai",
                "correct_understanding": "(a+b)^2 = a^2 + 2ab + b^2",
                "pre_empted_at_beat": "b1"}]
    client = FakeClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="explain", transcript="yeh sabse common galti hai...")]
    misconceptions = mine_misconceptions(client, beats)
    assert misconceptions[0].teacher_phrasing == "yeh sabse common galti hai"
    assert misconceptions[0].pre_empted_at_beat == "b1"
