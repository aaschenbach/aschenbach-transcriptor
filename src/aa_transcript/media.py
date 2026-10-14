import json
import subprocess
from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".aiff", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS - AUDIO_EXTENSIONS or path.suffix.lower() == ".mp4"


def get_duration_seconds(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    return float(data["format"]["duration"])


def extract_audio(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vn", "-ac", "1", "-ar", "16000",
            "-f", "wav",
            str(dst),
        ],
        capture_output=True, check=True,
    )


def slice_audio(src: Path, dst: Path, start_seconds: float, duration_seconds: float) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start_seconds),
            "-t", str(duration_seconds),
            "-i", str(src),
            "-ac", "1", "-ar", "16000",
            "-f", "wav",
            str(dst),
        ],
        capture_output=True, check=True,
    )


def split_into_chunks(path: Path, chunk_seconds: float, out_dir: Path) -> list[Path]:
    duration = get_duration_seconds(path)
    if duration <= chunk_seconds:
        return [path]

    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    start = 0.0
    index = 0
    while start < duration:
        length = min(chunk_seconds, duration - start)
        chunk_path = out_dir / f"{path.stem}_part{index}.wav"
        slice_audio(path, chunk_path, start, length)
        chunks.append(chunk_path)
        start += chunk_seconds
        index += 1
    return chunks
