import asyncio
from types import SimpleNamespace

from google.adk.tools.agent_tool import _SingleTurnAgentTool

from app import config
from app.agents.tutor_agent import _init_student, build_tutor_agent
from app.memory.tools import get_dpm, get_teaching_memory, log_turn, search_grounding


def test_tutor_agent_identity():
    agent = build_tutor_agent()
    assert agent.name == "TutorAgent"
    assert agent.model == config.REASONING_MODEL


def test_tutor_agent_defaults_to_a_valid_root_agent_mode():
    # ADK's Runner rejects mode='single_turn' on a root agent outright:
    # "LlmAgent as root agent must have mode='chat' or 'task', but got
    # mode='single_turn'." (google/adk/runners.py). build_tutor_agent()'s
    # default (mode=None, which the Runner itself normalizes to 'chat' for
    # a root agent) must stay valid for root use — this is what app/agent.py
    # actually constructs.
    agent = build_tutor_agent()
    assert agent.mode is None


def test_tutor_agent_supports_single_turn_mode_for_future_sub_agent_use():
    # Task 9 (VoiceAgent, not yet built) will attach TutorAgent as its own
    # sub-agent via build_tutor_agent(mode="single_turn") — the same
    # auto-wrap-into-tools mechanism ArtifactAgent relies on here. Proves
    # the factory still supports that mode on request, without making it
    # the default (which would break root-agent use, see the test above).
    agent = build_tutor_agent(mode="single_turn")
    assert agent.mode == "single_turn"


def test_tutor_agent_has_a_description_for_delegation():
    # Useful generically, and required for Task 9's future single_turn use:
    # with no input_schema set, ADK exposes a single_turn agent to its
    # parent as a tool taking one `request: str` field, described by
    # `agent.description` — verified against installed ADK source
    # (google/adk/tools/agent_tool.py::AgentTool._get_declaration).
    agent = build_tutor_agent()
    assert agent.description
    assert len(agent.description) > 10


def test_tutor_agent_has_the_memory_tools():
    agent = build_tutor_agent()
    assert search_grounding in agent.tools
    assert get_dpm in agent.tools
    assert get_teaching_memory in agent.tools
    assert log_turn in agent.tools


def test_tutor_agent_has_artifact_agent_as_a_single_turn_sub_agent():
    agent = build_tutor_agent()
    names = [a.name for a in agent.sub_agents]
    assert "ArtifactAgent" in names
    artifact_agent = next(a for a in agent.sub_agents if a.name == "ArtifactAgent")
    assert artifact_agent.mode == "single_turn"


def test_tutor_agent_auto_wraps_single_turn_sub_agent_as_a_tool():
    # This is the actual mechanism the "no raw AgentTool" architecture
    # decision relies on: LlmAgent.model_post_init auto-wraps any
    # mode='single_turn' sub-agent into the parent's own `.tools` list
    # (installed ADK source, google/adk/agents/llm_agent.py, the "Add
    # sub-agents as tools based on their mode" block). The previous test
    # only checked the *input* (ArtifactAgent listed in sub_agents with
    # mode='single_turn'); this checks the *output* — that the wrap
    # actually happened and points at the right agent instance.
    agent = build_tutor_agent()
    artifact_agent = next(a for a in agent.sub_agents if a.name == "ArtifactAgent")

    wrapped = [t for t in agent.tools if isinstance(t, _SingleTurnAgentTool)]
    assert len(wrapped) == 1
    assert wrapped[0].name == "ArtifactAgent"
    assert wrapped[0].agent is artifact_agent


def test_two_calls_to_build_tutor_agent_do_not_share_a_parent():
    # Regression guard for the "agent already has a parent" ValidationError —
    # factory functions must build fresh agent instances every call.
    a = build_tutor_agent()
    b = build_tutor_agent()
    assert a is not b


def test_init_student_defaults_student_id_when_absent():
    callback_context = SimpleNamespace(state={})
    asyncio.run(_init_student(callback_context))
    assert callback_context.state["student_id"] == "demo_student"


def test_init_student_does_not_override_an_already_set_student_id():
    callback_context = SimpleNamespace(state={"student_id": "someone_else"})
    asyncio.run(_init_student(callback_context))
    assert callback_context.state["student_id"] == "someone_else"
