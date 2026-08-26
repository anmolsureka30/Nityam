_BOARD_RECALL_FN = '''
def evaluate(instance: dict) -> float:
    from evals.e1_board_recall import board_recovery_recall
    import numpy as np
    predicted = np.array(instance["predicted_mask"])
    ground_truth = np.array(instance["ground_truth_mask"])
    return board_recovery_recall(predicted, ground_truth)
'''

_WER_FN = '''
def evaluate(instance: dict) -> float:
    from evals.e2_transcript_fidelity import word_error_rate
    return 1.0 - word_error_rate(instance["hypothesis"], instance["reference"])
'''

_CONCEPT_F1_FN = '''
def evaluate(instance: dict) -> float:
    from evals.e3_extraction_f1 import concept_f1
    return concept_f1(instance["predicted_concepts"], instance["gold_concepts"])
'''


def build_custom_metrics() -> list[dict]:
    return [
        {"name": "board_recovery_recall", "custom_function": _BOARD_RECALL_FN},
        {"name": "transcript_word_error_rate", "custom_function": _WER_FN},
        {"name": "concept_extraction_f1", "custom_function": _CONCEPT_F1_FN},
    ]
