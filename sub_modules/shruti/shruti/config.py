# shruti/config.py
from pydantic_settings import BaseSettings


class Models(BaseSettings):
    reasoner: str = "gemini-3.5-flash"
    router: str = "gemini-3.5-flash-lite"
    embedder: str = "gemini-embedding-001"
    whisper_model_size: str = "large-v3"


class Budget(BaseSettings):
    max_cost_per_recording_usd: float = 2.00
    use_batch_api: bool = True
    cache_ttl_seconds: int = 3600


class SlateConfig(BaseSettings):
    mask_tier: str = "framediff"
    board_vote_frames: int = 30
    composite_window_s: float = 45.0
    photometric_match: bool = True


class PulseConfig(BaseSettings):
    dense_fps: float = 1.0
    sparse_fps: float = 1 / 6
    erase_drop_ratio: float = 0.35
    erase_window_s: float = 3.0
    scene_threshold: float = 27.0
