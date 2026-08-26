from app import config
from app.agents.artifact_agent import build_artifact_agent, create_artifact
from app.memory.tools import get_dpm, get_teaching_memory, log_artifact_evidence


def test_artifact_agent_identity():
    agent = build_artifact_agent()
    assert agent.name == "ArtifactAgent"
    assert agent.mode == "single_turn"
    assert agent.model == config.REASONING_MODEL


def test_artifact_agent_has_a_description_for_delegation():
    agent = build_artifact_agent()
    assert agent.description
    assert len(agent.description) > 10


def test_artifact_agent_has_create_artifact_and_memory_read_tools():
    agent = build_artifact_agent()
    assert create_artifact in agent.tools
    assert get_dpm in agent.tools
    assert get_teaching_memory in agent.tools
    assert log_artifact_evidence in agent.tools


def test_two_calls_to_build_artifact_agent_do_not_share_a_parent():
    a = build_artifact_agent()
    b = build_artifact_agent()
    assert a is not b
