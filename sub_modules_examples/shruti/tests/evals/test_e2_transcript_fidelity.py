from evals.e2_transcript_fidelity import word_error_rate, script_fidelity


def test_word_error_rate_zero_for_identical_transcripts():
    assert word_error_rate("hello world", "hello world") == 0.0


def test_word_error_rate_counts_substitutions():
    assert word_error_rate("hello there", "hello world") == 0.5


def test_script_fidelity_penalizes_transliteration():
    reference = "अब हम iska derivative nikalenge"
    faithful = "अब हम iska derivative nikalenge"
    transliterated = "अब हम इसका डेरिवेटिव निकालेंगे"
    assert script_fidelity(faithful, reference) == 1.0
    assert script_fidelity(transliterated, reference) < 1.0
