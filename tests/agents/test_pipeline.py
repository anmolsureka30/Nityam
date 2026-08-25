from google.adk.agents import SequentialAgent, ParallelAgent
from shruti.agents.pipeline import build_pipeline


def test_build_pipeline_wires_stages_in_order():
    pipeline = build_pipeline()
    assert isinstance(pipeline, SequentialAgent)
    assert [a.name for a in pipeline.sub_agents] == \
        ["Gate", "Pulse", "Perceive", "Weave", "Glyph", "Atlas"]


def test_perceive_runs_slate_echo_point_in_parallel():
    pipeline = build_pipeline()
    perceive = next(a for a in pipeline.sub_agents if a.name == "Perceive")
    assert isinstance(perceive, ParallelAgent)
    assert [a.name for a in perceive.sub_agents] == ["Slate", "Echo", "Point"]
