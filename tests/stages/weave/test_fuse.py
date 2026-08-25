import json
from shruti.stages.weave.fuse import fuse_beats
from shruti.contracts.speech import Utterance


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


def test_fuse_beats_labels_kind_and_salience():
    payload = [{"idx": 0, "start_s": 0.0, "end_s": 8.0, "kind": "explain", "salience": 0.7}]
    client = FakeClient(payload)
    utterances = [Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=8.0,
                             text="so today we look at derivatives", speaker="TEACHER")]
    beats = fuse_beats(client, recording_id="r1", boundaries=[0.0, 8.0],
                        utterances=utterances, board_states=[], deixis=[])
    assert len(beats) == 1
    assert beats[0].kind == "explain"
    assert beats[0].salience == 0.7
    assert "derivatives" in beats[0].transcript
