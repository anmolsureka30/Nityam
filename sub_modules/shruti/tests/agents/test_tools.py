from shruti.agents.tools import GATE_TOOLS, PULSE_TOOLS


def test_gate_tools_wraps_three_functions():
    assert len(GATE_TOOLS) == 3


def test_pulse_tools_wraps_two_functions():
    assert len(PULSE_TOOLS) == 2
