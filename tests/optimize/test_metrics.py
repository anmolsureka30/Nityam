from shruti.optimize.metrics import build_custom_metrics


def test_build_custom_metrics_returns_one_metric_per_eval():
    metrics = build_custom_metrics()
    names = {m["name"] for m in metrics}
    assert names == {"board_recovery_recall", "transcript_word_error_rate", "concept_extraction_f1"}
    for m in metrics:
        assert "def evaluate(instance: dict)" in m["custom_function"]
