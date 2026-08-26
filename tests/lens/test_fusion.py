from shruti.lens.fusion import reciprocal_rank_fusion


def test_fusion_ranks_items_present_in_both_lists_above_single_list_items():
    fused = reciprocal_rank_fusion(["a", "b", "c"], ["b", "a", "d"])
    ranked_ids = [item_id for item_id, _score in fused]
    # "a" and "b" each appear near the top of both lists; "c" and "d" each
    # appear in only one list — the fused-in-both items must rank higher.
    assert set(ranked_ids[:2]) == {"a", "b"}
    assert set(ranked_ids[2:]) == {"c", "d"}


def test_fusion_handles_a_single_list_unchanged_in_relative_order():
    fused = reciprocal_rank_fusion(["x", "y", "z"])
    assert [item_id for item_id, _score in fused] == ["x", "y", "z"]


def test_fusion_handles_no_lists():
    assert reciprocal_rank_fusion() == []
