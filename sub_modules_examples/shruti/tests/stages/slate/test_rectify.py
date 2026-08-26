import numpy as np
from shruti.stages.slate.rectify import rectify


def test_rectify_maps_quad_to_full_canonical_frame():
    frame = np.zeros((150, 200, 3), dtype=np.uint8)
    frame[20:130, 30:170] = (10, 20, 30)  # the "board" region, one flat color
    quad = ((30, 20), (170, 20), (170, 130), (30, 130))
    rectified = rectify(frame, quad, out_size=(100, 100))
    assert rectified.shape[:2] == (100, 100)
    center = rectified[50, 50]
    assert tuple(int(c) for c in center) == (10, 20, 30)
