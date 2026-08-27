"""Drive the teaching loop in text mode — no microphone, no browser, no Live API.

This is the cheapest way to see whether the tutor actually uses its board, and
it is where to come back to when it stops. It runs TutorAgent directly through
run_async (so `before_model_callback` and friends all fire normally), prints
every tool call, and then prints the board that came out.

    .venv/bin/python -m scripts.drive "why is 45 degrees the best angle?"
    .venv/bin/python -m scripts.drive            # runs a short scripted lesson
"""
from __future__ import annotations

import asyncio
import sys

from app.auth import configure, describe, load_env

load_env()
MODE = configure()

from google.adk.apps import App  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from app import sessions  # noqa: E402
from app.agent import APP_NAME  # noqa: E402
from app.agents.tutor_agent import build_tutor_agent  # noqa: E402
from app.canvas import doc as D  # noqa: E402

SESSION_ID = "s_drive"
USER_ID = "demo_student"

SCRIPT = [
    "Hi — Mr Deshpande asked why 45 degrees is special and then the bell went.",
    "Why is 45 the best angle?",
    "[The student marked “sin(2θ)” on the page with the marker. Explain that specific thing.]",
    "Quiz me on this.",
]


async def main(turns: list[str]) -> int:
    print(f"── {describe()}\n")

    service = InMemorySessionService()
    runner = Runner(
        app=App(name=APP_NAME, root_agent=build_tutor_agent()),
        session_service=service,
    )
    await service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID,
        state={"session_id": SESSION_ID, "student_id": USER_ID},
    )

    tool_calls: list[str] = []

    for turn in turns:
        print(f"\n\033[1mstudent:\033[0m {turn}\n")
        said: list[str] = []
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=types.Content(role="user", parts=[types.Part(text=turn)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.function_call:
                    name = part.function_call.name
                    tool_calls.append(name)
                    args = str(part.function_call.args)
                    print(f"  → {event.author} calls \033[36m{name}\033[0m({args[:160]}"
                          f"{'…' if len(args) > 160 else ''})")
                if part.function_response:
                    got = str(part.function_response.response)
                    print(f"  ← {part.function_response.name} -> {got[:160]}"
                          f"{'…' if len(got) > 160 else ''}")
                if part.text and event.author == "TutorAgent":
                    said.append(part.text)
        if said:
            print(f"\n\033[1mtutor:\033[0m {''.join(said).strip()}")

    # ---------------------------------------------------------------- the board
    state = sessions.get(SESSION_ID)
    print("\n\n── the board it produced " + "─" * 40)
    for block in state.board.blocks():
        struck = " [STRUCK]" if block.struck else ""
        anchors = ", ".join(a.span for a in D.block_anchors(block))
        print(f"\n  {block.kind}{struck}  ({block.id})")
        print(f"    {D.block_text(block)[:300]}")
        if anchors:
            print(f"    pointable: {anchors}")

    drained = []
    while not state.outbox.empty():
        drained.append(state.outbox.get_nowait())

    print("\n\n── summary " + "─" * 54)
    print(f"  tool calls   : {len(tool_calls)}")
    board_tools = [
        t for t in tool_calls
        if t.startswith(("write_", "point_at", "strike_", "scroll_", "read_screen"))
    ]
    print(f"  board tools  : {len(board_tools)}  {sorted(set(board_tools))}")
    print(f"  grounding    : {tool_calls.count('search_grounding')} search_grounding call(s)")
    print(f"  memory reads : {tool_calls.count('get_dpm')} get_dpm, "
          f"{tool_calls.count('get_teaching_memory')} get_teaching_memory")
    print(f"  log_turn     : {tool_calls.count('log_turn')}")
    print(f"  delegated to : {sorted({t for t in tool_calls if t.endswith('Agent')})}")
    print(f"  patches      : {len(drained)}  {[p.op for p in drained]}")

    # What actually has to be true for the product to work at all.
    problems = []
    if not board_tools:
        problems.append("the tutor never wrote on the board")
    if not tool_calls.count("search_grounding"):
        problems.append("nothing was grounded in the lecture")
    if not drained:
        problems.append("no patches reached the outbox, so the browser would see nothing")
    print()
    for p in problems:
        print(f"  \033[31mPROBLEM\033[0m {p}")
    if not problems:
        print("  \033[32mthe loop is intact\033[0m: grounded, wrote to the board, patches queued")
    return 1 if problems else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    raise SystemExit(asyncio.run(main(argv or SCRIPT)))
