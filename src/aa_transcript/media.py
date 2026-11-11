import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".aiff", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    start: float
    keep_from: float
    keep_until: float


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


def _silence_midpoints(path: Path) -> list[float]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-nostats", "-i", str(path), "-vn",
             "-af", "silencedetect=noise=-35dB:d=0.25", "-f", "null", "-"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return []

    starts = re.findall(r"silence_start: ([0-9.]+)", result.stderr)
    ends = re.findall(r"silence_end: ([0-9.]+)", result.stderr)
    return [(float(start) + float(end)) / 2 for start, end in zip(starts, ends)]


def split_for_transcribe(path: Path, max_seconds: float, out_dir: Path) -> list[AudioChunk]:
    """Prefer pauses; overlap hard boundaries so speech remains intact in one slice."""
    duration = get_duration_seconds(path)
    if duration <= max_seconds:
        return [AudioChunk(path, 0.0, 0.0, duration)]

    overlap = 2.0
    target_span = max_seconds - 2 * overlap
    silences = _silence_midpoints(path)
    boundaries = [0.0]
    while duration - boundaries[-1] > max_seconds - overlap:
        target = boundaries[-1] + target_span
        nearby = [s for s in silences if target - 20 <= s <= target]
        boundaries.append(nearby[-1] if nearby else target)
    boundaries.append(duration)

    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for index, (keep_from, keep_until) in enumerate(zip(boundaries, boundaries[1:])):
        start = max(0.0, keep_from - overlap)
        end = min(duration, keep_until + overlap)
        chunk_path = out_dir / f"{path.stem}_part{index}.wav"
        slice_audio(path, chunk_path, start, end - start)
        chunks.append(AudioChunk(chunk_path, start, keep_from, keep_until))
    return chunks
