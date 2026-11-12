import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aa_transcript import gemini_backend
from aa_transcript.jobs import Job
from aa_transcript.media import AudioChunk


class ProgressTests(unittest.TestCase):
    def test_sync_reports_real_chunk_progress_and_persists_fields(self):
        source = Path("sample.wav")
        chunks = [
            AudioChunk(source, 0, 0, 116),
            AudioChunk(source, 114, 116, 180),
        ]
        job = Job(backend="gemini", options={"gemini_model": "gemini-3.5-transcribe"})
        snapshots = []

        def save_progress():
            snapshots.append((job.progress_stage, job.chunks_completed, job.chunks_total))

        def generate(_client, _model, _uploaded, _config, *, on_wait, on_attempt):
            on_wait()
            on_attempt()
            return SimpleNamespace(candidates=[], text="trecho")

        with (patch.object(gemini_backend, "_get_client", return_value=object()),
              patch.object(gemini_backend, "split_for_transcribe", return_value=chunks),
              patch.object(gemini_backend, "_upload_audio", return_value=object()),
              patch.object(gemini_backend, "_generate_sync_with_rate_limit", side_effect=generate)):
            gemini_backend.submit_sync(job, source, Path("chunks"), on_progress=save_progress)

        self.assertEqual(job.status, "completed")
        self.assertEqual((job.chunks_completed, job.chunks_total), (2, 2))
        self.assertIn(("Aguardando cota para o bloco 2/2", 1, 2), snapshots)
        self.assertIn(("Transcrevendo bloco 2/2", 1, 2), snapshots)
        self.assertIn(("Bloco 2/2 concluído", 2, 2), snapshots)
        restored = Job.from_dict(job.to_dict())
        self.assertEqual((restored.chunks_completed, restored.chunks_total), (2, 2))
        old_record = job.to_dict()
        for field in ("progress_stage", "chunks_total", "chunks_completed"):
            old_record.pop(field)
        self.assertEqual(Job.from_dict(old_record).chunks_completed, 0)


if __name__ == "__main__":
    unittest.main()
