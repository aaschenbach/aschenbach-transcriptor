import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from .jobs import Job

DATA_DIR = Path(__file__).parent.parent.parent / "data"
JOBS_FILE = DATA_DIR / "jobs.json"
BACKUP_DIR = DATA_DIR / "backups"
MAX_BACKUPS = 10

_lock = threading.Lock()


def load_jobs() -> dict[str, Job]:
    if not JOBS_FILE.exists():
        return {}
    raw = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    return {j["id"]: Job.from_dict(j) for j in raw}


def save_jobs(jobs: dict[str, Job]) -> None:
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        if JOBS_FILE.exists():
            _rotate_backup()

        payload = json.dumps([j.to_dict() for j in jobs.values()], ensure_ascii=False, indent=2)
        tmp = JOBS_FILE.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(JOBS_FILE)


def purge_old_jobs(jobs: dict[str, Job]) -> dict[str, Job]:
    try:
        days = int(os.environ.get("HISTORY_RETENTION_DAYS", "30"))
    except ValueError:
        days = 30
    if days <= 0:
        return jobs
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400

    def _ts(j: Job) -> float:
        try:
            return datetime.fromisoformat(j.created_at).timestamp()
        except Exception:
            return cutoff  # se não parsear, mantém

    return {jid: j for jid, j in jobs.items() if _ts(j) >= cutoff}


def _rotate_backup() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    shutil.copy2(JOBS_FILE, BACKUP_DIR / f"jobs_{ts}.json")

    backups = sorted(BACKUP_DIR.glob("jobs_*.json"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)
