import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

Backend = str  # "whisper" | "gemini"
JobStatus = str  # "pending" | "processing" | "completed" | "failed"


@dataclass
class Segment:
    speaker: str
    text: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"speaker": self.speaker, "text": self.text, "start": self.start, "end": self.end}

    @staticmethod
    def from_dict(d: dict) -> "Segment":
        return Segment(speaker=d["speaker"], text=d["text"], start=d["start"], end=d["end"])


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    filename: str = ""
    backend: Backend = "whisper"
    status: JobStatus = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    options: dict = field(default_factory=dict)
    result: list[Segment] = field(default_factory=list)
    error: str | None = None
    gemini_batch_name: str | None = None
    gemini_chunk_keys: list[str] = field(default_factory=list)
    gemini_chunk_offsets: dict[str, float] = field(default_factory=dict)
    gemini_end_time: str | None = None
    gemini_expire_at: str | None = None
    gemini_checked_at: str | None = None
    gemini_last_state: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "backend": self.backend,
            "status": self.status,
            "created_at": self.created_at,
            "options": self.options,
            "result": [s.to_dict() for s in self.result],
            "error": self.error,
            "gemini_batch_name": self.gemini_batch_name,
            "gemini_chunk_keys": self.gemini_chunk_keys,
            "gemini_chunk_offsets": self.gemini_chunk_offsets,
            "gemini_end_time": self.gemini_end_time,
            "gemini_expire_at": self.gemini_expire_at,
            "gemini_checked_at": self.gemini_checked_at,
            "gemini_last_state": self.gemini_last_state,
        }

    @staticmethod
    def from_dict(d: dict) -> "Job":
        return Job(
            id=d["id"],
            filename=d.get("filename", ""),
            backend=d.get("backend", "whisper"),
            status=d.get("status", "pending"),
            created_at=d.get("created_at", ""),
            options=d.get("options", {}),
            result=[Segment.from_dict(s) for s in d.get("result", [])],
            error=d.get("error"),
            gemini_batch_name=d.get("gemini_batch_name"),
            gemini_chunk_keys=d.get("gemini_chunk_keys", []),
            gemini_chunk_offsets=d.get("gemini_chunk_offsets", {}),
            gemini_end_time=d.get("gemini_end_time"),
            gemini_expire_at=d.get("gemini_expire_at"),
            gemini_checked_at=d.get("gemini_checked_at"),
            gemini_last_state=d.get("gemini_last_state"),
        )
