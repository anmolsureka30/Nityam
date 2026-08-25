"""ArtifactSpec - the input side of the module.

This is what the Learning Agent hands to create_artifact(). It is deliberately
pedagogical, not visual: it says what the student needs to work out, not what
the screen should look like. Turning it into something renderable is the
generator's job.
"""

import json
from dataclasses import dataclass, field


@dataclass
class ArtifactSpec:
    intent: str
    concept_ids: list
    learning_outcome: str
    target_misconception: str = ""
    must_be_manipulable: list = field(default_factory=list)
    must_be_visible: list = field(default_factory=list)
    student: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)
    mode: str = "deep_revision"

    @staticmethod
    def load(path):
        with open(path) as f:
            d = json.load(f)
        known = ArtifactSpec.__dataclass_fields__.keys()
        return ArtifactSpec(**{k: v for k, v in d.items() if k in known})

    @property
    def interest(self):
        return (self.student or {}).get("interest", "plain")

    def to_prompt_json(self):
        return json.dumps({
            "intent": self.intent,
            "concept_ids": self.concept_ids,
            "learning_outcome": self.learning_outcome,
            "target_misconception": self.target_misconception,
            "must_be_manipulable": self.must_be_manipulable,
            "must_be_visible": self.must_be_visible,
            "student_mastery": (self.student or {}).get("mastery", {}),
        }, indent=2)
