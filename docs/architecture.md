# Architecture

## End-to-end flow

```text
Browser microphone
  ↓ WebRTC
OpenAI Realtime API
  ↓ transcript events over the data channel
Communication Layer
  ↓ transcript snapshot + session_id
Session Manager
  ↓ session-scoped orchestrator
Semantic Detector
  ↓ meaningful update
Memory Retrieval → Presentation Context → Presentation Planner → Critic
                                                        ↓
                                                   State Manager
                                                    ↙          ↘
                              Session Presentation State   Memory Manager → Repository
Rendering Layer
  ↓ render model
Frontend
  ↓
Presentation Generator → PPT Master → Editable PPTX (per session artifact dir)
```

## Four separate concepts

| Concept | Owns | Does not own |
| --- | --- | --- |
| **Session** (`session.py`, `session_manager.py`) | `session_id`, lifecycle status, connection status, execution metadata | Slide content |
| **Presentation State** (per session via orchestrator) | Active/completed scenes, theme, metadata | Session connection or artifacts |
| **Memory** (`memory/`) | Durable Neon records, session working memory | Presentation state copies |
| **Artifact** (`presentation_generator/`) | Filesystem PPTX under `PRESENTATION_ARTIFACT_DIR/<session_id>/` | Neon or presentation state |

Session lifecycle: `created → connected → active → disconnected → completed` (or `failed`).

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `communication/static/index.html` | Creates a session, captures microphone audio, WebRTC to OpenAI, displays scenes and generation status. |
| `communication/server.py` | API key server-side, SDP exchange, session routing, transcript relay, health, graceful request handling. |
| `session.py` | Presentation session model and lifecycle helpers. |
| `session_manager.py` | Registry of sessions; one orchestrator + isolated generator workspace per session. |
| `orchestrator.py` | Coordinates detector, memory, planner, critic, state manager, generation for one session. |
| `semantic_detector.py` | Decides whether a transcript update warrants planning. |
| `memory/manager.py` | Failure-tolerant memory API; session working memory cleared on session end. |
| `memory/repository.py` | Neon PostgreSQL repository. |
| `presentation_context.py` | Read-only planner context. |
| `planner.py` | Structured `stage_scene` decision via tool calling. |
| `critic.py` | Evaluates proposed scenes before commit. |
| `state_manager.py` | Only module that mutates presentation state. |
| `state.py` | Factory for new presentation state dicts. |
| `rendering.py` | Read-only frontend render model. |
| `presentation_generator/` | Post-commit SVG + PPTX generation via real PPT Master scripts. |
| `ingestion.py` | Application entrypoint with logging and graceful shutdown. |

## Original pipeline detail

```text
Browser microphone
  ↓ WebRTC
OpenAI Realtime API
  ↓ transcript events over the data channel
Communication Layer
  ↓ transcript snapshot
Orchestrator
  ↓ transcript comparison
Semantic Detector
  ↓ meaningful update
Memory Retrieval → Presentation Context → Presentation Planner → Critic
                                                        ↓
                                                   State Manager
                                                    ↙          ↘
                                         Presentation State   Memory Manager → Repository
Rendering Layer
  ↓ render model
Frontend
```

## Module responsibilities (agent pipeline)

| Module | Responsibility |
| --- | --- |
| `communication/static/index.html` | Captures browser microphone audio, creates WebRTC, receives Realtime events, and displays the render model. |
| `communication/server.py` | Keeps the API key server-side, exchanges SDP with OpenAI, relays transcript events to the orchestrator, and serves rendering output. |
| `orchestrator.py` | Coordinates detector, memory retrieval, planner, critic, state manager, and post-update memory recording. It does not decide scene contents or mutate state itself. |
| `semantic_detector.py` | Uses its LLM and prompt to decide whether a transcript update warrants planning. |
| `memory/manager.py` | The high-level, failure-tolerant memory API used by the orchestrator. |
| `memory/repository.py` | Repository interface plus the current Neon PostgreSQL implementation. Another backend can implement the same interface later. |
| `memory/models.py` | Pydantic memory record, scope, and extraction-candidate schemas. |
| `memory/retrieval.py` | Pluggable lexical ranking policy; a semantic/vector retriever can later share its interface. |
| `memory/extraction.py` | Proposes bounded structured presentation memories after meaningful updates. |
| `presentation_context.py` | Builds the planner's read-only state context plus a small relevant-memory subset. |
| `planner.py` | Converts approved transcript content and read-only context into a structured `stage_scene` decision. |
| `critic.py` | Evaluates a proposed scene with structured output before the state manager can apply it. |
| `state_manager.py` | The only module that applies scene lifecycle changes to presentation state. |
| `state.py` | Factory for per-session presentation state dicts. |
| `rendering.py` | Reads presentation state and returns a frontend-ready component model. |
| Frontend | Selects and displays the named scene component; it does not plan or update state. |

## Scene lifecycle

The active scene has an `id`, `kind`, `status`, timestamps, and a `content`
object. Its status is `editing` while it is active. Before the state manager
moves it into `completed_scenes`, it changes its status to `completed`.

The planner can select four actions:

- `replace` — revise the active scene.
- `merge` — merge more content into the active scene.
- `start_new_scene` — finalize the active scene and start another.
- `complete_scene` — finalize the active scene.

## Agent Memory: state versus memory

`presentation_state` answers **what is happening now**: the active scene,
completed scenes, theme, and presentation metadata. It is only changed by
`state_manager.py`.

`MemoryManager` answers **what might be useful later**. It never stores a copy
of a scene or the full presentation state, and the planner cannot write to it.
Python retrieves memory before planning and records useful outcomes only after a
state update succeeds.

### Memory categories and schema

- **Working memory** is stored in Neon PostgreSQL and holds small session facts
  such as current topic, goal, audience, or stage.
- **Episodic memory** stores timestamped meaningful events, such as a topic
  change, in Neon PostgreSQL. Raw transcript snapshots are not stored.
- **Presentation memory** stores reusable details within one presentation, such
  as that the architecture section explains three layers.
- **Long-term user preferences** are in Neon PostgreSQL; they survive
  `clear_session()` and are only set from explicit/high-confidence preferences.

All four types use `MemoryRecord`: `id`, `type`, `content`, `importance`,
`user_id`, `presentation_id`, `session_id`, timestamps, and metadata.

`get_relevant_memory()` returns a short ranked list, never the entire store.
The current lexical ranking favors presentation-scoped records, then matching
user preferences, and uses token relevance, importance, and recency. Retrieval
is isolated in `memory/retrieval.py`, so a semantic/vector implementation can be
added later without changing the orchestrator. The orchestrator supplies that
list to `presentation_context.py`; the LLM can read it to make a decision, but
only Python calls `remember`, `record_event`, `store_candidate`, or
`set_preference`.

Presentation scopes are `(user_id, presentation_id, session_id)`. Preferences
are user-scoped; episodic and presentation memory are presentation-scoped, so
records from Presentation A are not returned for Presentation B. The local
defaults are `local-user`, `local-presentation`, and `local-session` until real
authentication supplies identities.

Memory is deliberately non-critical. Read/write/extraction failures are logged
as warnings and return an empty memory result; planning and state updates proceed.
The current `PostgresMemoryRepository` uses the server-only `DATABASE_URL` from
`.env`, initializes the single `presentation_memories` table safely on startup,
and keeps all SQL out of the orchestrator and planner. `MemoryRepository` remains
the extension point for a future vector-backed retrieval or another storage backend.

## Updated agent flow

```text
                    ┌──────────────────┐
                    │ Memory Retrieval │
                    └────────┬─────────┘
                             ↓
Transcript → Detector → Context → Planner
                              ↓
                           Critic
                              ↓
                        State Manager
                         ↙          ↘
                Presentation       Memory
                   State          Manager
                                    ↓
                               Repository
```

## Production reliability

Each component contains its own failure: the detector fails closed and waits for
the next transcript; memory returns an empty context; the planner leaves state
unchanged; the critic falls back to a valid planner result; the state manager
validates and drafts before committing; and rendering returns an error model
without mutating state. LLM calls use bounded exponential retries only for likely
transient network/service errors—invalid structured output is not retried.

The orchestrator serializes one local transcript cycle at a time and tracks a
small recent event-id set, preventing duplicate events from creating duplicate
scenes or memories. Each cycle uses the event id as its log correlation id.

The browser handles Realtime connection, data-channel, transcription-error, and
server delivery failures with visible status text and bounded exponential
reconnection. `/health` exposes backend, Neon, OpenAI configuration, and Realtime
readiness without failing simply because optional Neon memory is unavailable.

## Efficient execution policy

```text
Transcript
   ↓
Semantic Gate ── no meaningful update → stop
   ↓
Memory Retrieval
   ↓
Compact Context
   ↓
Planner
   ↓
Critic only when needed
   ↓
Maximum one refinement
   ↓
State Manager → Rendering
```

The semantic detector is the only LLM gate for whether presentation work begins.
Memory retrieval runs only after it approves content. `presentation_context.py`
builds a deterministic compact summary with title, goal, audience, stage, current
section, and recent completed titles; it includes only the current scene and the
three most recent completed-scene summaries. This keeps context priority on the
approved transcript, current scene/stage, summary, relevant memory, then recent
history.

`execution_policy.py` uses deterministic logic to skip the critic for simple
updates. It runs the critic for topic transitions, architecture, pipelines,
metrics, or dense cards. The orchestrator tracks `detector_called`,
`memory_retrieved`, `planner_called`, `critic_called`, `refinement_called`, and
`scene_updated` per event id. This accounting explains work without adding an
observability platform or extra LLM calls.

## Presentation generation and PPT Master

```text
Scene Decision → State Manager → Presentation State
                                      ↓
                           Presentation Generator
                                      ↓
                            PPT Master Adapter
                         ↙        ↓         ↘
                    Design SVG  Quality   Native PPTX
                                      ↓
                               Artifact storage
```

The planner owns **what** the audience should see; PPT Master owns **how** that
approved scene becomes editable PowerPoint. The generator runs only after the
state manager commits a scene and never writes `presentation_state` itself. Its
generation status is separate from state and is included in the read-only browser
render model.

Selected PPT Master components are deliberately narrow:

| PPT Master component | Integration | Why |
| --- | --- | --- |
| `skills/ppt-master/SKILL.md` and Generate routing | Adapter contract and setup boundary | Reuses the separation of SVG source, quality, and export without importing its agent workflow. |
| `scripts/svg_quality_checker.py` | `PptMasterAdapter.validate()` | Detects SVG structural/visual-quality issues before export. |
| `scripts/svg_to_pptx.py` | `PptMasterAdapter.export()` | Produces native editable DrawingML PPTX artifacts. |
| `finalize_svg.py` and the full Strategist pipeline | Not auto-integrated | They depend on interactive project gates and long-form deck authoring, unsuitable for realtime scene updates. |

PPT Master must be installed separately. `PPT_MASTER_ROOT` points to the script
checkout. Runtime browser sessions use an isolated workspace per session under
`PRESENTATION_ARTIFACT_DIR/<session_id>/ppt_master/` so stale SVG files from other
sessions never appear in a new deck. `PPT_MASTER_WORKSPACE` remains for manual demos
without a session id. The adapter updates only the affected scene SVG source; PPT
Master's exporter may rebuild the deck artifact, but state and prior artifacts are
never corrupted on failure. One bounded correction trims overly dense local card
output and reruns validation. Artifacts are filesystem files under
`PRESENTATION_ARTIFACT_DIR/<session_id>/presentation.pptx`; Neon continues to store
memory only.

## Session lifecycle and observability

```text
POST /session → created
POST /realtime/session → connected
POST /transcript → active
POST /session/disconnect or shutdown → disconnected / completed
```

Logs use `[session_id][event_id]` correlation. Sensitive values (API keys,
database URLs, full prompts, raw audio) are never logged.

Graceful shutdown (`SIGINT`/`SIGTERM`) completes sessions, clears session working
memory, and stops the HTTP server without leaving background tasks running.

## Multimedia architecture (Chapter 12)

```text
Presentation State (committed)
        ↓
Multimedia Planner (read-only)
        ↓
   Task graph (parallel)
   ┌────┼────────┐
   ↓    ↓        ↓
 Image Narration Metadata
 Agent  Agent
   ↓      ↓
 Asset   TTS
   └──┬───┘
      ↓
 Video Timeline → Composer → FFmpeg → presentation.mp4
```

| Module | Responsibility |
| --- | --- |
| `multimedia/planner.py` | Scene media plan — image/narration/TTS needs, visual roles |
| `multimedia/manager.py` | Scheduling, parallel execution, lifecycle, session media state |
| `multimedia/image_agent.py` | Provider-abstracted image generation |
| `multimedia/narration_agent.py` | Grounded presenter narration |
| `multimedia/tts_agent.py` | Speech synthesis |
| `multimedia/timeline.py` | Deterministic scene timing |
| `multimedia/composer.py` | Combines SVG slides, images, audio |
| `multimedia/video_renderer.py` | FFmpeg MP4 render |

Rules:

- **StateManager** remains the sole writer of presentation state
- Media binaries live on disk; `media/media_state.json` holds metadata per session
- Video failure does not affect PPTX
- Live presentation never waits for video render
- `GEMINI_API_KEY` optional — missing key degrades multimedia only
