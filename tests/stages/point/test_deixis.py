import json
import numpy as np
from shruti.stages.point.deixis import resolve_deixis
from shruti.contracts.speech import Utterance

_FAKE_FRAME = np.zeros((4, 4, 3), dtype=np.uint8)


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


def test_resolve_deixis_parses_pointed_region():
    payload = {"found": True, "phrase": "yeh term", "board_region": [0.3, 0.4, 0.1, 0.1],
               "kind": "point", "confidence": 0.81}
    client = FakeClient(payload)
    utterance = Utterance(id="u1", recording_id="r1", start_s=10.0, end_s=12.0,
                           text="ab yeh term yahan cancel ho jayega", speaker="TEACHER")
    deixis = resolve_deixis(client, clip_frames=[_FAKE_FRAME], utterance=utterance)
    assert deixis is not None
    assert deixis.phrase == "yeh term"
    assert deixis.board_region == (0.3, 0.4, 0.1, 0.1)
    assert deixis.utterance_id == "u1"


def test_resolve_deixis_returns_none_when_no_gesture_found():
    client = FakeClient({"found": False})
    utterance = Utterance(id="u2", recording_id="r1", start_s=0.0, end_s=1.0,
                           text="so today we begin", speaker="TEACHER")
    assert resolve_deixis(client, clip_frames=[_FAKE_FRAME], utterance=utterance) is None
