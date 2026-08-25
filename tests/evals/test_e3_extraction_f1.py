from evals.e3_extraction_f1 import concept_f1, edge_precision


def test_concept_f1_perfect_match():
    assert concept_f1(["a", "b"], ["a", "b"]) == 1.0


def test_concept_f1_partial_overlap():
    f1 = concept_f1(["a", "b", "c"], ["a", "b"])
    assert 0.7 < f1 < 0.9


def test_edge_precision_counts_only_correct_predictions():
    predicted = [("a", "b", "REQUIRES"), ("c", "d", "REQUIRES")]
    gold = [("a", "b", "REQUIRES")]
    assert edge_precision(predicted, gold) == 0.5
