# Agentic AI — AI-Powered Animated Video Generation System

End-to-end, agent-orchestrated pipeline that takes a single natural-language prompt and autonomously produces a complete short animated video — story, dialogue, character voices, visual scenes, and a final composited MP4 — plus an intelligent editing agent with full undo support.

---

## 1. Pipeline at a glance

```
   User prompt
        │
        ▼
┌─────────────────────┐   scenes + characters + portraits
│ Phase 1: Story      │
│  (Groq LLM, Pollin.)│
└─────────────────────┘
        │
        ▼
┌─────────────────────┐   per-line TTS, BGM, timing manifest
│ Phase 2: Audio      │
│  (ElevenLabs+edge,  │
│   ffmpeg)           │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐   per-scene mp4 + final composited video
│ Phase 3: Video      │
│  (Pollin. + ffmpeg) │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐   FastAPI + WebSocket + React SPA
│ Phase 4: Web UI     │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐   intent classifier → plan → execute → snapshot
│ Phase 5: Edit+Undo  │   with versioned SQLite-backed state log
└─────────────────────┘
```

Every phase is independently testable and reruns via a button in the UI. The **shared JSON contract** (`shared/schemas/pipeline.py`) flows through all phases untouched.

---

## 2. Technology stack

| Layer        | Tool                                     | Why                                         |
|--------------|------------------------------------------|---------------------------------------------|
| LLM / agents | **Groq API** (Llama 3.3 70B) + LangGraph | Free tier, JSON mode, fast                  |
| TTS          | **ElevenLabs** (primary) + **edge-tts** (fallback) | Multilingual v2 quality when key is set; keyless fallback otherwise — both free tiers |
| Images       | **Pollinations** (primary) + **fal.ai** (optional) | Pollinations is free + keyless (1024×576 cap); fal.ai key, when set, swaps in for native HD output |
| BGM          | **Archive.org CC-BY tracks** + ffmpeg lavfi synth fallback | Real ambient music per mood; synth chord pad if track absent |
| Video comp.  | **ffmpeg 8** (h264, xfade, overlay)      | Local, deterministic, runs on Apple Silicon |
| Vision FX    | **OpenCV + Pillow**                      | Style filters (sepia, noir, cyberpunk…)     |
| Backend      | **FastAPI + WebSocket**                  | Real-time per-phase progress events         |
| Frontend     | **React 18** (prebuilt JSX)              | No `npm install` needed for demos           |
| State store  | **SQLite** (append-only)                 | Guarantees "no version is lost" per spec    |

**API key requirements**:
- **Required** — `GROQ_API_KEY` (free tier, JSON mode LLM calls)
- **Optional** — `ELEVENLABS_API_KEY` upgrades TTS from edge-tts to ElevenLabs Multilingual v2 (free tier: 10K chars/month)
- **Optional** — `FAL_KEY` upgrades image generation from Pollinations (1024×576 cap) to fal.ai FLUX (native HD)

The pipeline auto-detects available keys and falls back gracefully — every external dependency has a free, keyless backup so the demo runs end-to-end with just `GROQ_API_KEY`.

---

## 3. Quick start

### 3.1 Install

```bash
cd "Agentic Project"
python3 -m pip install -r requirements.txt
brew install ffmpeg            # or apt-get install ffmpeg
```

Populate `.env` (only `GROQ_API_KEY` is required; the rest are quality upgrades):
```
GROQ_API_KEY=gsk_xxxxx
GROQ_MODEL=llama-3.3-70b-versatile

# Optional — upgrades TTS to ElevenLabs Multilingual v2 (free tier: 10K chars/month)
ELEVENLABS_API_KEY=sk_xxxxx
ELEVENLABS_MODEL=eleven_multilingual_v2

# Optional — upgrades image generation to fal.ai FLUX (HD output)
FAL_KEY=xxxxx
FAL_IMAGE_MODEL=fal-ai/flux/schnell
```

Optionally seed the BGM library once (CC-BY ambient tracks from archive.org):
```bash
python3 scripts/fetch_bgm.py
```

### 3.2 Run

```bash
# Web UI (recommended for the demo)
python3 -m uvicorn backend.app:app --port 8000
# open http://localhost:8000
```

or headless from the CLI:

```bash
python3 scripts/run_pipeline.py \
  --prompt "A young astronaut discovers a hidden ocean on Mars" \
  --scenes 3 --style cinematic
```

### 3.3 Tests

```bash
python3 -m pytest tests/ -q
# 42 passed
```

---

## 4. Repository layout

```
Agentic Project/
├── README.md                 ← this file
├── requirements.txt
├── config.py                 ← paths + Groq config
├── shared/
│   ├── schemas/              ← Pydantic JSON contract (Phase 1→5 glue)
│   ├── constants/            ← voice pool, emotion prosody, target res
│   └── utils/                ← ffmpeg, IO, event bus
├── mcp/                      ← MCP tool abstraction
│   ├── base_tool.py
│   ├── tool_registry.py
│   ├── tool_executor.py
│   ├── server.py             ← optional stdio MCP server
│   └── tools/
│       ├── llm_tools/        ← story gen, char design, edit intent
│       ├── audio_tools/      ← TTS, BGM, merge/mix
│       ├── vision_tools/     ← image gen, colour adj, style filters
│       ├── video_tools/      ← ken burns, overlay, composer, subtitles
│       └── system_tools/     ← file, state, event log
├── agents/
│   ├── story_agent/          ← Phase 1
│   ├── audio_agent/          ← Phase 2
│   ├── video_agent/          ← Phase 3
│   ├── edit_agent/           ← Phase 5 (intent → plan → execute → snap)
│   └── orchestrator/         ← LangGraph top-level pipeline
├── state_manager/            ← append-only SQLite versioning + undo
├── backend/                  ← FastAPI + WebSocket
├── frontend/
│   ├── index.html
│   ├── src/app.jsx
│   └── static/{app.js, app.css}   ← prebuilt, no `npm install` needed
├── data/
│   ├── outputs/              ← generated assets (images, wavs, mp4s)
│   └── state_versions/       ← per-version asset snapshots
├── scripts/run_pipeline.py   ← CLI runner
├── tests/                    ← unit + integration (pytest)
└── docs/                     ← architecture + report
```

---

## 5. Shared JSON contract

Every phase reads/writes one Pydantic model — `PipelineState` — that gets
serialised and stored in SQLite after every change. Hydrating a run from
a version snapshot is `PipelineState.model_validate_json(row.state_json)`.

```
PipelineState {
  job_id, prompt, num_scenes, style, version,
  story:  StoryState { title, logline, scenes[], characters[] },
  audio:  TimingManifest { segments[], scene_audio{}, scene_durations_ms{}, bgm_tracks{} },
  video:  VideoOutput { scene_clips{}, final_mp4, subtitles_burned, transitions },
  phase_status{}, errors[], log[]
}
```

See `shared/schemas/` for the full typed definitions.

---

## 6. Edit agent (Phase 5)

Four targets, each mapped to the cheapest valid pipeline re-run:

| Target        | Example query                          | Phases re-run                                  |
|---------------|-----------------------------------------|------------------------------------------------|
| `audio`       | "change voice tone to whispered"        | TTS for affected lines → mix → scene compose   |
| `video_frame` | "make scene 2 darker"                   | Scene background regen → ken burns → compose  |
| `video`       | "speed up scene 2" / "remove subtitle"  | Only compositing step                         |
| `script`      | "regenerate the script"                 | Full cascade Phase 1 → 2 → 3                  |

Classification uses the Groq LLM; a deterministic keyword-rule fallback
guarantees the demo works offline. Every edit triggers a
`StateManager.snapshot()` — so **undo is literally** `StateManager.revert(version)` plus
a new append-only row.

Test coverage: **17 edit-query types** parametrised in `tests/unit/test_edit_intent.py`.

---

## 7. Execution flow (example)

Run `scripts/run_pipeline.py --prompt "A spy meets an informant in Neo-Tokyo rain" --scenes 2`:

```
[story]    phase_start → story_gen_start → script_drafted → portrait_ready×N → phase_done
[audio]    phase_start → (tts→concat→bgm→mix)×scenes → phase_done
[video]    phase_start → (bg→kenburns→overlay→compose→burn_subs)×scenes → compose_final → phase_done
[pipeline] snapshot (v1)
```

Then in the UI:
1. `"make scene 2 darker"`     → v2 (video_frame target)
2. `"apply cyberpunk filter"`  → v3 (video_frame target)
3. `"speed up scene 2"`        → v4 (video target)
4. Undo → v5 (restores v2 state + assets)
5. Undo again → v6 (restores v1)

Version history and the reverted final MP4 are visible live.

---

## 8. Generation times (M4 Air, 16 GB)

| Step                              | Wall-clock time |
|-----------------------------------|-----------------|
| Story LLM (Groq)                  | ~1.5 s          |
| Character design LLM              | ~5–8 s          |
| Per-character portrait (Pollin.)  | ~15–90 s (net)  |
| Per-scene background              | ~20–90 s (net)  |
| TTS per line (ElevenLabs / edge-tts) | ~1–3 s        |
| ffmpeg per-scene compose          | ~200 ms         |
| Final xfade concat                | ~250 ms         |
| **Total (3 scenes)**              | **~3–6 min**    |
| Incremental edit (cached bg)      | < 2 s           |

Pollinations results are cached on disk by content hash, so subsequent
edits are near-instant.

---

## 9. Evaluation rubric mapping

| Rubric (weight)                         | Where it lives                                        |
|-----------------------------------------|-------------------------------------------------------|
| Phase 1 — Story & script (15%)          | `agents/story_agent/`, `mcp/tools/llm_tools/`         |
| Phase 2 — Audio generation (15%)        | `agents/audio_agent/`, `mcp/tools/audio_tools/`       |
| Phase 3 — Video composition (20%)       | `agents/video_agent/`, `mcp/tools/video_tools/`       |
| Phase 4 — Web interface (10%)           | `backend/`, `frontend/`                               |
| Integration & pipeline (10%)            | Shared `PipelineState` + orchestrator LangGraph       |
| Report & presentation (10%)             | `docs/REPORT.md`                                      |
| Phase 5 — Edit agent & undo (20%)       | `agents/edit_agent/`, `state_manager/`                |

---

## 10. Troubleshooting

* **`KeyError: Tool 'generate_story' not registered`** — something imported an agent before `mcp.tools`. All standard entry points (CLI, FastAPI) and the `agents/__init__.py` already trigger registration; check your custom script imports.
* **Pollinations 429 / slow** — the tool serialises requests via a thread lock. Give it a minute if you've been regenerating rapidly.
* **Subtitles missing** — ffmpeg's `subtitles` filter needs libass; homebrew's default build lacks it. We work around this by burning captions via Pillow PNG overlays, so you should see them regardless. If they're still missing, set `state.video.subtitles_burned = False`.

---

## 11. Team — division of work

See `docs/REPORT.md` §8 for the full member-by-member split.
All four members are jointly responsible for the shared JSON schema,
integration tests, and the final report.
