from google.adk.agents import SequentialAgent, ParallelAgent, LlmAgent
from google.adk.models import Gemini
from shruti.config import Models


def build_pipeline() -> SequentialAgent:
    router = Models().router
    reasoner = Models().reasoner

    gate = LlmAgent(name="Gate", model=Gemini(model=router),
                     instruction="Admit the recording: probe, normalize, fingerprint, "
                                 "classify the writing surface.",
                     output_key="recording")
    pulse = LlmAgent(name="Pulse", model=Gemini(model=router),
                      instruction="Build the temporal spine: shots, ink curve, erase "
                                  "events, adaptive sample plan.",
                      output_key="timeline")
    slate = LlmAgent(name="Slate", model=Gemini(model=router),
                      instruction="Recover clean board states for each interval. "
                                  "Degrade gracefully and report unrecoverable states.",
                      output_key="board_states")
    echo = LlmAgent(name="Echo", model=Gemini(model=reasoner),
                     instruction="Transcribe the audio faithfully, preserving code-mixing.",
                     output_key="utterances")
    point = LlmAgent(name="Point", model=Gemini(model=reasoner),
                      instruction="Resolve deictic references at gesture moments.",
                      output_key="deixis")
    perceive = ParallelAgent(name="Perceive", sub_agents=[slate, echo, point])
    weave = LlmAgent(name="Weave", model=Gemini(model=reasoner),
                      instruction="Fuse timeline, speech, and board signals into Beats.",
                      output_key="beats")
    glyph = LlmAgent(name="Glyph", model=Gemini(model=reasoner),
                      instruction="Read each board state into structured layout regions. "
                                  "Never guess occluded content.",
                      output_key="board_content")
    atlas = LlmAgent(name="Atlas", model=Gemini(model=reasoner),
                      instruction="Mine concepts, relations, and misconceptions.",
                      output_key="concept_graph")

    return SequentialAgent(name="Shruti",
                            sub_agents=[gate, pulse, perceive, weave, glyph, atlas])
