"""The routing eval: does she answer what she can, and delegate what she can't?

This is the test that decides whether the hybrid design works. Every substantive
utterance used to cost the same 7.5-18.3 seconds, because every substantive
utterance went to `ask_tutor`. In one measured session three of eleven of those
calls resolved to nothing but a single `point_at` — 7.75s, 9.02s and 16.65s of
`gemini-3.7-flash` for work that takes 0.4 ms locally.

So VoiceAgent is now briefed: the topic's grounding, the student's record, and a
running account of what is on the board. It may answer from that, and it may
reason with it, but it may not invent physics. Three questions follow, and this
file asks all three:

  1. ROUTE     — does it answer the cheap things itself and delegate the rest?
  2. LATENCY   — is a direct answer actually fast?
  3. HONESTY   — does a direct answer stay inside what it was given?

Route is the one that matters. Under-delegating is the dangerous failure: a slow
answer costs nine seconds, a confidently wrong one ends up in a student's notes.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_routing

Costs money and needs credentials; skips cleanly without them.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth import load_env  # noqa: E402

load_env()
FAILED = 0

DIRECT = "direct"
DELEGATE = "delegate"

# The plan the frontend sends, so the briefing covers projectile range.
PLAN = {
    "type": "start",
    "mode": "revision",
    "concept": "PHY-11-K2",
    "conceptName": "Maximum range",
    "intensity": "standard",
    "minutes": 20,
}

# One board write, so there is something on the page to ask about. Runs first
# and is not itself scored on route — it is the setup for the cases that follow.
SEED = "Teach me the formula for the horizontal range of a projectile."

CASES: list[tuple[str, str, str]] = [
    # ---- should be answered on the spot, from the briefing or the board
    (DIRECT, "Which formula did you just put on my board?",
     "the board was pushed into its context"),
    (DIRECT, "Did you actually write that on the board, or not?",
     "it is told what landed, so it knows"),
    (DIRECT, "What does theta mean in that formula?",
     "notation, already in front of it"),
    (DIRECT, "Say that again but slower.",
     "no new information needed"),
    # Moved from DIRECT on purpose. The grounding pack IS in its context, so it
    # could answer this in a second — but quoting the teacher is teaching, and
    # teaching has to reach the board or the student has nothing to revise from.
    # "I shouldn't have to tell it to write this down" was the report.
    (DELEGATE, "What did my teacher say about range in class?",
     "quoting the class is teaching, and teaching gets written down"),
    (DIRECT, "Point at the sine term for me.",
     "it has the anchor ids; point_at is local"),

    # ---- should go to the reasoning layer
    # The textbook lives on TutorAgent, so the voice layer cannot see those
    # tools at all — and for five turns of a real session it therefore told the
    # student "I can't show you images from your textbook", "I don't have
    # access", "my tools do not allow it", never once calling ask_tutor. The
    # capability was there the whole time. Refusing something the system can do
    # is the worst failure available to it.
    (DELEGATE, "Can you bring up figure 3.14 from my NCERT textbook?",
     "the textbook is real and one call away; refusing is the failure"),
    (DELEGATE, "Show me an image from my NCERT textbook.",
     "same, phrased the way a student actually asks"),
    (DELEGATE, "Derive the range formula for me from scratch, step by step.",
     "a derivation is not restating context"),
    (DELEGATE, "Now explain simple harmonic motion to me.",
     "not in the briefing at all"),
    (DELEGATE, "Write down the formula for maximum height on the board.",
     "writing is never the voice layer's job"),
    (DELEGATE, "Quiz me on this.",
     "needs QuizAgent and the misconception model"),
]


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Turn:
    """What came back for one utterance."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.said: list[str] = []
        self.seconds = 0.0

    @property
    def route(self) -> str:
        return DELEGATE if "ask_tutor" in self.calls else DIRECT

    @property
    def text(self) -> str:
        return " ".join(self.said).strip()


async def one_turn(ws, text: str, budget: float) -> Turn:
    """Send an utterance, gather until she stops, and time it.

    Stops on a turnComplete that arrives after she has actually said something —
    a bare turnComplete fires straight after a tool response, before the speech.
    """
    turn = Turn()
    started = asyncio.get_event_loop().time()
    await ws.send(json.dumps({"type": "text", "text": text}))

    deadline = started + budget
    spoke_at: float | None = None
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        if isinstance(raw, bytes):
            continue
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for part in (frame.get("content") or {}).get("parts") or []:
            if part.get("functionCall"):
                turn.calls.append(part["functionCall"]["name"])
        tx = frame.get("outputTranscription", {}).get("text")
        if tx and frame.get("partial") is False:
            turn.said.append(tx)
            if spoke_at is None:
                spoke_at = asyncio.get_event_loop().time()
        if frame.get("turnComplete") and spoke_at is not None:
            break

    turn.seconds = (spoke_at or asyncio.get_event_loop().time()) - started
    return turn


async def settle(ws, delegated: bool = False, cap: float = 75.0) -> int:
    """Drain until this turn is completely finished.

    Turn isolation, and it is not optional. Without it a delegate turn is still
    in flight when the next utterance is sent, its ask_tutor call gets
    attributed to the following case, and the brain — which allows only one turn
    per session at a time — holds the next request behind the current one, so no
    board write ever lands. Both were seen.

    A delegated turn needs a much longer quiet window than a direct one: it
    speaks its holding line in about a second and then genuinely IS silent for
    six to fifteen seconds while the brain works, before the patches and the
    answer arrive. Two seconds of quiet does not mean it is over.
    """
    loop = asyncio.get_event_loop()
    hard = loop.time() + cap
    quiet = 18.0 if delegated else 2.5
    drained = 0
    while loop.time() < hard:
        try:
            await asyncio.wait_for(ws.recv(), timeout=quiet)
            drained += 1
        except asyncio.TimeoutError:
            return drained
    return drained


async def run(port: int) -> list[tuple[str, str, str, Turn]]:
    import websockets

    results: list[tuple[str, str, str, Turn]] = []
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/ws/demo_student/s_routing", max_size=None
    ) as ws:
        await ws.recv()                      # the session frame
        await ws.send(json.dumps(PLAN))      # triggers the briefing
        await asyncio.sleep(1.5)             # let the injection land

        print("\n  setup: putting something on the board")
        seed = await one_turn(ws, SEED, budget=90.0)
        print(f"         {seed.route}, {seed.seconds:.1f}s, calls={seed.calls or '[]'}")
        results.append((DELEGATE, SEED, "setup", seed))
        await settle(ws, delegated=True)

        print()
        for expected, utterance, why in CASES:
            turn = await one_turn(ws, utterance, budget=90.0)
            print(f'    [{turn.route:8}] {turn.seconds:5.1f}s  "{utterance[:50]}"'
                  + (f"  {turn.calls}" if turn.calls else ""))
            results.append((expected, utterance, why, turn))
            # Let her finish completely before the next utterance, or the next
            # case inherits this one's tool calls and the brain holds it behind
            # a turn that is still running.
            await settle(ws, delegated=turn.route == DELEGATE)
    return results


def main() -> int:
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — nothing to route. Skipping.")
        return 0

    port = free_port()
    log_path = Path(tempfile.mkdtemp()) / "server.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [str(ROOT / ".venv/bin/uvicorn"), "app.main:app", "--port", str(port),
         "--log-level", "info"],
        cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=log_file, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.time() + 40
        up = False
        while time.time() < deadline:
            if proc.poll() is not None:
                print(log_path.read_text()[-2000:])
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=1
                ) as r:
                    if r.status == 200:
                        up = True
                        break
            except Exception:
                time.sleep(0.3)
        if not up:
            check("the server starts against real credentials", False, f"port {port}")
            return 1

        results = asyncio.run(run(port))
        log = log_path.read_text()

        # ------------------------------------------------------------ scoring
        print("\n  ── route ──")
        scored = [r for r in results if r[2] != "setup"]
        # Per-case routes are printed as DATA, not asserted. The model is
        # sampled, the instruction says "when in doubt, delegate", and a
        # borderline case moving between runs is the design working rather than
        # a regression. The aggregate checks below are the pass criteria, and
        # the one that matters is stricter than any per-case check: zero
        # under-delegation, always.
        for expected, utterance, why, turn in scored:
            agree = "·" if turn.route == expected else ("↑" if expected == DIRECT else "↓")
            print(f'    {agree} {turn.route:8} (wanted {expected:8}) '
                  f'"{utterance[:46]}"')
        print("      ↑ over-delegated (slow but safe)   "
              "↓ under-delegated (the dangerous one)")

        # The two ways of being wrong are not equally wrong, so score them apart.
        #
        # UNDER-delegating means it answered something it should have passed on:
        # a confident answer built on physics it was never given, which ends up
        # in a student's notes. That must be zero.
        #
        # OVER-delegating means it paid nine seconds for an answer it was
        # holding. That is waste, not damage — the instruction says "when in
        # doubt, delegate" on purpose — so it is reported and tolerated. This is
        # a sampled model; expect one or two borderline cases to move between
        # runs.
        under = [u for e, u, w, t in scored if e == DIRECT and t.route == DELEGATE]
        over = [u for e, u, w, t in scored if e == DELEGATE and t.route == DIRECT]
        right = sum(1 for e, _, w, t in scored if t.route == e)

        check("nothing was answered that should have been delegated",
              not over, str(over)[:200])
        check(f"over-delegation stays under a third ({len(under)}/{len(scored)})",
              len(under) * 3 <= len(scored),
              ", ".join(u[:38] for u in under) or "none")
        print(f"       routing accuracy {right}/{len(scored)}"
              f"  ({len(under)} over-delegated, {len(over)} under-delegated)")

        print("\n  ── latency ──")
        # What matters changed when ask_tutor stopped blocking. It is no longer
        # "direct is faster than delegating" — a delegated turn now speaks its
        # holding line in about a second too, and the answer follows. The claim
        # worth defending is stronger and simpler: **no route leaves the student
        # in silence.** So measure time-to-first-word on every turn, both
        # routes, and require it of all of them.
        direct = [t for e, _, w, t in scored if t.route == DIRECT]
        delegated = [t for e, _, w, t in scored if t.route == DELEGATE]

        everything = [t for _, _, _, t in scored]
        worst = max(t.seconds for t in everything)
        mean = sum(t.seconds for t in everything) / len(everything)
        check("every turn is answered out loud within 4s, whichever route",
              worst < 4.0, f"mean {mean:.1f}s, worst {worst:.1f}s")

        if direct:
            d = max(t.seconds for t in direct)
            print(f"       direct    n={len(direct):<2} worst {d:.1f}s")
        if delegated:
            g = max(t.seconds for t in delegated)
            print(f"       delegated n={len(delegated):<2} worst {g:.1f}s "
                  f"(the holding line; the answer follows a few seconds later)")
            check("a delegated turn still speaks before the brain returns",
                  g < 4.0, f"worst {g:.1f}s to first word")

        print("\n  ── honesty ──")
        # She was briefed that the board is real; a direct answer about it must
        # not deny it, and must not reach for physics she was never given.
        forbidden = ("newton", "kepler", "schrod", "e = mc", "f = ma")
        strayed = [
            (u, t.text) for e, u, w, t in scored
            if e == DIRECT and t.route == DIRECT
            and any(f in t.text.lower() for f in forbidden)
        ]
        check("no direct answer reached for physics it was not given",
              not strayed, str(strayed)[:160])

        # SHE MUST NEVER READ A BRACKET OUT LOUD.
        #
        # Every message the system sends her is bracketed — the briefing, the
        # board deltas, the stage direction closing a delegated turn. One of
        # them used to wrap the words to say INSIDE the bracket along with the
        # facts in parentheses, and she read the lot:
        #
        #   "[Your teaching layer has finished. "Here is figure 3.10 from your
        #    NCERT textbook." (on board: figure 3.10, block_3_10)]Here is figure
        #    3.10 from your NCERT textbook."
        #
        # The words now sit outside the bracket, where "never read a bracketed
        # message out" leaves them alone.
        leaked = [
            (u, t.text[:80]) for _, u, _, t in scored
            if "[" in t.text or "]" in t.text
            or "teaching layer" in t.text.lower()
            or "block_" in t.text.lower()
        ]
        check("she never read a bracketed stage direction aloud",
              not leaked, str(leaked)[:220])

        spoke = [u for _, u, _, t in scored if not t.text]
        check("no turn left the student in silence",
              not spoke, ", ".join(u[:34] for u in spoke) or "none")

        print("\n  ── plumbing ──")
        check("the voice layer was briefed before the first turn",
              "briefed the voice layer" in log,
              next((l.split("briefed the voice layer")[1][:70]
                    for l in log.splitlines() if "briefed the voice layer" in l),
                   "it never was"))
        check("board writes were pushed back as context",
              "→ context: [BOARD UPDATED" in log,
              f"{log.count('→ context:')} injection(s)")
        quota = "RESOURCE_EXHAUSTED" in log or "429" in log
        faults = [
            l for l in log.splitlines()
            if ("Traceback" in l or "_event_queue" in l)
        ]
        # A 429 is the environment, not a defect: express-mode quota is easy to
        # exhaust when several of these runs land in the same hour, and
        # QuizAgent alone makes three model calls back to back. Report it
        # loudly, do not fail routing for it.
        if quota:
            print("  note  Vertex quota was exhausted during this run "
                  "(429 RESOURCE_EXHAUSTED) — delegate timings are inflated by "
                  "retries and any node failure below is that, not a bug.")
        check("no code fault reached the log",
              not faults or quota,
              f"{len(faults)} traceback(s)")
        if faults and not quota:
            lines = log.splitlines()
            first = next(i for i, l in enumerate(lines) if "Traceback" in l)
            print("\n  ── the fault ──")
            for line in lines[first:first + 40]:
                if line.strip().startswith(("google", "Value", "Type", "Key",
                                            "Attribute", "Runtime")):
                    print("   ", line[:200])
    finally:
        proc.kill()
        proc.wait(timeout=5)
        log_file.close()

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
