import numpy as np


def match_local(donor_patch: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Match donor pixels' mean/std to the target's local neighbourhood so
    donated patches don't leave visible seams that confuse OCR."""
    result = donor_patch.copy().astype(np.float32)
    for c in range(donor_patch.shape[-1]):
        donor_vals = donor_patch[..., c][mask].astype(np.float32)
        target_vals = target[..., c][~mask].astype(np.float32) if (~mask).any() else donor_vals
        if donor_vals.size == 0 or target_vals.size == 0:
            continue
        d_mean, d_std = donor_vals.mean(), donor_vals.std() + 1e-6
        t_mean, t_std = target_vals.mean(), target_vals.std() + 1e-6
        result[..., c] = (result[..., c] - d_mean) / d_std * t_std + t_mean
    return np.clip(result, 0, 255).astype(np.uint8)
