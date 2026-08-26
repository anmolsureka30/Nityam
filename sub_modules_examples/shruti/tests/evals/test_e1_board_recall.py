import numpy as np
from evals.e1_board_recall import board_recovery_recall


def test_recall_is_one_for_identical_masks():
    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[5:10, 5:10] = 1
    mask[20:25, 20:25] = 1
    assert board_recovery_recall(mask, mask) == 1.0


def test_recall_is_half_when_one_of_two_components_is_missing():
    gt = np.zeros((30, 30), dtype=np.uint8)
    gt[5:10, 5:10] = 1
    gt[20:25, 20:25] = 1
    predicted = np.zeros((30, 30), dtype=np.uint8)
    predicted[5:10, 5:10] = 1
    assert board_recovery_recall(predicted, gt) == 0.5
