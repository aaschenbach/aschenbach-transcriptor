import logging
import logging.handlers
import os
import shutil
import threading
import traceback
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# Propaga o token do HF para o nome canônico que huggingface_hub lê automaticamente
if (hf_token := os.getenv("HUGGING_FACE_HUB_TOKEN")) and not os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = hf_token

from . import gemini_backend, store
from .gemini_backend import DEFAULT_GEMINI_MODEL, GEMINI_MODELS
from .store import purge_old_jobs
from .exporter import export_segments
from .jobs import Job
from .transcriber import PRESET_MODELS, list_models_status

_ALLOWED_MODELS = {m["name"] for m in PRESET_MODELS}
from .whisper_backend import run_whisper

_LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "errors.log", maxBytes=256 * 1024, backupCount=2, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger = logging.getLogger("aa_transcript")
logger.setLevel(logging.ERROR)
logger.addHandler(_handler)

app = FastAPI()

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
CHUNKS_DIR = Path(__file__).parent.parent.parent / "data" / "chunks"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _persist() -> None:
    with _jobs_lock:
        store.save_jobs(dict(_jobs))


@app.on_event("startup")
async def startup() -> None:
    global _jobs
    loaded = store.load_jobs()
    _jobs = purge_old_jobs(loaded)
    if len(_jobs) < len(loaded):
        _persist()


@app.get("/")
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/config")
async def get_config() -> dict:
    return {
        "has_hf_token": bool(os.getenv("HUGGING_FACE_HUB_TOKEN")),
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY")),
        "gemini_models": GEMINI_MODELS,
        "gemini_default_model": DEFAULT_GEMINI_MODEL,
    }


@app.get("/models")
async def list_models() -> list[dict]:
    return list_models_status(has_hf_token=bool(os.getenv("HUGGING_FACE_HUB_TOKEN")))


@app.get("/jobs")
async def list_jobs() -> list[dict]:
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return [j.to_dict() for j in jobs]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return PlainTextResponse("Job não encontrado", status_code=404)
    return job.to_dict()


@app.post("/jobs/{job_id}/check")
async def check_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return PlainTextResponse("Job não encontrado", status_code=404)
    if job.status != "processing" or job.backend != "gemini" or not job.gemini_batch_name:
        return job.to_dict()
    try:
        gemini_backend.poll_job(job)
        _persist()
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = str(exc)
        _persist()
    return job.to_dict()


@app.get("/jobs/{job_id}/export")
async def export_job(job_id: str, format: str = "txt") -> PlainTextResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return PlainTextResponse("Job não encontrado", status_code=404)
    if job.status != "completed":
        return PlainTextResponse("Job ainda não concluído", status_code=409)

    content = export_segments(job.result, format)
    return PlainTextResponse(content)


@app.post("/jobs")
async def create_jobs(
    files: list[UploadFile],
    backend: list[str],
    model: list[str] = None,
    diarization: list[str] = None,
    word_timestamps: list[str] = None,
    initial_prompt: list[str] = None,
    gemini_model: list[str] = None,
) -> list[dict]:
    model = model or []
    diarization = diarization or []
    word_timestamps = word_timestamps or []
    initial_prompt = initial_prompt or []
    gemini_model = gemini_model or []

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    created = []

    for i, upload in enumerate(files):
        job_backend = backend[i] if i < len(backend) else "whisper"
        job = Job(filename=upload.filename, backend=job_backend)

        if job_backend == "whisper":
            raw_model = model[i] if i < len(model) else "base"
            safe_model = raw_model if raw_model in _ALLOWED_MODELS else "base"
            job.options = {
                "model_name": safe_model,
                "initial_prompt": initial_prompt[i] if i < len(initial_prompt) else "",
            }
        else:
            raw_gmodel = gemini_model[i] if i < len(gemini_model) else DEFAULT_GEMINI_MODEL
            allowed_gmodels = {m["id"] for m in GEMINI_MODELS}
            safe_gmodel = raw_gmodel if raw_gmodel in allowed_gmodels else DEFAULT_GEMINI_MODEL
            job.options = {
                "gemini_model": safe_gmodel,
                "diarization": (diarization[i] if i < len(diarization) else "true") == "true",
                "word_timestamps": (word_timestamps[i] if i < len(word_timestamps) else "true") == "true",
            }

        dest_path = UPLOAD_DIR / f"{job.id}_{upload.filename}"
        with dest_path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)

        with _jobs_lock:
            _jobs[job.id] = job
        _persist()

        threading.Thread(target=_process_job, args=(job.id, dest_path), daemon=True).start()
        created.append(job.to_dict())

    return created


def _process_job(job_id: str, path: Path) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
    job.status = "processing"
    _persist()

    try:
        if job.backend == "whisper":
            job.result = run_whisper(
                path, job.options.get("model_name", "base"), job.options.get("initial_prompt", "")
            )
            job.status = "completed"
        else:
            gemini_backend.submit_job(job, path, CHUNKS_DIR)
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        tb = traceback.format_exc(limit=3)
        err_msg = str(exc)
        if "401" in err_msg or "RepositoryNotFoundError" in type(exc).__name__:
            job.error = (
                f"Modelo '{job.options.get('model_name')}' não encontrado ou requer autenticação "
                f"no Hugging Face (401). Use um modelo público como 'base', 'small', 'medium' ou 'large-v3'.\n\n{tb}"
            )
        else:
            job.error = tb
        logger.error("job=%s backend=%s model=%s\n%s", job.id, job.backend, job.options.get("model_name"), tb)
    finally:
        _persist()
        if path.exists():
            path.unlink()


def run() -> None:
    uvicorn.run("aa_transcript.main:app", host="127.0.0.1", port=8181, reload=False)
