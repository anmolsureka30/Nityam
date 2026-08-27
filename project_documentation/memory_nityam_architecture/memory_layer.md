# SMRITI — The Memory Layer (v2.0 — Google-managed storage)

**स्मृति · "that which is remembered"**

Supersedes v1.0's §5 (SQLite storage) and §6 (Memory Bank verdict). v1.0 kept the three
questions from v0.3 but answered them with typed, schema-validated JSON records over SQLite.
This version keeps the three questions, the four schemas, and the three-tier split
**completely unchanged** — the only thing that moves is where each tier physically lives:
Memorystore (Redis) for the workflow tier, Firestore for the episodic and long-term tiers,
Cloud Storage for binary artifacts. Nothing in §0–§4 below changed; §5 and §6 are the ones
that did. Full research, code, and the reasoning behind each service choice lives in the
companion document `google_cloud_storage_integration.md` — this file carries the short,
day-to-day version. The full v0.3 reasoning for markdown-first storage, and v1.0's SQLite
schema-design reasoning, are both preserved in git history if ever worth revisiting.

---

## 0. What memory has to answer

> **① Who am I teaching?** → Dynamic Personal Memory (DPM)
> **② What does the course say?** → Static Knowledge Grounding
> **③ What's the state of teaching them, right now?** → Teaching Memory

Three questions, three record types, plus one more that isn't really a "type" so much as the
evidence ledger the other three cite into: the **session log**.

**One memory layer, shared by every agent.** `VoiceAgent`, `TutorAgent`, and `ArtifactAgent`
all read through the same tool functions, backed by the same store. No agent gets its own
private copy or its own serialization format.

---

## 1. Three tiers

| Tier | What it is | Where it lives | Lifetime |
|---|---|---|---|
| **Workflow** | Current concept, current teaching mode, attempt count, the in-progress turn buffer | ADK `session.state` (live, in-process) + **Memorystore** (write-through mirror) | One session, ephemeral — Memorystore keys carry a safety-net TTL, not indefinite retention |
| **Episodic** | The turn-by-turn record of one session, closed out when it ends | `session_log` record, in **Firestore** | Forever, append-once |
| **Long-term** | Persistent, cross-session knowledge | `grounding_chunk` / `dpm_profile` / `teaching_memory` records, in **Firestore** | Forever, updated via validated operations |

The workflow tier is still ADK's native `session.state` for the live turn's own context-building
— that part is unchanged and still free. What's new in v2.0 is a write-through mirror to
Memorystore, so the tier is backed by a real Google-managed service rather than living only in
one process's RAM. See `google_cloud_storage_integration.md` §5 for why this is a mirror rather
than a session-service swap.

**Why episodic is its own tier, not folded into long-term:** every claim in `dpm_profile` and
`teaching_memory` cites a `session_id#turn`. That reference has to resolve against something.
The session log is that something — the evidence ledger, not just a transcript.

---

## 2. The four record types

Static Knowledge Grounding stays citation-heavy prose (it's quoting a lecture or a book — the
whole point is that it isn't paraphrased). DPM and Teaching Memory are structured JSON, because
they're mostly discrete facts (a mastery level, a doubt's status, which elements were used) that
a schema captures better than prose does. All four are real [JSON Schema](https://json-schema.org/)
documents — they validate every write, they aren't just documentation of intent.

### 2.1 `grounding_chunk` — shared, not per-student, read-only to the tutor

Written by Shruti ingestion and book ingestion. Retrieval fusion (graph + embedding) stays
Shruti's own implementation (see `sub_modules/shruti/docs/architecture.md`) — this is just the
record shape a `search_grounding()` call returns.

```json
{
  "$id": "https://nityam.dev/schemas/grounding_chunk.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "GroundingChunk",
  "description": "One retrievable, citable unit of static knowledge. Never written by the tutor.",
  "type": "object",
  "required": ["chunk_id", "source_type", "source_ref", "concept_ids", "text"],
  "properties": {
    "chunk_id":    { "type": "string" },
    "source_type": { "type": "string", "enum": ["lecture", "book"] },
    "source_ref":  { "type": "string", "description": "e.g. 'shruti:lec_41' or 'book:ch2'" },
    "location":    { "type": "string", "description": "e.g. '23:14' (timestamp) or 'p.42' (page)" },
    "concept_ids": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
    "text":        { "type": "string", "description": "Verbatim excerpt. Never paraphrased." }
  }
}
```

### 2.2 `dpm_profile` — one per student. *"Who am I teaching"* — persona-level, coarse.

```json
{
  "$id": "https://nityam.dev/schemas/dpm_profile.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DPMProfile",
  "description": "Persona, coarse per-concept mastery, and standing pedagogical reflections. Updated only via validated operations at session close — never rewritten wholesale.",
  "type": "object",
  "required": ["student_id", "persona", "weaknesses", "self_reflection"],
  "properties": {
    "student_id": { "type": "string" },
    "persona": {
      "type": "object",
      "properties": {
        "preferred_pace": { "type": "string", "enum": ["fast", "moderate", "deliberate"] },
        "language_mix":   { "type": "string" },
        "interests":      { "type": "array", "items": { "type": "string" } }
      }
    },
    "weaknesses": {
      "type": "object",
      "description": "Keyed by concept_id.",
      "additionalProperties": {
        "type": "object",
        "required": ["mastery", "strength", "evidence"],
        "properties": {
          "mastery":      { "type": "string", "enum": ["unknown", "misconceived", "partial", "known", "durable"] },
          "strength":     { "type": "string", "enum": ["weak", "strong"] },
          "evidence":     { "type": "array", "items": { "type": "string" }, "minItems": 1, "description": "session_id#turn refs" },
          "last_updated": { "type": "string", "format": "date-time" }
        }
      }
    },
    "self_reflection": {
      "type": "array",
      "description": "Tutor-authored pedagogical notes about this student (what works, what doesn't) — DeepTutor's D_r.",
      "items": {
        "type": "object",
        "required": ["note", "evidence", "status"],
        "properties": {
          "note":            { "type": "string" },
          "helpful_count":   { "type": "integer", "minimum": 0, "default": 0 },
          "harmful_count":   { "type": "integer", "minimum": 0, "default": 0 },
          "evidence":        { "type": "array", "items": { "type": "string" }, "minItems": 1 },
          "status":          { "type": "string", "enum": ["active", "superseded"] },
          "superseded_by":   { "type": ["string", "null"] }
        }
      }
    }
  }
}
```

### 2.3 `teaching_memory` — one per student. *"What's the state of teaching them, right now"* — operational, detailed.

Deliberately **not** duplicating doubt detail into `dpm_profile.weaknesses`, which only carries
a coarse flag. `weaknesses` answers "is this concept shaky" at a glance; `open_doubts` here is
the full record — manifestation, correct understanding, lifecycle — the tutor actually re-probes
against.

```json
{
  "$id": "https://nityam.dev/schemas/teaching_memory.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "TeachingMemory",
  "description": "Curriculum coverage, open doubts with lifecycle, current teaching mode.",
  "type": "object",
  "required": ["student_id", "syllabus", "covered", "open_doubts", "teaching_style"],
  "properties": {
    "student_id": { "type": "string" },
    "syllabus":   { "type": "array", "items": { "type": "string" }, "description": "concept_ids planned for this student" },
    "covered": {
      "type": "object",
      "description": "Keyed by concept_id.",
      "additionalProperties": {
        "type": "object",
        "required": ["status"],
        "properties": {
          "elements_used": { "type": "array", "items": { "type": "string" }, "description": "e.g. worked-example, diagram, quiz, artifact:<artifact_id>" },
          "taught_at":     { "type": "array", "items": { "type": "string" } },
          "status":        { "type": "string", "enum": ["in_progress", "covered"] }
        }
      }
    },
    "open_doubts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["concept_id", "doubt", "correct_understanding", "status", "evidence"],
        "properties": {
          "concept_id":            { "type": "string" },
          "doubt":                 { "type": "string", "description": "How the misconception manifests" },
          "correct_understanding": { "type": "string" },
          "status":                { "type": "string", "enum": ["active", "remediating", "resolved"] },
          "evidence":              { "type": "array", "items": { "type": "string" }, "minItems": 1 }
        }
      }
    },
    "teaching_style": {
      "type": "object",
      "required": ["current_mode"],
      "properties": {
        "current_mode": { "type": "string", "enum": ["socratic", "worked-example", "guided-practice", "direct"] },
        "notes":        { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

A doubt only moves `remediating → resolved` after evidence of a spaced re-check, not one
correct answer — the one piece of DeepTutor's evidence-gated lifecycle that survives the
simplification, because it's cheap (one enum field) and it's the difference between a real
signal and a guess.

### 2.4 `session_log` — episodic tier. One per session, written once at close.

```json
{
  "$id": "https://nityam.dev/schemas/session_log.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SessionLog",
  "description": "Every DPM/TeachingMemory evidence pointer ('session_id#turn') resolves against a turn here.",
  "type": "object",
  "required": ["session_id", "student_id", "started_at", "ended_at", "turns"],
  "properties": {
    "session_id": { "type": "string" },
    "student_id": { "type": "string" },
    "started_at": { "type": "string", "format": "date-time" },
    "ended_at":   { "type": "string", "format": "date-time" },
    "turns": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["turn", "role", "text"],
        "properties": {
          "turn":        { "type": "integer", "minimum": 1 },
          "role":        { "type": "string", "enum": ["student", "tutor"] },
          "text":        { "type": "string" },
          "concept_id":  { "type": ["string", "null"] },
          "artifact_id": { "type": ["string", "null"] }
        }
      }
    },
    "summary": { "type": "string" }
  }
}
```

---

## 3. The shared tool catalog

Every agent gets the same tool *objects* — not its own copy, not a re-implementation. This is
what "one memory layer, shared across agents" means concretely.

| Tool | Tier touched | Access | Called by |
|---|---|---|---|
| `search_grounding(query, top_k)` | long-term · grounding | read | `TutorAgent`, `ArtifactAgent` |
| `get_dpm(student_id)` | long-term · DPM | read | `TutorAgent`, `ArtifactAgent` |
| `get_teaching_memory(student_id)` | long-term · teaching memory | read | `TutorAgent`, `ArtifactAgent` |
| `log_turn(text, role, concept_id?, artifact_id?)` | workflow → buffer | write (RAM only) | `TutorAgent` |
| `log_artifact_evidence(event)` | workflow → buffer | write (RAM only) | `ArtifactAgent`, when an artifact reports an interaction event |
| `close_session(session_id)` | episodic + long-term | write | triggered at session end, not exposed to agents mid-conversation |

**Long-term memory is never written mid-session.** `dpm_profile` and `teaching_memory` are
read freely throughout, but the only path that updates them is `close_session`. This isn't a
Live-specific workaround — it's the same reasoning that held in v0.3: you don't know what a
turn meant until you see what followed it, and a file write inside a turn is latency you don't
need to pay. `log_turn` and `log_artifact_evidence` still append to the in-session buffer
(`session.state`) first — that part stays free — and, as of v2.0, additionally write through to
Memorystore (sub-millisecond, non-blocking; see `google_cloud_storage_integration.md` §5.3).
Both are `async` as of v2.0, which the ADK tool-dispatch path already supports natively.

---

## 4. Session close

Not a background agent — nobody has to be absent for this to run. It's the last step of the
*current* session's own lifecycle, triggered when the session ends:

1. **Deterministic.** Format the buffer into a `session_log` record. No model call.
2. **One LLM call.** Read the session log, propose validated operations against `dpm_profile`
   and `teaching_memory` — append a doubt, close a doubt (only with spaced-recheck evidence,
   never on one correct answer), update coverage, add a self-reflection note. Structured output,
   checked against the schemas in §2 before anything is written; malformed operations are
   dropped rather than applied.
3. **Write.** Persist the `session_log`, apply the validated operations.

---

## 5. Storage

**No local database, no SQLite, no Postgres — every persistent tier lives on a Google-managed
service.** Three services, one per concern, none of them overlapping in role:

| Record / tier | Backend | Collection / mechanism |
|---|---|---|
| `grounding_chunk` | Firestore | `grounding_chunks` collection, `concept_ids` array field + a native vector field (`embedding`) for semantic search |
| `dpm_profile` | Firestore | `dpm_profiles` collection, one document per `student_id` |
| `teaching_memory` | Firestore | `teaching_memories` collection, one document per `student_id` |
| `session_log` | Firestore | `session_logs` collection, one document per `session_id` |
| Workflow-tier turn buffer | Memorystore (Redis) | `session:<id>:turns` / `session:<id>:artifact_events` lists, write-through mirror of `session.state`, TTL'd |
| `ArtifactAgent` binary outputs | Cloud Storage | via ADK's built-in `GcsArtifactService` — not agent-callable tools, transparent runtime layer |

The four Pydantic models mirroring §2's schemas validate every write exactly as before — Firestore
documents hold the same JSON shape SQLite's payload column held, just without the extra narrow
relational columns SQLite needed for indexed lookups (Firestore's own field-level indexes and
`array_contains_any` cover `student_id`/`concept_id`/`status` queries natively).

**Why Firestore over the alternatives, and why Memorystore for the workflow tier specifically —
full research, exact per-file code, the embedding-dimension conflict that must be resolved before
`grounding_chunk` writes, auth/networking prerequisites, and every source consulted, are in
[`google_cloud_storage_integration.md`](google_cloud_storage_integration.md).** That document
also has the file-by-file migration plan: `app/memory/store.py` is the only file that needs a
real rewrite (function-for-function, same signatures); `app/memory/tools.py` gains a Memorystore
write-through call in two functions; `app/memory/ops.py` and `app/session_close.py` need no
changes at all.

---

## 6. Why not Memory Bank, Agent Search, or Vector Search

Checked directly against Google's current Vertex AI Memory Bank (`VertexAiMemoryBankService`),
not just the earlier Gemini Enterprise Agent Platform version: it still extracts and
*consolidates* facts via an LLM pass, and consolidation has no mechanism to carry a
`session_id#turn` evidence pointer through it. That's the one property every schema in §2 depends
on (§0's citation ledger), so `dpm_profile`/`teaching_memory` stay in Firestore rather than Memory
Bank, same conclusion as v1.0, now reconfirmed against the current product.

Two more services were newly evaluated for v2.0 and also declined: **Vertex AI Search / Agent
Search** (`VertexAiSearchTool`, Discovery Engine) is built for coarse, unstructured-document
retrieval via a managed GCS connector — the wrong grain for `grounding_chunk`, which Shruti
already chunks and tags with `concept_ids`/`location` precisely; routing it through Discovery
Engine would re-ingest content Shruti already processed, losing that metadata. **Vertex AI Vector
Search 2.0** has the same grain mismatch plus a KFP-pipeline/Collection infrastructure footprint
that Firestore's native vector field makes unnecessary at our chunk volume. Full reasoning and
sources for both: `google_cloud_storage_integration.md` §1.

The full six-service platform evaluation (RAG Engine, Vector Search, Skill Registry, Feedback
Service, Sandbox) that led to v1.0's original Memory Bank verdict is preserved in git history;
none of those conclusions changed, they're just not reproduced here since most of what they gated
(the skill-file teaching-mode system, background agents, Manim rendering) is itself deferred —
see `deferred.md`.

---

*v2.0. Supersedes v1.0 §5 (SQLite storage) and §6 (Memory Bank-only verdict) — §0–§4 unchanged.
v1.0 superseded v0.3 (`smriti_harness_integration.md`, `smriti_session_lifecycle.md`,
`nityam_error_registory.md`, and `google_platform_integration.md` are folded into this file and
`architecture.md`, or moved to `deferred.md`; recoverable in full via git history.)*
