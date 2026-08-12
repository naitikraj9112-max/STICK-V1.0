<p align="center">
  <img src="docs/images/stick-logo.svg" alt="Stick logo" width="72" height="72" />
</p>

<h1 align="center">Stick</h1>

<p align="center">
  <strong>Speak to build your presentation.</strong><br />
  Live decks, photorealistic visuals, and export-ready PowerPoint — created in real time from your voice.
</p>

<p align="center">
  <a href="#description">Description</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#how-it-works">Architecture</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#verification">Verification</a>
</p>

---

## Description

> **Stick is a live presentation engine that builds professional slide decks while you speak.**  
> No templates to fill in, no timeline to edit first — just talk, and Stick turns your ideas into a structured, visual story.

Most presentation tools assume you already know what every slide should say. Stick flips that workflow. You open a browser session, press the microphone, and present out loud the way you would to a colleague. An **AI Director** listens through OpenAI Realtime, detects narrative beats, and composes slides on the fly — choosing the right layout for each moment (hero intro, problem statement, solution cards, architecture diagram, metrics, closing quote).

Behind the scenes, Stick maintains a full presentation pipeline: semantic understanding, planning, state management, strategy-based SVG layouts, **Gemini-generated photorealistic imagery**, incremental **PowerPoint export** via PPT Master, and optional **narrated MP4 video**. Every session is isolated — its own orchestrator, workspace, and artifacts — so live demos stay clean and production deployments stay predictable.

**Who it's for:** founders pitching live, educators teaching in real time, consultants who think out loud, and builders who want voice-native deck creation instead of manual slide wrangling.

**What you get:** a live 16:9 stage preview, an AI Director panel with deck structure and progress, downloadable `.pptx`, and optional `.mp4` — all from one continuous conversation.

<p align="center">
  <img src="docs/images/live-session-ui.png" alt="Stick live session — on-the-fly presentations with AI Director panel" width="920" />
</p>

<p align="center"><em>Live session UI: welcome cover, real-time stage preview, and Stick AI Director.</em></p>

---

## Features

| | |
|---|---|
| **Voice-first authoring** | Stream microphone audio over WebRTC to OpenAI Realtime; slides update as you speak. |
| **AI Director** | Structures narrative beats (intro, problem, solution, architecture, results, close) and picks the right slide type for each moment. |
| **Intelligent visual composition** | Strategy-based layouts — hero, cards, architecture diagrams, pipelines, metrics, quotes — instead of one fixed template. |
| **Live Gemini imagery** | Photorealistic slide visuals generated on demand when a scene needs them. |
| **Incremental PPTX export** | Editable PowerPoint builds automatically in the background via PPT Master (SVG → native PPTX). |
| **Optional MP4 video** | Narration, TTS, and FFmpeg composition when `GEMINI_API_KEY` is configured. |
| **Session isolation** | Each presentation gets its own orchestrator, state, workspace, and artifact directory. |
| **Persistent memory** | Neon PostgreSQL stores user preferences and presentation context across sessions. |

---

## Generated slides

Stick chooses layout and visual strategy per slide type. Examples from the visual composition pipeline:

<p align="center">
  <img src="docs/images/slide-hero.svg" alt="Hero slide — SpaceX introduction" width="420" />
  &nbsp;&nbsp;
  <img src="docs/images/slide-architecture.svg" alt="Architecture slide — stacked system diagram" width="420" />
</p>

<p align="center">
  <img src="docs/images/slide-metrics.svg" alt="Metrics slide — results dashboard" width="640" />
</p>

<p align="center"><em>Exported SVG slides from PPT Master — hero, architecture, and metrics layouts.</em></p>

---

## How it works

```mermaid
flowchart LR
  Browser["Browser UI"]
  Realtime["OpenAI Realtime"]
  Server["Stick Server"]
  Director["AI Director"]
  State["Presentation State"]
  PPTX["PPT Master → PPTX"]
  Media["Gemini → Images / TTS → MP4"]

  Browser -->|WebRTC audio| Realtime
  Realtime -->|transcript + tool calls| Server
  Server --> Director
  Director --> State
  State --> PPTX
  State --> Media
  State -->|live preview| Browser
```

**End-to-end path**

```text
Browser → WebRTC → OpenAI Realtime → Session Manager → Orchestrator
  → Semantic Detector → Memory / Context → Planner → Critic
  → State Manager → Presentation State
      ├─→ Presentation Generator → PPT Master → Editable PPTX
      └─→ Multimedia Manager → Images / Narration / TTS → MP4
```

Separate concepts:

- **Session** — one running presentation interaction (`created → connected → active → disconnected → completed`)
- **Presentation state** — slide content and scene lifecycle (per session)
- **Memory** — durable Neon records scoped by user / presentation / session
- **Artifact** — filesystem PPTX and optional MP4 under `PRESENTATION_ARTIFACT_DIR/<session_id>/`

---

## Quick start

### Prerequisites

- Python 3.10+
- [OpenAI API key](https://platform.openai.com/) with Realtime access
- Optional: [Neon PostgreSQL](https://neon.tech/) for persistent memory
- Optional: [Google Gemini API key](https://ai.google.dev/) for live imagery and video
- Optional: PPT Master checkout for PowerPoint export
- Optional: `ffmpeg` for MP4 rendering

### 1. Configure environment

Create `.env` in the project root:

```env
OPENAI_API_KEY=your_key_here
DATABASE_URL=postgresql://user:password@host/database?sslmode=require

# Optional — live slide imagery + video
GEMINI_API_KEY=your_gemini_key_here

# Optional — PowerPoint export
PPT_MASTER_ROOT=/absolute/path/to/ppt-master
PRESENTATION_ARTIFACT_DIR=artifacts
PRESENTATION_PORT=8001
```

`OPENAI_API_KEY` and `DATABASE_URL` stay on the server and are never sent to the browser.

### 2. Install and run

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python ingestion.py
```

### 3. Open the app

Visit **http://127.0.0.1:8001** (or your configured `PRESENTATION_PORT`), click the microphone button, and start speaking. Stick replaces the welcome cover with your first slide and builds the deck as you go.

---

## Configuration

### Core

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | Required. Powers Realtime voice sessions. |
| `OPENAI_REALTIME_MODEL` | `gpt-realtime` | Realtime model id |
| `PRESENTATION_PORT` | `8001` | Local HTTP server port |
| `PRESENTATION_LANGUAGE` | `en` | Default slide copy language |
| `DATABASE_URL` | — | Neon PostgreSQL for agent memory |

### Reliability

```env
LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=2
LLM_RETRY_BACKOFF_SECONDS=0.5
DATABASE_TIMEOUT_SECONDS=8
HTTP_TIMEOUT_SECONDS=30
RECONNECT_MAX_ATTEMPTS=3
```

### PPT Master (PowerPoint export)

Runtime sessions use an **isolated workspace per session**:

```text
PRESENTATION_ARTIFACT_DIR/<session_id>/ppt_master/
```

```env
PPT_MASTER_ROOT=/absolute/path/to/ppt-master
GENERATION_MAX_CORRECTIONS=1
GENERATION_DEBOUNCE_SECONDS=0.5
```

### Multimedia & video (optional)

`GEMINI_API_KEY` is optional. Without it, Stick still runs and PPTX export still works; video reports `unavailable`.

```env
GEMINI_API_KEY=your_key_here
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
MEDIA_MAX_CONCURRENCY=4
VIDEO_ENABLED=true
FFMPEG_PATH=ffmpeg
TTS_VOICE=Kore
```

Session artifacts:

```text
artifacts/<session_id>/
  presentation.pptx
  presentation.mp4
  media/images/
  media/narration/
  media/audio/
  media/slides/
  media/video/
```

---

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /session` | Create a presentation session |
| `POST /realtime/session` | WebRTC SDP exchange (requires `session_id`) |
| `POST /transcript` | Forward transcript snapshot |
| `GET /presentation?session_id=` | Render model + generation status |
| `GET /presentation/download?session_id=` | Latest session PPTX |
| `GET /presentation/media?session_id=` | Scene image assets |
| `GET /presentation/video/status?session_id=` | Video / multimedia status |
| `POST /presentation/video/generate` | Start background MP4 generation |
| `GET /presentation/video/download?session_id=` | Latest session MP4 |
| `GET /health` | App, Neon, OpenAI, PPT Master, multimedia health |

---

## Project structure

```text
stick/
├── communication/          # HTTP server, WebRTC, static UI
├── presentation_generator/   # SVG templates, visual strategy, PPT Master adapter
├── multimedia/             # Gemini providers, video pipeline, live imagery
├── memory/                 # Neon persistence
├── orchestrator.py         # Session-scoped presentation orchestration
├── realtime_director.py    # Live slide director (OpenAI tool calls)
├── ingestion.py            # Application entry point
└── docs/images/            # README assets (committed for GitHub rendering)
```

---

## Verification

```bash
python -m py_compile *.py communication/*.py memory/*.py presentation_generator/*.py multimedia/*.py multimedia/providers/*.py

python demo_reliability.py
python demo_memory.py
python demo_presentation_intelligence.py
python demo_presentation_generation.py
python demo_end_to_end.py
python demo_realtime_director.py
python demo_visual_composition.py
python demo_real_ppt_master.py      # requires PPT_MASTER_ROOT
python demo_multimedia.py
python demo_video_pipeline.py
python demo_real_gemini.py          # skipped without GEMINI_API_KEY
python demo_neon_memory.py          # requires DATABASE_URL
```

Graceful shutdown: `Ctrl+C` completes active sessions and stops the server cleanly.

`GET /health` reports `healthy` or `degraded`. Optional dependencies (Neon, PPT Master, Gemini) degrade status without blocking core voice + slide functionality.

---

## Security notes

- API keys and database credentials live only in server-side `.env`.
- Each session is isolated with its own artifact directory.
- Do not commit `.env` or generated artifacts containing user content.

---

<p align="center">
  <strong>Stick</strong> — on-the-fly presentations, built from speech.
</p>

<!-- Suggested GitHub repository description (copy to repo settings):
Live presentation engine — speak to build structured slide decks with AI Director, Gemini visuals, and automatic PowerPoint export.
-->
