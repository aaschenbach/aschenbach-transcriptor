# Aschenbach Transcriptor

Audio and video transcription tool with two backends: **Whisper** (local, offline) and **Google Gemini** (cloud, batch or sync). Runs as a local web server with a single-page interface.

> **[Leia em Português](README.pt.md)**

---

## Features

- Drag-and-drop upload of audio and video files
- **Whisper (local):** fully offline transcription using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — no data leaves your machine
- **Gemini:** cloud transcription via Google Generative AI API
  - Synchronous mode (`gemini-3.5-transcribe`): native speaker diarization and word-level timestamps
  - Batch (async) mode (`gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`): submit and come back later; up to 58-minute chunks
- Export transcripts as `.txt` or `.md`, with or without timestamps
- Job history persisted across restarts (configurable retention)
- Gemini models configurable via `gemini_models.toml` without touching code

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Windows (WASAPI audio capture if using live features; transcription itself is cross-platform)
- FFmpeg available in PATH (for video audio extraction)

---

## Installation

```bash
git clone https://github.com/aaschenbach/aschenbach-transcriptor.git
cd aschenbach-transcriptor
uv sync
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the values you need:

```env
# Required for Gemini transcription
GEMINI_API_KEY=

# Optional: Hugging Face token for gated Whisper models
HUGGING_FACE_HUB_TOKEN=

# Default Gemini model key (see gemini_models.toml: transcribe, recommended, lite, difficult)
GEMINI_DEFAULT_MODEL=recommended

# How many days to keep job history (default: 30)
HISTORY_RETENTION_DAYS=30
```

The `GEMINI_API_KEY` is only required if you use Gemini. Whisper works entirely without it.

### Gemini models

Edit `gemini_models.toml` to add, remove, or update Gemini models without changing any code:

```toml
[[models]]
key         = "recommended"
id          = "gemini-3.5-flash"
label       = "Flash 3.5"
description = "General purpose, best balance of cost and accuracy. Async batch."
mode        = "batch"
```

---

## Running

```bash
uv run aa-transcript
```

Then open [http://127.0.0.1:8181](http://127.0.0.1:8181) in your browser.

---

## Usage

1. Drag audio or video files onto the drop zone, or click to browse.
2. For each file, choose a **backend** (Whisper or Gemini) and a **model**.
3. Click **Enviar para transcrição**.
4. Whisper jobs complete in seconds to minutes depending on file length and model size. Gemini batch jobs run asynchronously — click **Verificar agora** to poll for results.
5. Once complete, expand the job card to read the transcript and export it.

### Whisper models

| Model | Size | Notes |
|---|---|---|
| tiny | ~75 MB | Fastest, lowest accuracy |
| base | ~145 MB | Good default for quick tasks |
| small | ~465 MB | Better accuracy |
| medium | ~1.5 GB | High accuracy, slower |
| large-v3 | ~3 GB | Best accuracy |

Downloaded models are cached in `~/.cache/huggingface/hub/`. The first run for each model downloads it automatically.

### Gemini models

| Model | Mode | Best for |
|---|---|---|
| `gemini-3.5-transcribe` | Sync | Short files, needs diarization |
| `gemini-3.5-flash` | Batch | General use |
| `gemini-3.1-flash-lite` | Batch | High volume, lower cost |
| `gemini-3.8-flash` | Batch | Noisy audio, strong accents |

Batch results expire 48 hours after the job completes on Google's side.

---

## Project structure

```
src/aa_transcript/
├── main.py          # FastAPI app, endpoints (port 8181)
├── gemini_backend.py # Gemini sync + batch logic
├── transcriber.py   # faster-whisper wrapper, model listing
├── whisper_backend.py # Whisper execution
├── jobs.py          # Job and Segment dataclasses
├── store.py         # JSON persistence, purge by age
└── exporter.py      # .txt and .md export

static/
└── index.html       # Full UI (HTML + CSS + JS, no framework)

gemini_models.toml   # Gemini model configuration
```

---

## License

This is free and unencumbered software released into the public domain. See [LICENSE](LICENSE).

---

by [Alexandre Aschenbach](https://github.com/aaschenbach)
