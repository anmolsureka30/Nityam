# Deferred — out of scope for v1.0, not lost

Everything below was designed in earlier research passes, in real depth, and cut on purpose to
get to a first working build. Nothing here is wrong; it's just not this pass. Each line points
to where the full detail lived — recoverable via `git log -- project_documentation/memory_nityam_architecture/`
if it's ever needed again.

| Deferred | Was in | Why it's cut for now |
|---|---|---|
| FSRS spaced-repetition scheduling + `schedule` table | `memory_layer.md` v0.2–v0.3 §4, §7 | No re-testing/decay math in v1 — `teaching_memory.open_doubts[].status` is a simple lifecycle flag, not a memory-decay model |
| Background agents (Consolidator, Scheduler, PrepAgent, Nudge) + the wake-webhook pattern | `nityam_initial_architecture.md` §4.7 | Nothing runs when no student is present in v1. `close_session` (see `memory_layer.md` §4) covers the one write-back step that's actually load-bearing, and it's triggered by the session's own end, not a schedule |
| Teaching modes as `SKILL.md` files, progressive disclosure, `ModeGuard` tool-filtering, the scaffolding-collapse defense | `memory_layer.md` v0.2 §5 | Real, well-evidenced design (expertise reversal effect, adaptive fading, a named failure mode with a red-team protocol) — deferred because it's a second layer of infrastructure on top of a voice loop that doesn't exist yet. `teaching_memory.teaching_style.current_mode` keeps the concept as a plain field; `TutorAgent`'s instruction handles style directly for now |
| tldraw canvas + the Canvas Operation Protocol (`plan.set`, `derivation.step`, `diagram.svg`, etc.) | `nityam_initial_architecture.md` §3.4, §5 | Superseded by `sub_modules/artifact_generator`'s own IR → validate → HTML pipeline and `sub_modules/canvas`'s paged-notebook approach — a different, already-built frontend direction, not a gap |
| Multi-device advisory locking | `smriti_harness_integration.md` §9 | Real failure mode (silent memory corruption from two concurrent sessions), cheap to add (~10 lines), but not blocking a first build |
| Weekly curator / cross-student skill promotion | `memory_layer.md` v0.2 §7 | Depends on the `SKILL.md` teaching-mode system above and on `self_reflection` counters accumulating across many students first |
| Full Google-platform-service evaluation (Agent Registry, Feedback Service, Sandbox/Code Execution, hosted Skill Registry) | `google_platform_integration.md` | Most of what it gated (background agents, Manim rendering, the hosted skill catalog) is itself deferred above. The one conclusion that does carry forward — Memory Bank doesn't close the citation gap — is now in `memory_layer.md` §6 |
| `ContextCacheConfig` tuning (the 4,096-token floor, prefix ordering) | `smriti_harness_integration.md` §2 | Was needed because the old design put a ~40-skill catalog in every prompt. Nothing in v1 has a standing context large enough for caching to matter yet — see `architecture.md` §5 |
| ADK gotchas tied to the old topology (`SequentialAgent` + compaction crash, tool-scoping via `before_model_callback` instead of `before_agent_callback`) | `nityam_error_registory.md` E9, E19, E20 | Specific to the old `Investigate → Teach` `SequentialAgent` pipeline, which no longer exists in this design. Noted here only so nobody rediscovers a fix for a problem that isn't there anymore |
| Barge-in as a pedagogical signal, classified offline at write-back | `nityam_error_registory.md` E12 | Genuinely good, still true if/when barge-in handling is built — just not wired to anything in v1's minimal voice loop |

---

*If a deferred item becomes the next thing to build, re-read the source doc from git history before
redesigning from scratch — most of this was already researched carefully once.*
