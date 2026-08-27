"""Scripted board writes for mock mode — no credentials, no network.

This is not a fake of the delivery path: patches published here go through the
same `sessions.publish` -> outbox -> outbound route the real tools use, so the
frontend reducer, the anchor gate and the patch ordering all get exercised for
real. Only the *choice* of what to write is scripted.

It keeps roughly the same beats as the old frontend/src/lib/tutorScript.ts, so
the demo reads the same with the network unplugged.
"""
from __future__ import annotations

from app import sessions
from app.canvas import doc as D
from app.canvas.tools import parse_markup


def _note(session_id: str, text: str, prefix: str = "b_note") -> None:
    state = sessions.get(session_id)
    clean, marked = parse_markup(text)
    anchors = [
        D.Anchor(id=state.mint(f"a_{D.slug(span, 12)}"), span=span, concept=concept)
        for span, concept in marked
    ]
    sessions.publish(
        session_id,
        D.AppendBlock(
            block=D.TutorText(id=state.mint(prefix), text=clean, anchors=anchors)
        ),
    )


def _equation(session_id: str, tex: str, caption: str) -> None:
    state = sessions.get(session_id)
    clean, marked = parse_markup(tex)
    anchors = [
        D.Anchor(id=state.mint(f"a_{D.slug(span, 12)}"), span=span, concept=concept)
        for span, concept in marked
    ]
    sessions.publish(
        session_id,
        D.AppendBlock(
            block=D.Equation(
                id=state.mint("b_eq"), tex=clean, caption=caption or None, anchors=anchors
            )
        ),
    )


def _quiz(session_id: str) -> None:
    state = sessions.get(session_id)
    cid = state.mint("c")
    sessions.publish(
        session_id,
        D.ShowQuiz(
            checkpoint=D.Checkpoint(
                id=cid,
                index=1,
                total=1,
                question="Tonight the speed is fixed at 20 m/s. So what actually decides how far the ball lands?",
                hint="Look at the formula and ask which symbol you can change.",
                footnote="projectile.horizontal_range",
                options=[
                    D.CheckpointOption(
                        id=f"{cid}_a", letter="A", text="The launch angle", correct=True
                    ),
                    D.CheckpointOption(
                        id=f"{cid}_b", letter="B", text="The launch speed", correct=False,
                        rebuttal="Speed matters in general — but tonight it is given to you as 20 m/s, so it cannot be the thing you are choosing.",
                    ),
                    D.CheckpointOption(
                        id=f"{cid}_c", letter="C", text="The mass of the ball", correct=False,
                        rebuttal="Mass cancels out of the range formula entirely. Look — there is no m in it.",
                    ),
                ],
            )
        ),
    )


def script_reply(session_id: str, said: str) -> None:
    """Write whatever this utterance would plausibly have made the tutor write."""
    low = said.lower()

    # The three modes open differently, so the mock does too — otherwise mock
    # mode cannot demonstrate the one thing the modes were added for.
    if "has opened a revision session" in low:
        _note(
            session_id,
            "Mr. Deshpande asked why [[45°|projectile.launch_angle]] is special and "
            "then the bell went. Let's pick that up — what do you think decides "
            "how far it goes?",
        )
        return

    if "has opened exam preparation" in low:
        _note(
            session_id,
            "Straight to the thing that costs you marks: you reach for "
            "[[speed|projectile.launch_speed]] when the question is about "
            "[[angle|projectile.launch_angle]]. Here is one the way the paper asks it.",
        )
        return

    if "has opened a doubt session" in low:
        _note(session_id, "Tell me what's bothering you and we'll take it apart.")
        return

    if "answered checkpoint" in low:
        state = sessions.get(session_id)
        tone = "finding" if "which is correct" in low else "correction"
        label = "YOU WORKED THIS OUT" if tone == "finding" else "WORTH KEEPING"
        text = (
            "The angle is the only thing you control, so the angle is what decides "
            "it. Saved in your own words."
            if tone == "finding"
            else "Speed does matter in general — but tonight it is fixed. Look at "
            "what is left."
        )
        sessions.publish(
            session_id,
            D.AppendBlock(
                block=D.Callout(
                    id=state.mint("b_call"), tone=tone, label=label, text=text
                )
            ),
        )
        return

    # Order matters: "answered checkpoint …" contains "checkpoint", so the
    # answer branch above has to win or answering a quiz shows another quiz.
    if "quiz" in low or "test me" in low or "checkpoint" in low:
        _quiz(session_id)
        return

    if "formula" in low or "range" in low or "45" in low or "why" in low:
        _equation(
            session_id,
            "R = u² [[sin(2θ)|projectile.horizontal_range]] / g",
            "range of a projectile on flat ground",
        )
        _note(
            session_id,
            "Of these, [[u|projectile.launch_speed]] and g are handed to you. Only "
            "[[θ|projectile.launch_angle]] is yours to choose, so θ is what decides "
            "the answer.",
        )
        return

    if "show me" in low or "simulat" in low or "diagram" in low or "draw" in low:
        # No IR: the frontend falls back to its hand-written kernel, so mock
        # mode still has something interactive to explore with no model call.
        state = sessions.get(session_id)
        sessions.publish(
            session_id,
            D.AppendBlock(
                block=D.ArtifactBlock(
                    id=state.mint("b_art"), artifactId="art_launch_angle", ir={}
                )
            ),
        )
        _note(
            session_id,
            "Drag the [[angle|projectile.launch_angle]] and watch where it lands. "
            "Do not take my word for it — find the furthest one yourself.",
        )
        return

    if "marked" in low and "did not cover any words" not in low:
        _note(
            session_id,
            "You pointed at that, so let's stay on it — tell me what you think it "
            "does and I'll tell you if you're right.",
        )
        return

    if "discovered the optimum" in low or "discovered_optimum" in low:
        state = sessions.get(session_id)
        sessions.publish(
            session_id,
            D.AppendBlock(
                block=D.Callout(
                    id=state.mint("b_call"),
                    tone="finding",
                    label="YOU FOUND IT YOURSELF",
                    text="That is the furthest it goes, and you found it by exploring rather than being told.",
                )
            ),
        )
