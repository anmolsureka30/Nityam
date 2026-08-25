from google.adk.tools import FunctionTool
from shruti.stages.gate.probe import probe_video, fingerprint
from shruti.stages.gate.normalize import normalize_video
from shruti.stages.pulse.shots import detect_shots
from shruti.stages.pulse.plan import build_sample_plan

GATE_TOOLS = [FunctionTool(f) for f in (probe_video, normalize_video, fingerprint)]
PULSE_TOOLS = [FunctionTool(f) for f in (detect_shots, build_sample_plan)]
