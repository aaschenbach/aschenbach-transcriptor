from pathlib import Path

from .jobs import Segment
from .media import extract_audio, is_video
from .transcriber import Transcriber

_transcriber: Transcriber | None = None


def get_transcriber(model_name: str) -> Transcriber:
    global _transcriber
    if _transcriber is None or _transcriber.model_name != model_name:
        _transcriber = Transcriber(model_name)
    return _transcriber


def run_whisper(path: Path, model_name: str, initial_prompt: str = "") -> list[Segment]:
    audio_path = path
    if is_video(path):
        audio_path = path.with_suffix(".extracted.wav")
        extract_audio(path, audio_path)

    transcriber = get_transcriber(model_name)
    try:
        return transcriber.transcribe_file(str(audio_path), initial_prompt)
    finally:
        if audio_path != path and audio_path.exists():
            audio_path.unlink()
