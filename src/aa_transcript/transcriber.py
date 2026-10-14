import re

from huggingface_hub import scan_cache_dir
from faster_whisper import WhisperModel
from faster_whisper.utils import _MODELS

from .jobs import Segment

# Modelos pré-definidos exibidos na UI: alias -> { repo_id, size_mb, label }
PRESET_MODELS: list[dict] = [
    {"name": "tiny",                     "repo_id": "Systran/faster-whisper-tiny",                            "size_mb": 75,   "group": "Systran"},
    {"name": "base",                     "repo_id": "Systran/faster-whisper-base",                            "size_mb": 145,  "group": "Systran"},
    {"name": "small",                    "repo_id": "Systran/faster-whisper-small",                           "size_mb": 466,  "group": "Systran"},
    {"name": "medium",                   "repo_id": "Systran/faster-whisper-medium",                          "size_mb": 1500, "group": "Systran"},
    {"name": "large-v3",                 "repo_id": "Systran/faster-whisper-large-v3",                        "size_mb": 3100, "group": "Systran"},
    {"name": "large-v3-turbo",           "repo_id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",           "size_mb": 1600, "group": "Systran"},
    {"name": "distil-large-v3",          "repo_id": "Systran/faster-distil-whisper-large-v3",                 "size_mb": 1500, "group": "Distil"},
    {"name": "distil-large-v3.5",        "repo_id": "distil-whisper/distil-large-v3.5-ct2",                   "size_mb": 1500, "group": "Distil"},
    {"name": "large-v3-q4",              "repo_id": "bartowski/whisper-large-v3-GGUF",                        "size_mb": 1100, "group": "Quantizado", "gated": True},
    {"name": "large-v3-turbo-q8",        "repo_id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",           "size_mb": 900,  "group": "Quantizado", "gated": True},
    {"name": "distil-large-v3-int8",     "repo_id": "ctranslate2-4you/distil-whisper-large-v3-ct2-int8",      "size_mb": 750,  "group": "Quantizado", "gated": True},
    {"name": "distil-large-v3-int8_float16", "repo_id": "ctranslate2-4you/distil-whisper-large-v3-ct2-int8_float16", "size_mb": 750, "group": "Quantizado", "gated": True},
]


def _resolve_repo_id(model_name: str) -> str:
    """Retorna o repo_id HuggingFace para um alias ou repo_id direto."""
    if re.match(r".+/.+", model_name):
        return model_name
    return _MODELS.get(model_name, f"Systran/faster-whisper-{model_name}")


def list_models_status(has_hf_token: bool = False) -> list[dict]:
    try:
        cached = {r.repo_id for r in scan_cache_dir().repos}
    except Exception:  # noqa: BLE001
        cached = set()
    return [
        {**m, "local": m["repo_id"] in cached}
        for m in PRESET_MODELS
        if not m.get("gated") or has_hf_token
    ]


class Transcriber:
    def __init__(self, model_name: str = "base") -> None:
        self.model_name = model_name
        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )

    def transcribe_file(self, audio_path: str, initial_prompt: str = "") -> list[Segment]:
        kwargs = dict(
            language="pt",
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        segments, _ = self.model.transcribe(audio_path, **kwargs)
        return [
            Segment(speaker="transcricao", text=seg.text.strip(), start=seg.start, end=seg.end)
            for seg in segments
            if seg.text.strip()
        ]
