from app import config


def test_live_model_is_the_verified_live_preview_id():
    assert config.LIVE_MODEL == "gemini-3.1-flash-live-preview"


def test_reasoning_model_is_the_verified_flash_id():
    assert config.REASONING_MODEL == "gemini-3.7-flash"
