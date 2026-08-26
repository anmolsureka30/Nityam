from shruti.config import Models, Budget, SlateConfig, PulseConfig


def test_config_defaults_load():
    assert Models().reasoner == "gemini-3.5-flash"
    assert Budget().max_cost_per_recording_usd == 2.00
    assert SlateConfig().mask_tier == "framediff"
    assert PulseConfig().dense_fps == 1.0
