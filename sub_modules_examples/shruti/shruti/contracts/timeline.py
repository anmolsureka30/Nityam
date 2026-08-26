from pydantic import BaseModel


class Shot(BaseModel):
    start_s: float
    end_s: float


class EraseEvent(BaseModel):
    at_s: float
    before: float
    after: float


class SamplePlanRegion(BaseModel):
    start_s: float
    end_s: float
    fps: float
    pixel_diff_threshold: float


class Timeline(BaseModel):
    recording_id: str
    shots: list[Shot] = []
    ink_curve: list[float] = []
    ink_curve_times: list[float] = []
    erase_events: list[EraseEvent] = []
    sample_plan: list[SamplePlanRegion] = []
