import cv2
import numpy as np


def board_recovery_recall(predicted_mask: np.ndarray, ground_truth_mask: np.ndarray,
                           iou_threshold: float = 0.5) -> float:
    """AccessMath-style connected-component recall: fraction of ground-truth
    ink components that have a matching (IoU >= threshold) predicted component."""
    gt_n, gt_labels = cv2.connectedComponents(ground_truth_mask.astype(np.uint8))
    pred_n, pred_labels = cv2.connectedComponents(predicted_mask.astype(np.uint8))

    if gt_n <= 1:
        return 1.0

    matched = 0
    for gt_id in range(1, gt_n):
        gt_component = gt_labels == gt_id
        best_iou = 0.0
        for pred_id in range(1, pred_n):
            pred_component = pred_labels == pred_id
            intersection = np.logical_and(gt_component, pred_component).sum()
            union = np.logical_or(gt_component, pred_component).sum()
            if union > 0:
                best_iou = max(best_iou, intersection / union)
        if best_iou >= iou_threshold:
            matched += 1
    return matched / (gt_n - 1)
