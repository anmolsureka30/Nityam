"""Runs the LLM-judging phase in a SEPARATE PROCESS from agent execution.

Confirmed live, five times, across four fix attempts (retry-with-fresh-
client, sync-to-async client switch, structural separation of agent-vs-judge
code, and a second asyncio.run() for a fresh event loop): none of them
stopped a direct genai.Client() call from failing immediately - on the
FIRST judging call, in a brand-new event loop, with zero prior aiohttp
activity in that loop - after ADK agent execution had run earlier in the
SAME PROCESS. A minimal isolated script with no ADK involvement at all
succeeds immediately. That combination (fails after ADK ran earlier in the
process; a fresh event loop doesn't help; a fresh process does) points at
process-wide module-level state in google-genai or google-adk, not
anything loop-scoped - so a real subprocess, not just a new event loop, is
the fix that actually isolates it.

Reads a pickled list[PersonaResult] from argv[1], runs all judges, writes a
pickled list[JudgeResult] to argv[2].
"""
from __future__ import annotations

import asyncio
import pickle
import sys

from tests.eval.memory_eval.judges import run_all_judges


async def _main(in_path: str, out_path: str) -> None:
    results = pickle.loads(open(in_path, "rb").read())
    judge_results = []
    for result in results:
        judge_results.extend(await run_all_judges(result))
    with open(out_path, "wb") as f:
        pickle.dump(judge_results, f)


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1], sys.argv[2]))
