DeepTutor : Personalized Agentic learning 
Challenges today :  
Conventional tutoring systems rely on static pre-training knowledge that lacks adaption to individual learners 
Also current RAG-augmented systems fall short in providing personalized guided feedback 

What deep tutor provides


Current LLM tutors remain session-bounded assistants. They adapt to the immediate prompt rather than to a persistent learner model and their functions are often implemented as isolated modules 

Iska impact : not just weaker personalization but a fragmented learning experience where pedagogical progress in one interaction rarely informs the next


What is actually needed?
A unified architecture rather than fragmented prompts.
must 
synchronize learner memory
task decomposition
tool usage across multimodal sessions
grounded with right content

DeepTutor grounds both problem solving and question generation in the learner’s knowledge base and diagnosed weaknesses


Benefits of an agentic system
Can maintain persistent state across extended horizons 
(Cultivating a dynamic learner model rather than treating interactions as an isolated event)
 Agents can orchestrate tools and sub-agents into structured workflows, enabling complex tasks like problem-solving, targeted exercise generation, and guided learning 
provides a scalable foundation for autonomous operation, allowing proactive behaviors to extend the system’s utility without re-engineering its core logic

Here is exactly what this is :::: 
Personalized Agentic Tutoring. 
A hybrid personalization engine synthesizes static knowledge grounding with a dynamic trace forest, distilling interaction history into a continuously refined learner profile. We establish a closed-loop pedagogy that interlocks citation-grounded problem solving with difficulty-calibrated question generation. This shared substrate further powers collaborative writing, multi-agent deep research, and interactive guided learning, ensuring that pedagogical progress transcends individual modalities.

Proactive Autonomous Companionship. 
Through TutorBot, Deeptutor operationalizes its tutoring core into autonomous agents equipped with extensible skills, multi-bot coordination, and context-preserving multi-channel gateways. This architecture transforms the system from a reactive interface into a proactive companion capable of autonomously initiating review sessions, synthesizing daily practice, and remediating diagnosed knowledge gaps across platforms.











This part is just for context for LLMs. In the future, do not read this entirely.
Some key important things / ADRs that are key takeaways 
The system is built upon a unified runtime where personalization, context propagation, and event-based streaming are natively shared across all workflows, spanning both reactive tutoring and proactive deployment.
Develop a good benchmark to robustly test agent responses based on your objective : For example – TutorBench,  a student-centric benchmark comprising university-level materials across five diverse disciplines. Each entry synthesizes a source-grounded learner profile with diagnosed knowledge gaps and a corresponding interactive tutoring task. A first person student simulator conducts multi-turn dialogues to rigorously assess adaptive pedagogical behaviors from the learner’s perspective
Design Principles 
A robust personalized tutoring system must be pedagogically deep to model individual learners, functionally broad to span diverse knowledge modalities, and architecturally open to accommodate emerging interfaces and autonomous behaviors. While addressing these demands in isolation is straightforward, the primary challenge lies in integrating them without letting the architecture degenerate into a fragmented collection of point solutions. We consolidate these requirements into three guiding design principles. 
Principle 1: Shared Personalization as the Unifying Substrate. 
Systems often treat problemsolving, question generation, and research as decoupled states, causing the tutor to lose pedagogical context when a learner switches tasks. Deeptutor mitigates this by routing all workflows through a centralized personalization engine comprising shared knowledge bases, the trace forest, and a unified learner profile D. Consequently, a weakness identified during problem-solving directly shapes the subsequent guided session, while insights from research refine the parameters of future question generation. The learner interacts with a cohesive, evolving intelligence rather than a fragmented toolkit.
Principle 2: Reusable Agentic Workflows over Monolithic Features. 
Architectures that hardcode pedagogical behaviors are inherently brittle and scale poorly. We instead adopt an agent-native design where tutoring functions from writing assistance to deep research are implemented as composable workflows atop a shared runtime for retrieval, reasoning, and personalization. Because these workflows inherit standardized context-propagation and delivery mechanisms by construction, extending the system with new modalities does not require re-engineering the underlying stack. 
Principle 3: Proactive Agency with Unified Context.
 Autonomy provides value only if the learner’s state remains coherent across all entry points. In Deeptutor, proactive behavior is an architectural extension of the tutoring substrate rather than a separate product surface. The tutoring dimension formalizes the learner model and workflows, while the proactive dimension leverages them for autonomous, multi-platform engagement. Our objective is autonomy without context fragmentation: whether a student solves a problem via a web interface or receives a review reminder via Telegram, they engage with a singular, context-unified tutor
Agent-Native Infrastructure The design principles articulated above dictate a core implementation requirement: every workflow and interaction entry point must operate within a unified, shared runtime. This subsection details how DEEPTUTOR’s infrastructure operationalizes this requirement to ensure architectural consistency. Common Runtime for Extensible Workflows. To avoid redundant implementation across diverse interfaces or pedagogical tasks, DEEPTUTOR centers execution on a uniform runtime that provides a suite of foundational services: retrieval-augmented generation (RAG), agentic reasoning, sandboxed code execution, memory access, and multi-agent orchestration. All tutoring behaviors—ranging from multi-stage problem solving to parallel deep research—are implemented as composable workflows atop this layer. By design, these workflows inherit standardized context-propagation mechanisms and a unified streaming protocol, ensuring functional parity across the system. Unified Context and Event-Driven Streaming. 
A system-wide context structure encapsulates the complete state of each interaction turn, including session metadata, conversation history, tool registries, knowledge-base references, and the personalization signal Cmem. This ensures that every agent, regardless of its specific entry point, operates on a coherent and synchronized learner model. Furthermore, all agent outputs are emitted as strongly-typed events via an asynchronous event bus. This decouples the core agent logic from the delivery layer, enabling diverse consumers to consume and render the same telemetry stream without custom adaptation. Convergent Entry Points. A critical architectural consequence of this design is that every entry point including the web interface, CLI, programmatic SDK, and TUTORBOT (§5) converges on a single orchestrator. This convergence ensures that both the reactive tutoring pipelines and the proactive autonomous components described in the subsequent sections execute on the identical infrastructure, anchored by the same continuously evolving learner model.
____________________________________________________________

Important thing to note 

All agent outputs are emitted as strongly-typed events via an asynchronous event bus. This decouples the core agent logic from the delivery layer, enabling diverse consumers to consume and render the same telemetry stream without custom adaptation

Nityam — Technical Architecture & Build Document
Google AI Hackathon · Autonomous Collaborative Learning Agent Version 0.1 · draft for review · Arnav & Anmol

0. How to read this document
This is a decision document, not a spec you implement top-to-bottom. It compiles four bodies of research — the DeepTutor system and paper, the tldraw SDK and its agent tooling, the Google ADK / Gemini stack as it stands in August 2026, and the learning-science layer (FSRS, knowledge tracing, LearnLM) — into one buildable architecture.
Read Parts 1–3 to agree on what we're building. Read Parts 4–7 for how. Part 9 is the actual build plan; Part 10 is what will bite us.
Open decisions requiring sign-off before we write code are collected in §0.1. Everything else in this doc assumes those defaults.
0.1 Decisions needing your call
#
Decision
Recommendation
Why it matters
D1
Canvas engine: tldraw vs. Excalidraw vs. custom
tldraw
Best agent tooling in the ecosystem. But it needs a license key in production (§5.7). Real risk.
D2
Voice: Gemini Live native audio vs. STT→LLM→TTS pipeline
Live API (native audio)
Barge-in and sub-second latency are the demo. But Live models are a separate model family from Gemini 3.5 Flash (§4.3).
D3
Subject scope for the demo
One chapter, one subject (Class 9 Maths — Polynomials, or MM331 Stress & Strain)
Depth beats breadth in a 3-minute demo. A shallow multi-subject demo reads as a wrapper.
D4
Grounding source
Gemini File Search for v1, hybrid graph+vector later
File Search is RAG-as-a-service with citations. Zero infra. DeepTutor's dual-index is better but is a week of work.
D5
Frontend transport
AG-UI (CopilotKit) for agent events + raw WebSocket for audio
AG-UI is an officially documented ADK integration and gives us typed events → canvas ops for free.
D6
Do we build the teacher dashboard for the hackathon?
No — stub it
The deck's teacher side is the business wedge, not the technical wedge. One static screenshot in the demo.
D7
Persistence
Cloud SQL / Postgres via DatabaseSessionService
Required for the background-agent story to be real rather than simulated.


1. What we are building
1.1 One paragraph
Nityam is a voice-first learning partner that teaches on an infinite canvas. The student talks; the tutor talks back and simultaneously draws — diagrams, worked steps, animations, interactive widgets — onto a canvas that accumulates into that session's notes. Underneath, a persistent learner model tracks not just what the student got wrong but the misconception behind it, and whether it is still active. Between sessions, a background agent wakes on a schedule, re-checks decayed concepts, prepares the next session, and pushes a review nudge — without the student having to open the app.
1.2 How this maps to the hackathon brief
The brief asks for two things. Here is exactly how we hit each.
"Beyond standard chat loops — runs asynchronously in the background, handles heavy lifting of complex workflows, or dynamically manipulates data pipelines and representations."
Brief clause
Our implementation
Runs asynchronously in the background
ADK durable state machine + DatabaseSessionService + webhook/cron resumption via runner.run_async(state_delta=...). The Nightly Consolidator and the Review Scheduler are real background agents, not cron jobs pretending. (§4.7)
Handles heavy lifting of complex workflows
Multi-agent pipeline: SequentialAgent(Investigate → Plan → Teach) , ParallelAgent fan-out for memory consolidation, LoopAgent for generator↔critic question validation. (§4.2)
Dynamically manipulates data pipelines and representations
This is the canvas. The agent chooses the representation — SVG diagram, Manim-style animation, interactive HTML widget, worked algebra, concept graph — as a pedagogical action, then emits typed canvas operations that mutate the tldraw store live. (§3.4, §5)

"Collaborative Partner: leads the way and takes notes. Asks clarifying questions, guides step-by-step, captures feedback, constantly adapts."
Brief clause
Our implementation
Leads the way
A Plan shape is placed on the canvas at session start. The tutor drives through it; the student can drag/reorder/reject steps. The tutor is not waiting to be asked. (§6.1)
Takes notes
The canvas is the notes. Every generated artifact persists as a tldraw shape in a session snapshot. Plus an explicit write_note tool for the tutor's own margin annotations. (§6.3)
Asks clarifying questions
ask_user as a first-class tool that pauses the turn — modelled on DeepTutor's implementation and ADK's LongRunningFunctionTool + request_confirmation. (§6.2)
Guides step-by-step
Socratic gating: question → hint → full explanation, gated on a genuine attempt. Enforced structurally, not just prompted. (§6.4)
Captures feedback
Two channels: implicit (canvas interactions, response latency, retries, barge-ins) and explicit (a Feedback shape — "too fast / too slow / I don't get it" — pinned to the canvas). Both write to the learner model. (§6.5)
Constantly adapts
The learner model is injected into every agent's instruction via ADK state templating, so adaptation is structural rather than a prompt suggestion. (§7)


2. What DeepTutor teaches us
2.1 What it is, factually
DeepTutor is an open-source agentic tutoring framework from the HKU Data Intelligence Lab (HKUDS), Apache-2.0, ~30k GitHub stars, paper at arXiv:2604.26962. Python 3.11+ backend, Next.js 16 frontend. It was rewritten in early 2026 as an "agent-native architecture" (~200k lines) around a Tools + Capabilities plugin model.
It matters to us because it is the most complete public answer to the question "what does a tutoring system look like if you take agents seriously?" — and because its paper contains the ablation study that tells us which parts actually carry the weight.
2.2 The eight ideas worth stealing
① The Hybrid Personalization Engine — two kinds of context, always. Every agent step is conditioned on two separately-budgeted context blocks:
C_rag — Static Knowledge Grounding (SKG): what the course teaches. Documents decomposed into atomic content units, indexed twice (a knowledge graph G for structural relations, a dense embedding index B for semantic similarity), retrieved in parallel and fused with reciprocal rank fusion, deduplicated, truncated to budget.
C_mem — Dynamic Personal Memory (DPM): how this learner has engaged with it.
The total token budget is dynamically partitioned between the two. This is the single most important structural idea in the paper. Most tutoring apps have one context blob; DeepTutor has two with a negotiated split.
② The Trace Forest — memory as a searchable tree, not a summary. Each completed tutoring interaction becomes a tree, not a paragraph:
Level 1 — session-level input + global summary
Level 2 — intermediate planning units from task decomposition
Level 3 — fine-grained execution records: tool outputs, evidence, validation outcomes
Every node carries a dense embedding. Retrieval budget is allocated proportionally across levels so the agent gets both broad session context and fine-grained precedents.
③ TraceToolkit — memory is a tool, not a prefix. The forest is exposed programmatically with three operations: SearchTrace (semantic ANN retrieval), ListTraces (filtered enumeration by time / task type / topic), ReadNodes (full content + ancestor paths). Agents query their memory at the resolution they need rather than receiving a fixed dump.
④ The learner profile is three views, not one score. D = (D_s, D_w, D_r):
D_s — session history: topics covered, solving paths, performance trends
D_w — evidence-backed inventory of recurring confusions, wrong-answer patterns, and active vs. resolved knowledge gaps
D_r — pedagogical self-reflections that guide future interactions
Critically, the profile is built by three specialized memory agents that actively query the TraceToolkit — retrieving related prior sessions, inspecting fine-grained nodes, comparing latest behaviour against cross-session patterns — rather than by summarizing the last transcript. Profile construction is a tool-mediated analysis procedure.
⑤ Role-specific profile excerpting. Different slices of D route to different agents: the planner gets D_s + D_w; the writer gets D_r; question-generation agents get D_w plus historical question patterns. This cuts irrelevant context per role. Cheap to implement, disproportionately effective.
⑥ Investigate → Solve → Write, as three separate stages. Prior tool-augmented agents (ReAct-style) fold planning, retrieval, and composition into one loop. DeepTutor separates them because "thorough investigation and personalized presentation compete for the same context window."
Stage ① Investigate before plan: decompose the question into meta-questions, gather evidence across the KB, the trace forest, and tools — then commit to a plan of annotated sub-goals. This produces sub-goals specific to the learner's actual gaps ("review chain rule in trigonometry") instead of generic ones ("review calculus").
Stage ② Step-by-step guided solving, with three context-management mechanisms: self-notes (each step distils to a concise takeaway that later steps reference instead of verbose intermediates), hierarchical compression (completed sub-goals progressively summarized into digests), and adaptive replanning (revise remaining sub-goals while preserving completed work).
Stage ③ Evidence-based iterative writing: extract structured evidence from the scratchpad, construct the answer through successive refinement, reconcile conflicting findings. C_mem steers depth and tone to the learner's Zone of Proximal Development. Every externally grounded claim carries a traceable citation.
⑦ Generator and validator must not share a reasoning chain. For question generation, a structurally separated validator applies LLM-based verification (template alignment, factual correctness, pedagogical soundness) plus sandboxed code execution for computational items. The paper is explicit about why: because the validator shares no reasoning chain with the generator, it must independently verify correctness, reducing self-confirming errors that self-evaluation misses. Failed pairs get structured diagnostic feedback and are regenerated.
⑧ Bidirectional task coupling is the whole point. Weaknesses diagnosed during tutoring propagate to D_w and directly shape which questions are generated next; performance on those questions refines D_s and D_r, improving future explanations. This operationalizes formative assessment. Diagnose and Practice are one loop, not two features — which is exactly the claim already on slide 5 of the Nityam deck.
2.3 What the evidence actually says
From the paper's evaluation on TutorBench (30 knowledge bases across five disciplines → 90 learner profiles → 270 interactive tasks, judged by a first-person student simulator against ten rubric dimensions):
Finding
Number
What it means for us
DeepTutor vs. baselines (Naive / CoT / Self-Refine / ReAct on the same backbone + same RAG)
+10.76% overall quality
The four baselines cluster tightly. Adding CoT or ReAct to the same model does not produce learner-adaptive behaviour. Architecture is doing the work, not prompting.
Largest tutoring-side gains
Vividness, Personalization, Logical Depth
Vividness = "rich presentation through multiple representations beyond plain prose." This is our canvas. The single biggest measured win in the literature is the thing we are making our core UX.
Solver-only transfer (personalization disabled) across 5 backbones
+25.7% to +32.0%, avg +29.4%
The investigate–solve–write scaffold generalizes beyond tutoring. Safe to build on.
Ablation: remove SKG
Groundedness drops most, then Source Faithfulness, then Cross Concept
SKG anchors what the tutor says
Ablation: remove DPM
Personalization and Fitness drop most sharply
DPM shapes how it adapts
Weakest dimension overall
Groundedness (practice questions traceable to source)
Generating correct items is easier than making every item traceable. Budget effort for citations.
Human↔LLM judge agreement
Pearson r = 0.82, p = 0.0038
Rubric-based LLM judging is defensible for our own eval (§8).

The honest caveat the paper states: the multi-stage pipeline trades additional inference cost for controllability. And all system extensions (Book Engine, TutorBot) are presented as architectural instantiations — their effect on real retention is untested.
2.4 What we deliberately do differently
DeepTutor is a reactive text workspace with a proactive bolt-on. We invert that. Five deliberate divergences:
Dimension
DeepTutor
Nityam
Rationale
Primary modality
Text chat, markdown, side-panel visualizations
Voice in / voice + canvas out
The deck's whole thesis. Also: a 14-year-old will talk before they will type.
Visualization
A capability you invoke ("Visualize", "Math Animator")
The default output surface. Every explanation renders.
Vividness is the top measured gain. Make it structural.
Notes
Co-Writer, a separate markdown editor
The canvas is the notes — no separate artifact
One less thing to sync, one less thing to abandon
Grounding
Your uploaded documents
The lesson the student's own teacher gave that day
Our actual differentiation vs. every other AI tutor
Proactivity
TutorBot heartbeat, multi-channel IM
Background agent tied to a memory-decay schedule (FSRS), not a fixed heartbeat
Review timing should be derived from the memory model, not a cron interval

Two implementation ideas from the repository (not the paper) also worth taking:
Inspectable, file-backed three-layer memory with provenance: L1 append-only event traces (trace/<surface>/<date>.jsonl), L2 per-surface curated facts, L3 cross-surface synthesis — where L2 cites L1 and L3 cites L2, "so nothing in your profile is unaccountable." For an education product sold to schools and parents, auditable personalization is a feature, not an implementation detail. A "why does Nityam think I'm weak at this?" button that traces to the exact moment is a demo beat.
ask_user as a turn-pausing tool. Not a prompt instruction to ask questions — an actual tool that suspends the agent loop.

3. Nityam architecture
3.1 The five planes
┌─────────────────────────────────────────────────────────────────┐
│  PRESENTATION PLANE                                             │
│  tldraw infinite canvas  ·  voice I/O  ·  session timeline      │
└────────────▲──────────────────────────────────┬─────────────────┘
             │  typed canvas ops (AG-UI events) │  audio (PCM 16k)
             │                                  ▼
┌────────────┴──────────────────────────────────────────────────────┐
│  ORCHESTRATION PLANE  —  Google ADK Runner                        │
│                                                                    │
│   ┌──────────────┐   ┌───────────────┐   ┌──────────────────┐    │
│   │ VoiceAgent   │──▶│ TutorPipeline │──▶│ CanvasDirector   │    │
│   │ (Live, bidi) │   │ (Sequential)  │   │ (emits ops)      │    │
│   └──────────────┘   └───────────────┘   └──────────────────┘    │
│          │                   │                                     │
│          │           ┌───────┴────────┐                            │
│          │           │ DiagnoseAgent  │  QuestionLoop (Loop)       │
│          │           └────────────────┘  gen ⇄ critic              │
└──────────┼─────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────┐   ┌────────────────────────────────┐
│  MEMORY PLANE                │   │  GROUNDING PLANE               │
│  session.state (hot)         │   │  Gemini File Search store      │
│  LearnerProfile (D_s/D_w/D_r)│   │  per-chapter, cited            │
│  TraceStore (L1/L2/L3)       │   │  + Google Search (fallback)    │
│  FSRS scheduler              │   │                                │
└──────────────────────────────┘   └────────────────────────────────┘
           ▲
┌──────────┴──────────────────────────────────────────────────────┐
│  BACKGROUND PLANE  (no user present)                            │
│  Consolidator · Scheduler · PrepAgent · NudgeAgent              │
│  Cloud Scheduler → webhook → runner.run_async(state_delta=…)    │
└─────────────────────────────────────────────────────────────────┘
3.2 The core loop (one turn)
Student speaks → PCM audio → LiveRequestQueue.send_realtime()
Live model transcribes, decides intent, may call a tool
If the turn needs teaching: TutorPipeline runs on Gemini 3.5 Flash
InvestigateAgent → queries File Search + TraceStore, writes plan to state
TeachAgent → produces a response plan: what to say, what to draw
CanvasDirector → emits canvas ops as typed events
Ops stream to the frontend; tldraw shapes appear in step with the speech
Student responds / interacts with a shape → interaction event → session.state
after_agent_callback appends an L1 trace record
On session end: ConsolidatorAgent (background) updates D_w, schedules FSRS reviews
3.3 The Learner Model (the spec that matters most)
This is the artifact everything else reads from. Get this right and the rest is plumbing.
# schema/learner.py  — persisted in session.state under key "learner"

class MasteryState(str, Enum):
    UNKNOWN         = "unknown"          # never assessed
    MISCONCEIVED    = "misconceived"     # holds an active wrong model
    PARTIAL         = "partial"          # right idea, unreliable execution
    KNOWN           = "known"            # demonstrated, not yet durable
    DURABLE         = "durable"          # survived a spaced re-check

class Misconception(BaseModel):
    id: str
    concept_id: str                      # e.g. "quad.factor_vs_expand"
    statement: str                       # "treats factoring as distributing"
    manifestation: str                   # how it shows up in student work
    correct_understanding: str           # the reference, never shown as answer
    state: Literal["active", "remediating", "resolved"]
    evidence: list[TraceRef]             # ← L1 pointers. non-negotiable.
    first_seen: datetime
    last_probed: datetime
    probe_count: int
    resolved_at: datetime | None

class ConceptCard(BaseModel):
    concept_id: str
    mastery: MasteryState
    # FSRS memory state
    difficulty: float                    # D, 1–10
    stability: float                     # S, days until R decays 100%→90%
    last_review: datetime
    due: datetime
    lapses: int

class LearnerProfile(BaseModel):
    # D_s — session view
    topics_covered: list[str]
    performance_trend: list[SessionScore]
    preferred_pace: Literal["fast", "moderate", "deliberate"]
    language_mix: str                    # "hi-en-code-mixed" | "en" | "hi"

    # D_w — weakness view  ← the money object
    misconceptions: list[Misconception]
    concept_cards: dict[str, ConceptCard]
    recurring_error_patterns: list[ErrorPattern]

    # D_r — pedagogical reflection view
    what_works: list[str]                # "responds to visual proofs"
    what_fails: list[str]                # "shuts down on 3+ step symbolic chains"
    tutor_notes: list[str]
Three design rules, enforced:
Every claim in D_w carries evidence: list[TraceRef]. No un-sourced assertions about a child's ability. This is DeepTutor's L2-cites-L1 principle, and it is the difference between a learner model and a horoscope.
Misconceptions have a lifecycle, not a boolean. active → remediating → resolved, with probe_count. A gap isn't closed because the student got one question right; it's closed when it survives a spaced re-probe. This is what "It remembers where the confusion started, and keeps re-checking it until the gap is closed" (deck, slide 7) actually means in code.
MasteryState and FSRS (D, S) are separate. Mastery is pedagogical state; D/S is memory decay. A student can be KNOWN and still due for review. Conflating them is the most common mistake in this product category.
3.4 The Canvas Operation Protocol
The agent never touches tldraw directly. It emits typed ops; a client-side reducer applies them. This is the "dynamically manipulate representations" clause of the brief, made concrete.
type CanvasOp =
  | { op: 'plan.set';      steps: PlanStep[] }
  | { op: 'plan.advance';  stepId: string; status: 'active'|'done'|'skipped' }
  | { op: 'concept.card';  conceptId: string; title: string; body: string; mastery: MasteryState }
  | { op: 'derivation.step'; line: string; latex?: string; annotation?: string; highlight?: string[] }
  | { op: 'diagram.svg';   svg: string; caption: string }          // model-generated SVG
  | { op: 'widget.html';   html: string; title: string; h: number } // sandboxed iframe
  | { op: 'image.gen';     assetUrl: string; alt: string }          // Nano Banana output
  | { op: 'quiz.mcq';      stem: string; options: string[]; correct: number; conceptId: string }
  | { op: 'note.write';    text: string; anchorTo?: ShapeRef }
  | { op: 'gap.flag';      conceptId: string; misconception: string }
  | { op: 'camera.focus';  target: ShapeRef | Bounds }
  | { op: 'connect';       from: ShapeRef; to: ShapeRef; label?: string }
Design notes, taken from tldraw's own agent guidance:
Ops are declarative and idempotent-ish, keyed by a client-generated id. Retries don't duplicate shapes.
The model outputs a simplified schema, not raw tldraw records. tldraw's own docs say bluntly: "You may find that models are bad at generating changes directly" — their example project uses a simplified format and parses it into real changes. We do the same.
Ops stream. Each op applies when it finishes streaming, so the canvas fills in while the tutor is still speaking. This is the demo moment.
Every op carries conceptId where applicable. That's how a canvas interaction (student clicks the wrong MCQ option) becomes a learner-model update without a separate telemetry path.

4. Google ADK implementation
4.1 Why ADK, and what version
ADK is Google's open-source, code-first agent framework — Python, TypeScript, Go, Java. Optimized for Gemini, model-agnostic via LiteLLM. It gives us, out of the box, the four things that would otherwise eat the whole hackathon: bidirectional streaming to the Live API, durable sessions, multi-agent orchestration primitives, and one-command deploy.
Use Python (richest surface, all the streaming docs are Python-first). Pin your ADK version — the project is iterating fast and internals change between releases.
4.2 Agent topology
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent, LoopAgent
from google.adk.models import Gemini

REASONER = "gemini-3.5-flash"      # hackathon-mandated headline model
FAST     = "gemini-3.5-flash-lite" # cheap sub-agents: classification, routing

# ── Stage ①: Investigate before planning ────────────────────────────
investigate = LlmAgent(
    name="InvestigateAgent",
    model=Gemini(model=REASONER),
    instruction="""You diagnose before you teach.

Learner profile (weaknesses): {learner_weaknesses}
Session so far: {session_summary}
Current concept: {concept_id}

Decompose the student's question into meta-questions. Gather evidence with
your tools: search the chapter for the source material, search the trace
store for how THIS student has handled related concepts before.

Do NOT produce an explanation. Produce a diagnosis and a plan of concrete,
annotated sub-goals specific to this student's actual gaps.
Bad:  "review polynomials"
Good: "student factors by distributing; re-derive (x+3)^2 by area model first"
""",
    tools=[file_search_tool, search_trace, list_traces, read_nodes],
    output_key="tutoring_plan",
)

# ── Stage ②+③: Teach, with the canvas as co-output ──────────────────
teach = LlmAgent(
    name="TeachAgent",
    model=Gemini(model=REASONER),
    instruction="""You are Nityam, a tutor who thinks on a canvas.

Plan: {tutoring_plan}
Learner reflections (what works for this student): {learner_reflections}
Pace: {preferred_pace}

Rules:
1. ASK BEFORE YOU TELL. Lead with a question and a hint. Only open the full
   explanation after a genuine attempt. Call `check_attempt` to decide.
2. EVERY explanation gets a visual. Choose the representation deliberately —
   diagram for structure, animation for process, widget for parameters,
   derivation for symbolic work. Call the matching canvas tool.
3. Speak in the student's language mix ({language_mix}). Do not translate
   technical terms the teacher used in English.
4. Cite the chapter for factual claims. Uncited claims are bugs.
5. When you detect a wrong mental model, call `flag_gap` immediately.
""",
    tools=[
        draw_diagram, draw_derivation, render_widget, generate_image,
        emit_quiz, write_note, flag_gap, focus_camera,
        ask_user,            # ← pauses the turn
        check_attempt,
    ],
    output_key="teach_result",
)

tutor_pipeline = SequentialAgent(
    name="TutorPipeline",
    sub_agents=[investigate, teach],
)

# ── Question generation: generator ⇄ critic, structurally separated ──
q_gen = LlmAgent(
    name="QuestionGenerator", model=Gemini(model=REASONER),
    instruction="""Generate ONE practice item targeting {target_gap}.
Ground the stem, key and explanation in {chapter_context}. Calibrate
difficulty to {mastery_level}.""",
    output_key="candidate_item",
)

q_critic = LlmAgent(
    name="QuestionValidator", model=Gemini(model=REASONER),
    instruction="""You did NOT write this item. Verify independently.
Item: {candidate_item}
Check: (a) factual correctness against {chapter_context}
       (b) does it actually probe {target_gap}, or something adjacent?
       (c) distractor plausibility  (d) single unambiguous key
Set `validated: true` ONLY if all pass. Otherwise return structured
diagnostics for regeneration.""",
    output_key="validation",
)

question_loop = LoopAgent(
    name="QuestionLoop", sub_agents=[q_gen, q_critic], max_iterations=3,
)
Two ADK mechanics doing real work here:
output_key writes to shared session.state, and {placeholders} in an instruction are filled from state at run time. That's how tutoring_plan flows from Investigate to Teach without an explicit message pass, and how the learner profile is injected structurally into every agent.
LoopAgent with a separate critic agent gives us DeepTutor's structurally-separated validator almost for free. The critic has its own instruction and its own context — it does not inherit the generator's reasoning chain.
4.3 The voice loop (and the model-family trap)
⚠️ Critical fact, flag this early: you cannot run native voice on gemini-3.5-flash. The Live API is a separate model family (gemini-3.1-flash-live-preview and siblings) speaking a stateful WebSocket protocol. The hackathon's "Gemini 3.5 Flash" requirement is satisfied by using it as the reasoning and generation model for every tutoring agent — which is the intellectually honest reading anyway, since that's where the agentic work happens.
Live API specs to design against:
Input: raw 16-bit PCM, 16 kHz, little-endian. Images ≤ 1 FPS. Text.
Output: raw 16-bit PCM, 24 kHz, little-endian.
Transport: stateful WebSocket (WSS). 70 languages. Barge-in supported.
On Gemini 3.1 Live models: proactive audio and affective dialog are not supported — remove those config keys. Use thinkingLevel (minimal/low/medium/high), not thinkingBudget. Default minimal for lowest latency.
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types

run_config = RunConfig(
    streaming_mode=StreamingMode.BIDI,
    response_modalities=["AUDIO"],            # exactly one modality per session
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    session_resumption=types.SessionResumptionConfig(),
)

# ONE fresh queue per streaming session. Never reuse — the close signal
# persists in the queue and will terminate the next session's sender loop.
queue = LiveRequestQueue()

async for event in runner.run_live(
    user_id=uid, session_id=sid, live_request_queue=queue, run_config=run_config
):
    await fanout(event)   # → audio to speaker, transcript to UI, ops to canvas
Hard-won operational notes from the docs and community:
Gotcha
Handling
One LiveRequestQueue per run_live(). Reuse corrupts state.
Create per WebSocket connection; close on disconnect.
Sub-agents + live → ADK auto-enables input/output transcription regardless of your config (needed for agent transfer).
Don't fight it. Budget the tokens; use the transcripts for the L1 trace.
Sessions >15 min need context window compression (sliding window).
Enable it. A tutoring session will exceed this.
Connection drops.
session_resumption — tokens valid 2h after last termination.
Client-side WebSocket exposes your key.
Ephemeral tokens, never raw API keys in the browser.
send_realtime() for continuous input; send_client_content() only to seed history.
Wire them separately from the start.
Send audioStreamEnd when the mic pauses.
Flushes cached audio.
One server event can contain multiple parts (audio + transcript together).
Iterate all parts. This one bites everyone.

4.4 Tool catalog
Tool
Kind
Purpose
file_search
Gemini File Search
Grounded retrieval over the chapter, returns citations
search_trace / list_traces / read_nodes
Function
TraceToolkit — query the learner's own history
draw_diagram
Function → canvas op
Model emits SVG; validated, then op-emitted
draw_derivation
Function → canvas op
Step-by-step symbolic work with LaTeX + annotations
render_widget
Function → canvas op
Self-contained HTML/JS in a sandboxed iframe shape
generate_image
gemini-3.1-flash-image-preview (Nano Banana 2)
Real-world imagery, labelled figures
emit_quiz
Function → canvas op
Places an interactive MCQ shape
flag_gap
Function → state
Writes a Misconception with trace evidence
write_note
Function → canvas op
The tutor's margin notes
check_attempt
Function
Gates the Socratic ladder (§6.4)
ask_user
LongRunningFunctionTool
Pauses the turn for a clarifying question
schedule_review
Function → FSRS
Enqueues a spaced re-probe

On render_widget and code execution: the safest hackathon path is to have Gemini 3.5 Flash write self-contained HTML that renders in an iframe with sandbox="allow-scripts" — no server-side execution needed. If you want Manim-style animations, that requires a real sandbox (ADK's BuiltInCodeExecutor, or a runner sidecar as DeepTutor does with Dockerfile.runner). Recommendation: skip Manim for the hackathon. HTML/CSS/SVG animation gets you 90% of the visual impact at 5% of the infrastructure.
4.5 State, sessions and memory services
Layer
ADK service
Contents
Lifetime
Hot state
session.state
Current concept, plan, attempt count, canvas shape refs
One session
Durable session
DatabaseSessionService (SQLite local → Cloud SQL prod)
Full event history, checkpointed on every tool call
Forever
Long-term memory
VertexAiMemoryBankService or custom TraceStore
L1/L2/L3 trace hierarchy, LearnerProfile
Forever
Artifacts
ArtifactService (GCS)
Generated images, canvas snapshots, exported notes
Forever

Recommendation: build the TraceStore yourself rather than using Memory Bank. Memory Bank auto-consolidates and gives you opaque memories; we specifically want DeepTutor's inspectable, provenance-carrying three-layer structure, because "trace this claim back to the moment it happened" is a demo beat and a trust feature. It's ~200 lines over Postgres + pgvector.
Switching to durable sessions is one line, and it's what makes the background story real:
from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    session_service_uri="postgresql+asyncpg://…/nityam",  # sqlite+aiosqlite:// locally
)
Every ToolContext.state write is then durably persisted. Kill the server mid-session, restart, and the agent resumes from the correct checkpoint.
4.6 Callbacks and plugins — the control plane
ADK gives two extension levels: callbacks (attached to one agent/tool) and plugins (registered once on the Runner, apply globally). The return contract is the same and it's the important part: return None to continue, return a value to short-circuit and replace the default behaviour.
Lifecycle order: on_user_message → before_run → before_agent → before_model → [LLM] → after_model → before_tool → [tool] → after_tool → after_agent → on_event → after_run
Our plugins:
class TracePlugin(BasePlugin):
    """L1 capture. Every event → append-only trace record."""
    async def on_event_callback(self, *, invocation_context, event):
        await trace_store.append_l1(session_id=..., event=event)

class PedagogyGuardPlugin(BasePlugin):
    """Structural enforcement of ask-before-tell."""
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        if tool.name == "reveal_full_explanation":
            if tool_context.state.get("attempts_this_concept", 0) < 1:
                return {  # short-circuits the tool
                    "blocked": True,
                    "reason": "No attempt recorded. Offer a hint first.",
                }
        return None

class SafetyPlugin(BasePlugin):
    """Age-appropriate content gate + PII scrub before persistence."""
    async def before_model_callback(self, *, callback_context, llm_request): ...
PedagogyGuardPlugin is worth dwelling on. Every AI tutor promises "it asks before it tells" and every AI tutor caves when the student says "just tell me." Making it a runtime gate rather than a prompt instruction is a genuine architectural claim you can demo: say "just give me the answer" on stage, and watch it hold.
Also register ReflectAndRetryToolPlugin for resilience — free retry-with-reflection on tool failures.
4.7 The background plane
This is the clause of the brief most teams will fake. Here's how to make it real.
Pattern (from Google's own long-running-agents guidance): durable state machine + persistent sessions + event-driven resumption. No polling, no blocked threads. The container scales to zero between wakes.
class ReviewState:
    IDLE            = "IDLE"
    SESSION_ACTIVE  = "SESSION_ACTIVE"
    CONSOLIDATING   = "CONSOLIDATING"
    AWAITING_DECAY  = "AWAITING_DECAY"   # ← the long sleep, hours to days
    REVIEW_DUE      = "REVIEW_DUE"
    PREPPED         = "PREPPED"
Three background agents:
① ConsolidatorAgent — fires on session end. A ParallelAgent running three memory sub-agents concurrently (mirroring DeepTutor's three profile agents), each querying the TraceToolkit before writing:
consolidator = ParallelAgent(
    name="MemoryConsolidator",
    sub_agents=[session_summarizer,   # → D_s
                weakness_analyst,     # → D_w   (the important one)
                pedagogy_reflector],  # → D_r
)
② SchedulerAgent — takes updated D_w, runs FSRS over every touched ConceptCard, writes due timestamps, transitions to AWAITING_DECAY. Cloud Scheduler polls for due cards.
③ PrepAgent — the differentiator. When a card comes due, this wakes before the student opens the app, generates and validates the practice item via QuestionLoop, pre-renders the canvas artifacts, caches them, transitions to PREPPED. When the student next opens Nityam, the session is already built.
The wake mechanism:
@app.post("/internal/review_due")
async def review_due(payload: WakePayload):
    async for event in runner.run_async(
        user_id=payload.user_id,
        session_id=payload.session_id,
        new_message=types.Content(role="user", parts=[
            types.Part.from_text(text="Scheduled wake: prepare review session.")
        ]),
        state_delta={                       # ← applied atomically BEFORE inference
            "current_step": ReviewState.REVIEW_DUE,
            "due_concepts": payload.concept_ids,
        },
    ):
        log(event)
state_delta is the key mechanism: the transition lands before the agent's next inference call, so the model sees the correct state in its system prompt and doesn't hallucinate intermediate steps after a multi-day gap.
Alternative / complement — Gemini's background=true: for genuinely long single tasks (e.g. "build a full revision book for this chapter"), the Interactions API supports server-side background execution. client.interactions.create(model=..., background=True) returns an ID immediately; poll or resume the stream with last_event_id. States: in_progress, requires_action, completed, failed, cancelled. Worth a slide even if you only use it for one feature.
4.8 Deployment
Use the Agents CLI (uv tool install google-agents-cli), which also installs skills into your coding agent so it stops guessing at CLI commands:
agents-cli scaffold enhance --deployment-target cloud_run
agents-cli deploy         # reads deployment_target from pyproject.toml
Cloud Trace is on by default — spans for LLM calls and tool executions. For a hackathon: Cloud Run. It scales to zero (which is genuinely part of the background-agent story) and deploys in one command. Agent Runtime / Agent Engine is the managed option if you want session persistence and autoscaling handled for you.

5. The canvas layer
5.1 tldraw primitives we need
The Editor class is the whole API surface — creating, reading, updating, deleting shapes; selection; history; camera. The store is reactive (signals-based), so UI updates propagate automatically.
import { Tldraw, createShapeId, toRichText, AssetRecordType } from 'tldraw'
import 'tldraw/tldraw.css'

editor.createShape({ type: 'geo', x: 100, y: 100,
                     props: { geo: 'rectangle', w: 200, h: 150, color: 'blue' } })
editor.updateShape({ id, type, x: 200 })
editor.getCurrentPageShapes()
editor.zoomToSelection({ animation: { duration: 600 } })
Shapes are immutable records; updates create a new record. Creation runs through a lifecycle: ID assignment → parent resolution → fractional index for z-order → onBeforeCreate → schema validation → store write.
5.2 Custom shapes for learning
Each learning artifact is a custom ShapeUtil. Minimum viable set — build these five, in this order:
Shape
Base
Contents
concept-card
BaseBoxShapeUtil
Title, body, mastery ring (the deck's progress dials)
derivation
ShapeUtil
Ordered LaTeX/KaTeX steps, per-step annotation, highlight spans
diagram
ShapeUtil
Model-generated SVG, sanitized, with caption
widget
ShapeUtil
Sandboxed iframe (srcDoc, sandbox="allow-scripts")
quiz-card
BaseBoxShapeUtil
Stem, options, selection state, conceptId


const DERIVATION = 'derivation'

declare module 'tldraw' {
  export interface TLGlobalShapePropsMap {
    [DERIVATION]: { w: number; h: number; steps: Step[]; activeStep: number; conceptId: string }
  }
}

export class DerivationShapeUtil extends ShapeUtil<TLShape<typeof DERIVATION>> {
  static override type = DERIVATION
  static override props = { w: T.number, h: T.number, steps: T.any,
                            activeStep: T.number, conceptId: T.string }

  getDefaultProps() { return { w: 420, h: 300, steps: [], activeStep: 0, conceptId: '' } }
  getGeometry(shape) { return new Rectangle2d({ width: shape.props.w,
                                                height: shape.props.h, isFilled: true }) }
  component(shape) {
    return <HTMLContainer><DerivationView {...shape.props} /></HTMLContainer>
  }
  indicator(shape) { return <rect width={shape.props.w} height={shape.props.h} /> }
}
Register via <Tldraw shapeUtils={[DerivationShapeUtil, ...]} />.
For generated images: create an asset first, then an image shape.
const asset = AssetRecordType.create({
  id: AssetRecordType.createId(), type: 'image',
  props: { src: generatedUrl, w: 512, h: 512, mimeType: 'image/png',
           name: 'figure.png', isAnimated: false },
})
editor.createAssets([asset])
editor.createShape({ type: 'image', x, y, props: { assetId: asset.id, w: 512, h: 512 } })
5.3 How the agent sees the canvas
Steal tldraw's agent-starter-kit context model wholesale. It gives the model three levels of detail:
BlurryShape — shapes in the agent's viewport: bounds, ID, type, text. Enough to know what it's looking at, not enough to reconstruct.
FocusedShape — shapes the agent is attending to: most properties, including colour, fill, alignment. This is also the format the model outputs when creating shapes.
PeripheralShapeCluster — shapes outside the viewport, grouped into clusters with bounds + count. Awareness without cost.
Combine with a screenshot (editor.toImage() / getSvgString()). tldraw's guidance is explicit: send both visual and structured data — the image gives spatial relationships and styling, the structured data gives exact values.
One non-obvious performance note from tldraw's docs: keep shape schema properties in alphabetical order — it measurably improves Gemini model performance.
5.4 How the agent manipulates the canvas
Mirror the AgentActionUtil pattern. Each action has a Zod schema (with _type first — the underscore encourages the model to emit it first), a sanitizeAction() pass, and an applyAction().
export const DrawDerivationAction = z.object({
  _type: z.literal('derivation'),
  conceptId: z.string(),
  steps: z.array(z.object({ latex: z.string(), annotation: z.string().optional() })),
  x: z.number(), y: z.number(),
}).meta({ title: 'Derivation', description: 'Render step-by-step symbolic work.' })
Sanitization is mandatory, not optional. The model hallucinates IDs and the canvas moves under it between the time it looked and the time the action lands. tldraw ships helpers for exactly this: ensureShapeIdExists(), ensureShapeIdIsUnique(), ensureValueIsVec(), ensureValueIsNumber(). Also normalize coordinates with applyOffsetToVec / removeOffsetFromVec and round with roundAndSaveNumber / unroundAndRestoreNumber.
5.5 Modes = pedagogical phases
tldraw's agent kit has a mode system: each mode defines parts (what the agent can see) and actions (what it can do), with lifecycle hooks onEnter, onExit, onPromptStart, onPromptEnd, onPromptCancel.
Map modes directly onto tutoring phases:
Mode
Sees
Can do
diagnosing
Learner profile, trace history, student's work
ask_user, flag_gap, emit_quiz — no explanation actions
teaching
Chapter context, plan, canvas
All drawing actions, write_note
probing
Misconception record, past probes
emit_quiz, check_attempt only
reviewing
Session canvas, FSRS due list
write_note, schedule_review, connect

This is a real architectural win: the tutor cannot explain while in diagnosing mode because the explanation actions are not registered. Pedagogy enforced by capability scoping, not by prompt discipline.
Transitions use agent.mode.setMode(), and agent.interrupt({ mode, input }) lets an action force a phase change mid-turn.
5.6 Scheduling further work
agent.schedule('...') queues follow-up work within the agentic loop; agent.interrupt(...) preempts. Use both:
override applyAction(action: Streaming<FlagGapAction>) {
  if (!action.complete) return
  this.agent.schedule({
    message: `Design one probe for the gap "${action.misconception}" before the session ends.`,
  })
}
That's the deck's "every practice question comes from what Diagnose just found" — as a scheduling primitive.
5.7 ⚠️ The licensing problem
tldraw requires a valid license key in production. The SDK detects development mode (localhost, non-production NODE_ENV) and works without a key there. In production — HTTPS on a non-localhost domain with NODE_ENV=production — an unlicensed SDK logs console errors, and license keys are domain-scoped.
Options:
Path
Cost
Watermark
Fit
Dev-only demo (localhost)
Free
No
✅ Best for a live hackathon demo
100-day free trial license
Free, one per commercial unit
No
✅ If you must deploy to a public URL
Hobby license (discretionary)
Free
Yes — "made with tldraw" must stay visible
⚠️ Fine, arguably charming
Commercial license
~$6k/yr startup tier
No
❌ Not now

Action item: request the trial license this week. It's a form; they issue immediately. Don't discover this at 3am on demo night. Fallback if the license path fails: Excalidraw (MIT) — worse agent tooling, but you own it.

6. Collaborative-partner behaviours
This is the second hackathon criterion, and it is where most entries will be thin. Each behaviour below gets a mechanism, not a prompt line.
6.1 It leads
At session start the tutor emits plan.set — a visible plan shape with 3–6 steps derived from the diagnosis. The student sees where they're going. The tutor advances it with plan.advance. The student can drag, reorder, or strike steps; that interaction writes to session.state and the tutor replans (DeepTutor's adaptive replanning: revise remaining sub-goals, preserve completed work).
Demo value: the plan is visible proof the agent has a model of the session, not just of the last message.
6.2 It asks clarifying questions
ask_user is a LongRunningFunctionTool. When called, ADK pauses the agent run — no further events stream until a FunctionResponse with the matching function_call_id comes back. (The ID comes from event.long_running_tool_ids; matching it exactly is mandatory or ADK ignores the response.)
In voice mode this maps beautifully: the tutor asks, genuinely stops, and waits. In text mode it renders as a structured question card on the canvas.
Trigger it on real ambiguity, not performatively: multiple valid interpretations of the question, a symbol used inconsistently, or an unclear prerequisite. One question, then proceed.
6.3 It takes notes
Three layers, all durable:
Automatic — every generated artifact stays on the canvas. Nothing scrolls away. This is the deck's "everything generated in a session compiles onto one lasting canvas that becomes the student's actual notes."
Deliberate — write_note for the tutor's own margin annotations: "you tripped here last time too", "remember: factor ≠ expand".
Structured — on session end, a canvas snapshot + an L1 trace record + a markdown export.
6.4 It guides step by step (the Socratic ladder)
Four rungs, with an explicit gate between each:
1. Guiding question   →  "What happens to the area if you add 3 to each side?"
2. Hint               →  "Try drawing the square."
3. Partial reveal     →  first step only
4. Full explanation   →  gated on check_attempt() == genuine_attempt
check_attempt classifies the student's response as genuine_attempt | guess | stuck | refusing (cheap call on gemini-3.5-flash-lite). PedagogyGuardPlugin blocks rung 4 when attempts_this_concept == 0.
Ground the prompt layer in LearnLM's framing: pedagogical behaviour is instruction-following, specified at the system-instruction level, no fine-tuning required. LearnLM's data is now infused into Gemini, so pedagogical instructions land better than they used to. Worth citing in the pitch — it shows you read the learning-science literature, not just the API docs.
6.5 It captures feedback
Channel
Signal
Writes to
Explicit
Feedback shape: too fast / too slow / lost me / got it
D_r
Implicit — latency
Time to respond after a question
preferred_pace
Implicit — barge-in
Student interrupts mid-explanation
"explanation too long" → D_r
Implicit — canvas
Which shapes get zoomed, dragged, revisited
what_works
Implicit — retries
Repeat attempts on the same concept
difficulty (FSRS D)
Implicit — language
Code-mixing ratio in student speech
language_mix

Barge-in as a pedagogical signal is a genuinely novel touch — it's free (the Live API gives it to you) and it means something ("I already know this" or "you lost me"). Nobody else will use it.

7. Memory, decay and scheduling
7.1 Why FSRS
FSRS (Free Spaced Repetition Scheduler) implements the DSR model — three variables sufficient to describe a memory's state:
Difficulty (D) — inherent complexity, 1–10. Governs how fast stability grows.
Stability (S) — days for retrievability to fall from 100% → 90%. S = 365 means a year until 90%.
Retrievability (R) — current recall probability, decaying along the forgetting curve.
FSRS-6 uses 21 trainable parameters and, unlike SM-2, models the spacing effect properly: reviewing right after learning barely strengthens a memory; reviewing just before forgetting strengthens it a lot. Reviews get scheduled when R drops to a target (default ~0.90). Typical result: 20–30% fewer reviews for the same retention.
7.2 How it plugs into the tutor
The standard flashcard rating (again/hard/good/easy) is replaced by a derived grade from tutoring evidence:
Evidence
Grade
Solved unaided, first attempt, no hesitation
Easy
Solved with one hint
Good
Solved after full explanation
Hard
Reproduced the flagged misconception
Again (+ reopen the Misconception to active)

SchedulerAgent runs FSRS per touched ConceptCard, writes due, and the background plane wakes on it. The review interval is derived from a memory model, not a fixed cadence — that's the sentence for the pitch.
7.3 Misconception lifecycle vs. mastery
Keep them separate and make the transition rules explicit:
UNKNOWN ──assess──▶ MISCONCEIVED ──remediate──▶ PARTIAL ──practice──▶ KNOWN
                          │                                              │
                          └──── reproduced on probe ◀────────────────────┘
                                                        │
                          KNOWN ──survives spaced probe──▶ DURABLE
A Misconception only moves remediating → resolved after surviving two spaced probes at increasing intervals. One correct answer is not evidence of a repaired mental model — it's evidence of a correct answer.

8. Evaluation (how we prove it in a hackathon)
Judges reward evidence. Two cheap, credible instruments:
① A miniature TutorBench. Adopt DeepTutor's protocol at 1/50 scale. Build 6 entries for your chosen chapter: each = a learner profile + three source-grounded knowledge gaps (misconception / incomplete understanding / missing knowledge, each anchored to specific pages) + an interactive task. Run a student simulator (Gemini 3.5 Flash prompted to embody the profile in first person, converting the gaps into first-person beliefs) against both Nityam and a plain-chat baseline. Judge transcripts with a fixed rubric, three times, averaged, temperature 0.
Score the same ten dimensions — Source Faithfulness, Personalization, Applicability, Vividness, Logical Depth / Fitness, Groundedness, Diversity, Answer Quality, Cross Concept. Report the delta. Even n=6 with a clear rubric beats "it feels smart."
② ADK golden evals for the background workflow. adk eval with pre-seeded session state lets you simulate a 48-hour idle gap in seconds. Write two cases:
Safety gate: after a gap is flagged, the agent refuses to skip ahead to a full explanation when the student asks it to. Asserts tool_uses: [].
Resume with context: pre-seed state to AWAITING_DECAY, fire the wake, assert the agent recalls the specific misconception and calls emit_quiz targeting it.
adk eval ./app tests/eval/evalsets/idle_time_resume.json \
  --config_file_path tests/eval/eval_config.json
These slot into CI and they demo well: "here's the agent refusing to give the answer, as a passing test."

9. Build plan
9.1 Sequencing
Day 0 — unblock (do today)
Request the tldraw trial license
Confirm Gemini API access + Live API model availability in your region
agents-cli setup; scaffold the ADK project
Pick the chapter (D3). Ingest it into a File Search store. Verify citations work.
Days 1–2 — the spine (highest risk first)
Voice loop: FastAPI + WebSocket + LiveRequestQueue + run_live(). Talk to it, get audio back. Do not proceed until barge-in works.
tldraw shell with two custom shapes (concept-card, derivation)
Canvas Op Protocol: agent tool → typed event → reducer → shape appears. One op end-to-end.
Day 3 — the tutor 4. TutorPipeline (Investigate → Teach) on Gemini 3.5 Flash, grounded in File Search 5. Remaining canvas ops: diagram.svg, widget.html, quiz.mcq 6. LearnerProfile in session.state, injected into instructions via {placeholders}
Day 4 — the partner behaviours 7. ask_user (LongRunningFunctionTool) + check_attempt + PedagogyGuardPlugin 8. flag_gap → Misconception with trace evidence 9. QuestionLoop (generator ⇄ critic) 10. Feedback shape + implicit signal capture
Day 5 — the background plane (the differentiator) 11. DatabaseSessionService + durable state machine 12. ConsolidatorAgent (ParallelAgent, three memory agents) 13. FSRS scheduler + PrepAgent 14. Wake webhook + Cloud Scheduler
Day 6 — evidence and polish 15. Mini-TutorBench (6 entries), run the comparison, make one chart 16. Two ADK golden evals 17. Deploy to Cloud Run, Cloud Trace on 18. Rehearse the demo eight times
9.2 Demo script (3 minutes)
t
Beat
What the judge sees
0:00
"Nityam, I don't get why (x+3)² isn't x²+9."
Voice in, no typing
0:10
Tutor asks a clarifying question and stops
ask_user pausing the turn
0:20
Plan appears on canvas
It leads
0:30
Tutor talks; an area-model diagram draws itself in sync
The moment. Streaming ops.
1:00
"Just tell me the answer." → tutor offers a hint instead
PedagogyGuardPlugin holding the line
1:20
Student attempts → tutor reveals, flags the misconception
flag_gap with evidence
1:40
Click the flag → traces back to the exact utterance
Auditable personalization
2:00
Close the session. Show the background agent waking.
State machine, durable session
2:20
Reopen: session already prepped, probe targets the same gap
Closed loop, proven
2:40
The eval chart
Evidence, not vibes

9.3 Cut list, in cut order
If you're behind, drop in this order: ① Manim animations → ② teacher dashboard → ③ multi-chapter → ④ Nano Banana image gen → ⑤ code-mixed Hindi (demo in English) → ⑥ mini-TutorBench.
Never cut: the voice loop, one custom shape drawing in sync with speech, the pedagogy gate, the background wake. Those four are the submission.

10. Risks
#
Risk
Likelihood
Mitigation
R1
tldraw license blocks the deployed demo
Medium
Request trial now; demo on localhost; Excalidraw fallback
R2
Live API latency spoils the "in sync" illusion
High
Decouple: speech starts immediately, canvas ops stream behind it. Pre-render the demo chapter's likely artifacts. thinkingLevel: minimal.
R3
Model emits malformed canvas ops
High
Zod schemas + sanitizeAction() + ensureShapeIdExists(). Simplified schema, never raw tldraw records.
R4
Multi-agent + Live forces transcription, blowing token budget
Medium
Expected behaviour, not a bug. Enable context-window compression; keep the live agent flat and delegate reasoning to a separate run_async pipeline.
R5
Background agent looks staged
Medium
Use a real durable session over Postgres. Kill the container on stage and restart it. That's the proof.
R6
Scope: the deck's full product ≫ a hackathon build
High
This doc's §9.3 exists for this. The hackathon build is one vertical slice, framed explicitly as such.
R7
Model names churn (3.5 → 3.6 Flash shipped in July; gemini-3.7-flash already appears in docs)
High
Centralize model IDs in one config module. Never hardcode.
R8
Judges see "another AI tutor"
Medium
Lead with the canvas drawing in sync with speech and the background agent, not with tutoring. The tutoring is the domain; the agent architecture is the entry.


Appendix A — Model & API reference card
Purpose
Model / API
Notes
Reasoning, teaching, question gen
gemini-3.5-flash
GA (May 2026). 1M context, 64K output. temperature/top_p/top_k deprecated — use thinking levels.
Cheap sub-agents (classify, route)
gemini-3.5-flash-lite
~$0.30/1M in, $2.50/1M out
Newer alternative
gemini-3.6-flash
17% fewer output tokens, cheaper than 3.5 Flash, knowledge cutoff Mar 2026. Use if the brief permits.
Voice (bidi)
gemini-3.1-flash-live-preview
16kHz PCM in / 24kHz out, WSS. No proactive audio, no affective dialog. thinkingLevel not thinkingBudget.
Image generation
gemini-3.1-flash-image-preview (Nano Banana 2)
512px–4K. Pro tier: gemini-3-pro-image-preview
Grounding / RAG
Gemini File Search
Managed chunk+embed+index, returns citations. Trade-off: can't tune embeddings or ranking.
Background long tasks
Interactions API background=true
Poll or resumable-stream with last_event_id
Agent framework
google-adk (Python)
Pin the version
CLI / deploy
google-agents-cli
uv tool install google-agents-cli
Frontend transport
AG-UI + CopilotKit
npx copilotkit@latest create -f adk
Canvas
tldraw + agent starter kit
npm create tldraw@latest -- --template agent
Scheduler
FSRS-6 (py-fsrs / fsrs-rs)
21 params, DSR model

Appendix B — Sources
DeepTutor — repo github.com/HKUDS/DeepTutor (Apache-2.0); paper DeepTutor: Towards Agentic Personalized Tutoring, arXiv:2604.26962v2, Zhao et al., HKU; docs at deeptutor.info
tldraw — tldraw.dev/docs/ai, tldraw.dev/starter-kits/agent, tldraw.dev/sdk-features/{editor,shapes,default-shapes,license-key}, tldraw.dev/community/license, @tldraw/ai module docs
Google ADK — adk.dev (agents, workflows, plugins, tools, deploy), google.github.io/adk-docs/streaming/dev-guide/part1–part5, google.github.io/adk-docs/integrations/ag-ui, google.github.io/agents-cli; Google Developers Blog: Build Long-running AI agents that pause, resume, and never lose context with ADK (May 2026), Developer's guide to multi-agent patterns in ADK
Gemini — ai.google.dev/gemini-api/docs/{live-api,background-execution,changelog}, Gemini 3.5 Flash model card (DeepMind), Gemini Live API guides (AI + Cloud)
Learning science — LearnLM: Improving Gemini for Learning (arXiv:2412.16429) + LearnLM prompt guide; FSRS: open-spaced-repetition/awesome-fsrs wiki (The Algorithm, ABC of FSRS)
