import pytest
from shruti.agents.state import Stage, next_stage, is_before


def test_next_stage_advances_in_order():
    assert next_stage(Stage.ADMITTED) == Stage.SPINED
    assert next_stage(Stage.PERCEIVED) == Stage.WOVEN


def test_next_stage_raises_at_terminal_stage():
    with pytest.raises(ValueError):
        next_stage(Stage.SHELVED)


def test_is_before_orders_correctly():
    assert is_before(Stage.ADMITTED, Stage.SHELVED)
    assert not is_before(Stage.SHELVED, Stage.ADMITTED)
