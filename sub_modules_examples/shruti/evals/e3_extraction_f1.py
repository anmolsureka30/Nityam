def concept_f1(predicted: list[str], gold: list[str]) -> float:
    pred_set, gold_set = set(predicted), set(gold)
    if not pred_set and not gold_set:
        return 1.0
    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def edge_precision(predicted: list[tuple], gold: list[tuple]) -> float:
    if not predicted:
        return 1.0 if not gold else 0.0
    gold_set = set(gold)
    correct = sum(1 for e in predicted if e in gold_set)
    return correct / len(predicted)
