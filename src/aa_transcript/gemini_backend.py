import os
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google import genai
from google.genai import types

from .jobs import Job, Segment
from .media import extract_audio, get_duration_seconds, is_video, split_into_chunks

_MODELS_FILE = Path(__file__).parent.parent.parent / "gemini_models.toml"


def _load_models() -> list[dict]:
    try:
        data = tomllib.loads(_MODELS_FILE.read_text(encoding="utf-8"))
        return data.get("models", [])
    except Exception:
        return [
            {"key": "transcribe", "id": "gemini-3.5-transcribe", "label": "Transcribe 3.5", "description": "Síncrono, diarização nativa.", "mode": "sync"},
            {"key": "recommended", "id": "gemini-3.5-flash",      "label": "Flash 3.5",      "description": "Batch, uso geral.",           "mode": "batch"},
            {"key": "lite",        "id": "gemini-3.1-flash-lite", "label": "Flash 3.1 Lite", "description": "Batch, menor custo.",         "mode": "batch"},
            {"key": "difficult",   "id": "gemini-3.8-flash",      "label": "Flash 3.8",      "description": "Batch, áudio difícil.",       "mode": "batch"},
        ]


GEMINI_MODELS: list[dict] = _load_models()

def _resolve_default() -> str:
    key = os.environ.get("GEMINI_DEFAULT_MODEL", "")
    # Tenta por key (ex: "recommended"), depois por id direto, depois o primeiro da lista
    for m in GEMINI_MODELS:
        if m.get("key") == key or m.get("id") == key:
            return m["id"]
    # Compatibilidade retroativa com GEMINI_TRANSCRIBE_MODEL
    legacy = os.environ.get("GEMINI_TRANSCRIBE_MODEL", "")
    for m in GEMINI_MODELS:
        if m.get("id") == legacy:
            return legacy
    return GEMINI_MODELS[0]["id"] if GEMINI_MODELS else "gemini-3.5-flash"


DEFAULT_GEMINI_MODEL: str = _resolve_default()

LIMIT_SYNC_SECONDS  = 28 * 60   # limite do transcribe síncrono (30 min com margem)
LIMIT_WITH_ANNOTATIONS_SECONDS = 28 * 60
LIMIT_PLAIN_SECONDS = 58 * 60

PROMPT = (
    "Transcreva o áudio a seguir em Português do Brasil. "
    "Regras estritas: "
    "1. Idioma e Vocabulário: Mantenha termos técnicos da área de tecnologia e "
    "negócios no idioma original em inglês (ex: deploy, prompt, call, budget). "
    "2. Limpeza: Remova vícios de linguagem (como 'ééé', 'tipo', 'né', 'ah', gaguejos), "
    "palavras de hesitação e ignore ruídos de fundo, suspiros ou tosses."
)

TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _mime_type(path: Path) -> str:
    return {
        ".mp3": "audio/mp3", ".wav": "audio/wav", ".m4a": "audio/m4a",
        ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac",
        ".opus": "audio/opus", ".aiff": "audio/aiff", ".webm": "audio/webm",
    }.get(path.suffix.lower(), "audio/wav")


def _parse_transcription_parts(candidates, offset: float) -> list[Segment]:
    segments: list[Segment] = []
    for candidate in candidates or []:
        for part in (getattr(candidate.content, "parts", None) or []):
            transcription = getattr(part, "audio_transcription", None)
            if transcription is None:
                continue
            speaker = getattr(transcription, "speaker_label", None) or "SPEAKER_1"
            start = (getattr(transcription, "start_offset", None) or 0.0) + offset
            end   = (getattr(transcription, "end_offset",   None) or 0.0) + offset
            text  = (getattr(transcription, "text", None) or "").strip()
            if text:
                segments.append(Segment(speaker=speaker, text=text, start=start, end=end))
    return segments


def _model_mode(model_id: str) -> str:
    for m in GEMINI_MODELS:
        if m["id"] == model_id:
            return m.get("mode", "batch")
    return "batch"


# ── Síncrono (gemini-3.5-transcribe) ─────────────────────────────────────────

def submit_sync(job: Job, path: Path, chunks_dir: Path) -> None:
    client = _get_client()
    model_name = job.options.get("gemini_model", DEFAULT_GEMINI_MODEL)
    diarization = job.options.get("diarization", True)
    word_timestamps = job.options.get("word_timestamps", True)

    audio_path = path
    if is_video(path):
        audio_path = path.with_suffix(".extracted.wav")
        extract_audio(path, audio_path)

    chunk_paths = split_into_chunks(audio_path, LIMIT_SYNC_SECONDS, chunks_dir)

    transcription_config = types.AudioTranscriptionConfig(
        diarization=diarization,
        word_timestamp=word_timestamps,
    )

    all_segments: list[Segment] = []
    for i, chunk_path in enumerate(chunk_paths):
        offset = i * LIMIT_SYNC_SECONDS
        uploaded = client.files.upload(file=str(chunk_path))
        response = client.models.generate_content(
            model=model_name,
            contents=[uploaded],
            config=types.GenerateContentConfig(
                audio_transcription_config=transcription_config,
            ),
        )
        segs = _parse_transcription_parts(response.candidates, offset)
        # fallback: se não veio audio_transcription estruturado, usa response.text
        if not segs and getattr(response, "text", None):
            all_segments.append(Segment(
                speaker="transcricao",
                text=response.text.strip(),
                start=offset,
                end=offset,
            ))
        else:
            all_segments.extend(segs)

    all_segments.sort(key=lambda s: s.start)
    job.result = all_segments
    job.status = "completed"
    now = datetime.now(timezone.utc)
    job.gemini_end_time = now.isoformat()
    job.gemini_checked_at = now.isoformat()
    job.gemini_last_state = "COMPLETED"

    if audio_path != path and audio_path.exists():
        audio_path.unlink()
    for chunk_path in chunk_paths:
        if chunk_path != audio_path and chunk_path.exists():
            chunk_path.unlink()


# ── Batch assíncrono (flash) ──────────────────────────────────────────────────

def submit_job(job: Job, path: Path, chunks_dir: Path) -> None:
    model_name = job.options.get("gemini_model", DEFAULT_GEMINI_MODEL)

    if _model_mode(model_name) == "sync":
        submit_sync(job, path, chunks_dir)
        return

    client = _get_client()
    audio_path = path
    if is_video(path):
        audio_path = path.with_suffix(".extracted.wav")
        extract_audio(path, audio_path)

    chunk_paths = split_into_chunks(audio_path, LIMIT_PLAIN_SECONDS, chunks_dir)

    requests = []
    offsets = {}
    for i, chunk_path in enumerate(chunk_paths):
        key = f"{job.id}_part{i}"
        offsets[key] = i * LIMIT_PLAIN_SECONDS

        uploaded = client.files.upload(file=str(chunk_path))
        requests.append(
            types.InlinedRequest(
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                file_data=types.FileData(
                                    file_uri=uploaded.uri, mime_type=uploaded.mime_type
                                )
                            ),
                            types.Part(text=PROMPT),
                        ],
                    )
                ],
                metadata={"key": key},
            )
        )

    batch_job = client.batches.create(
        model=model_name,
        src=requests,
        config=types.CreateBatchJobConfig(display_name=f"transcricao_{job.id}"),
    )

    job.gemini_batch_name = batch_job.name
    job.gemini_chunk_keys = list(offsets.keys())
    job.gemini_chunk_offsets = offsets
    job.status = "processing"

    if audio_path != path and audio_path.exists():
        audio_path.unlink()
    for chunk_path in chunk_paths:
        if chunk_path != audio_path and chunk_path.exists():
            chunk_path.unlink()


def poll_job(job: Job) -> None:
    client = _get_client()
    batch_job = client.batches.get(name=job.gemini_batch_name)
    state = batch_job.state.name
    now = datetime.now(timezone.utc)

    job.gemini_checked_at = now.isoformat()
    job.gemini_last_state = state

    if batch_job.end_time:
        job.gemini_end_time = batch_job.end_time.isoformat()
        job.gemini_expire_at = (batch_job.end_time + timedelta(hours=48)).isoformat()

    if state not in TERMINAL_STATES:
        return

    if state in {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}:
        job.result = _parse_batch_results(batch_job, job.gemini_chunk_offsets)
        job.status = "completed"
    elif state == "JOB_STATE_EXPIRED":
        job.status = "failed"
        job.error = "Job expirou no Gemini antes de concluir (48h sem rodar)."
    else:
        job.status = "failed"
        job.error = str(batch_job.error) if batch_job.error else f"Job terminou em estado {state}."


def _parse_batch_results(batch_job, offsets: dict[str, float]) -> list[Segment]:
    segments: list[Segment] = []
    for resp in (batch_job.dest.inlined_responses or []):
        key = (resp.metadata or {}).get("key")
        offset = offsets.get(key, 0.0)
        if resp.error:
            continue
        candidates = getattr(resp.response, "candidates", None)
        segs = _parse_transcription_parts(candidates, offset)
        if segs:
            segments.extend(segs)
        else:
            # Flash batch retorna texto simples via response.text
            text = ""
            for candidate in (candidates or []):
                for part in (getattr(candidate.content, "parts", None) or []):
                    text += getattr(part, "text", "") or ""
            text = text.strip()
            if text:
                segments.append(Segment(speaker="transcricao", text=text, start=offset, end=offset))
    segments.sort(key=lambda s: s.start)
    return segments
