from shruti.lens.route import classify_intent


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, label):
        self._label = label

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(self._outer._label)

    @property
    def models(self):
        return FakeClient._Models(self)


def test_classify_intent_recognizes_known_label():
    assert classify_intent(FakeClient("prerequisite"), "what do I need before this?") == "prerequisite"


def test_classify_intent_defaults_to_other_for_unknown_label():
    assert classify_intent(FakeClient("gibberish-label"), "asdf") == "other"
