"""Reset one REAL signed-in student to a clean, demonstrable state.

WHAT IS SEEDED lives in app/seeding.py, not here — the account menu's
"Reset my account" button calls the same `reset()`, and when this content
lived in the script the two could have drifted apart.

    .venv/bin/python -m scripts.seed_student            # wipe, then seed
    .venv/bin/python -m scripts.seed_student --clear    # wipe only
    .venv/bin/python -m scripts.seed_student --student <uid> --email <addr>

WHAT IT DOES. Deletes every session log for the student, resets their
dpm_profile and teaching_memory, and writes back TWO finished sessions plus the
record those sessions produced. Idempotent: run it as often as you like and the
state is identical afterwards, which is what makes it usable before a demo.

The two sessions are seeded WITH before/after snapshots, so /sessions/:id has
something to show. That is the whole reason this exists in its current form —
a session log written before recaps existed renders as "no record kept", which
is honest but demonstrates nothing.

THE TWO SESSIONS ARE THE PREREQUISITES FOR TONIGHT, not a rehearsal of it.
Mr. Deshpande derived the range formula in class on Tue 25 Aug and asked "Why
is 45 degrees special? Think about it tonight" — and never answered it
(lib/data.ts:classRecap). Tonight's session is that question. So the record
behind it has to be what a student would already have covered on the way
there:

    5 days ago   Resolving a vector into components
    2 days ago   Motion in two dimensions — the two axes are independent
    TONIGHT      Maximum range, and why 45 degrees wins   <- not seeded

Seeding tonight's topic as a past session would make the live session look
like a repeat, which is the opposite of the point.

WHY THE CONTENT IS NOT INVENTED. The failures are taken from real recorded
sessions (backend/logs/2026-08-30_02-46-17 and 03-37-59): the student really
did answer "u sin theta" when asked for the horizontal component, and really
did need walking through every step of the derivation. The memory layer's
invariant is that a claim about a student resolves back to a moment that
happened.

CONCEPT IDS ARE THE REAL ONES, checked against store.list_concept_ids(). This
matters: `seed_demo_data.py` cites `projectile.horizontal_range` twice and no
such concept is in the corpus, so those weaknesses retrieve nothing and vanish
from the brief without any error.
"""
from __future__ import annotations

import argparse

# BEFORE app.memory.store: store.py picks its backend off NITYAM_STORE at
# IMPORT time, so loading .env afterwards silently seeds sqlite while the
# running app reads Firestore. That happened on this script's first run.
from app.auth import load_env

load_env()

from app.memory import store  # noqa: E402

from app.seeding import (  # noqa: E402
    DEFAULT_EMAIL,
    DEFAULT_STUDENT,
    reset,
    wipe,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--student", default=DEFAULT_STUDENT, help="Firebase uid")
    ap.add_argument("--email", default=DEFAULT_EMAIL, help="only for the printout")
    ap.add_argument("--clear", action="store_true", help="wipe and stop")
    args = ap.parse_args()

    conn = store.connect()
    print(f"store: {store.backend()}")

    if args.clear:
        gone = wipe(conn, args.student)
        print(f"cleared {gone} session log(s) and the record for {args.student}")
        return 0

    outcome = reset(conn, args.student)
    print(f"cleared {outcome['cleared_sessions']} session log(s) "
          f"and the record for {args.student}")

    logs = store.list_session_logs(conn, args.student)
    dpm = store.get_dpm(conn, args.student)
    tm = store.get_teaching_memory(conn, args.student)
    print(f"\nseeded {args.email}")
    print(f"  sessions      : {len(logs)}")
    for entry in logs:
        moved = sum(
            1 for cid in set(entry.dpm_before.weaknesses if entry.dpm_before else {})
            | set(entry.dpm_after.weaknesses if entry.dpm_after else {})
            if (entry.dpm_before.weaknesses.get(cid) if entry.dpm_before else None)
            != (entry.dpm_after.weaknesses.get(cid) if entry.dpm_after else None)
        )
        refused = sum(1 for o in entry.operations if not o.get("applied"))
        print(f"      {entry.session_id}  {entry.topic:34} "
              f"{moved} change(s), {refused} refused")
    print(f"  weaknesses    : {len(dpm.weaknesses)}")
    for cid, w in dpm.weaknesses.items():
        print(f"      {w.mastery:12} {w.strength:6} {cid}")
    print(f"  open doubts   : {len(tm.open_doubts)}")
    print(f"  mode          : {tm.teaching_style.current_mode}")
    print(f"  interests     : {', '.join(dpm.persona.interests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
