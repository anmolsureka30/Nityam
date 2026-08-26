from scenedetect import open_video, SceneManager
from scenedetect.detectors import AdaptiveDetector
from shruti.contracts.timeline import Shot


def detect_shots(video_path: str, threshold: float = 27.0) -> list[Shot]:
    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(AdaptiveDetector(adaptive_threshold=threshold))
    manager.detect_scenes(video)
    scene_list = manager.get_scene_list()
    if not scene_list:
        return [Shot(start_s=0.0, end_s=video.duration.seconds)]
    return [Shot(start_s=s.seconds, end_s=e.seconds) for s, e in scene_list]
