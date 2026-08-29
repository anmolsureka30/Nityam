# What changed since last night

Plain-language summary of the real work done on Nityam's backend, point by point.

---

## 1. Rebuilt how the tutor's helper agents work

**What changed:** Replaced the old single "Tutor Agent" (which handled memory, board-writing, quizzes, simulations, and textbook lookups all in one) with one small **Voice Agent** that just talks and listens, plus four separate helpers it can call on: a **Board Agent** (writes explanations/formulas), an **Artifact Agent** (builds simulations), a **Quiz Agent** (writes checkpoint questions), and a **Textbook Agent** (finds real textbook pages/figures). The Voice Agent never waits for a helper to finish — it hands off the work and keeps going.

**Why:** The old design made the tutor go quiet mid-sentence every time it needed to do something heavier, because it had to physically wait for that work to finish before it could speak again. It also meant every single turn carried the full weight of memory + board-writing + everything else, making it slower and more expensive on every exchange.

**Effect:** The tutor now hands off work in the background using a real feature of the voice model built for exactly this, so it doesn't get stuck waiting. This was the single biggest change of the night — around 25 separate commits, fully tested, reviewed, and already pushed live.

---

## 2. Fixed the Observatory dashboard not showing live sessions

**What changed:** Two separate bugs fixed: (1) the dashboard wasn't being told which session was live until *after* it ended, so it never showed anything in real time; (2) the dashboard's own frontend was running on a port its backend didn't trust, so the browser silently blocked every request.

**Why:** Both bugs made a real, running tutoring session invisible on the memory dashboard the whole time it was happening — you'd only see it after the fact.

**Effect:** Confirmed live — the dashboard now shows a session as soon as it connects, not after it closes.

---

## 3. Fixed the tutor going awkwardly silent after asking a helper for something

**What changed:** After a helper (like the Board Agent) finishes its work, the tutor used to also wait an extra 3+ seconds for an unrelated background task (refreshing its own notes about the student) before it was allowed to speak again. That extra wait is now done separately, in the background, instead of blocking the tutor's reply.

**Why:** You reported the tutor going quiet and feeling stuck after making a request — this was traced to real, measured delay in the logs, not just a feeling.

**Effect:** Every handoff to a helper now gets back to the tutor faster, by however long that background step used to take. Not yet re-tested live by you since the fix.

---

## 4. Made the tutor write on the board proactively, and made it stream in

**What changed:** The tutor's instructions were rewritten so that explaining something new *is* a board-write by default, instead of the tutor talking for a while and only writing something down if you explicitly asked. Also, when several things are written to the board at once, they now appear one at a time (about half a second apart) instead of all snapping into place instantly.

**Why:** You noticed the tutor would explain things purely out loud, several times over, before ever writing anything down — meaning you had to keep asking for things to be put on the board yourself instead of it happening naturally.

**Effect:** The board should now fill in as the tutor teaches, without you having to ask, and it should visually feel like it's being written rather than dumped. Not yet re-tested live by you since the fix.

---

## 5. Cleaned up unused tools, and added visibility into what the helpers actually do

**What changed:** Removed a handful of tools that were either never actually being used (checked against your real session logs, not guessed) or actively discouraged by the tutor's own instructions. Also added logging inside each helper agent so their internal actions (like looking up the student's notes, or searching the teacher's material) are now visible in the logs — before this, that was completely invisible even in a full session log.

**Why:** Extra unused tools add clutter and cost without helping, and not being able to see what a helper actually does internally made it impossible to judge whether it was working well.

**Effect:** Fewer, more purposeful tools. And going forward, the logs will actually show what each helper is doing behind the scenes, which is needed for judging future improvements.

---

## 6. Gave the Board helper access to the student's personal notes, and made end-of-session notes more detailed

**What changed:** The Board Agent (the one doing the actual teaching/writing) can now look up the student's known weak spots and teaching history before writing something — it couldn't before. Also, the automatic notes written about a student at the end of a session were pushed to be specific and quote real things the student said, instead of generic one-line labels.

**Why:** You asked that all the helpers have real access to the student's personal memory, and that what gets saved about a session be genuine, detailed context — not just keywords.

**Effect:** Confirmed live in a test run — a real end-of-session note now reads like *"Student asked 'why 45 degrees?' when discussing the optimal launch angle"* with a full, specific explanation attached, instead of a vague label.

---

## 7. Fixed textbook figure search so it works by describing the picture, not just its number

**What changed:** Every figure in the textbook index now carries its actual printed caption text (previously only its number and position were stored — no idea what it actually showed). Search now checks that caption text too, so a figure can be found by describing it rather than knowing its number.

**Why:** You pointed out that figure search only worked if you already knew the exact figure number, which isn't how a student actually asks for something.

**Effect:** Verified directly — asking for "the resultant vector after multiplying" now correctly finds Figure 3.3, with no number involved. Also caught and fixed a real bug this introduced along the way (a plain number search was briefly matching the wrong figure by accident) before it shipped.

---

*Everything above was checked against automated tests and, where noted, real test runs — not just claimed. Items 3 and 4 are implemented and tested but haven't been confirmed by you in a real live session yet.*
