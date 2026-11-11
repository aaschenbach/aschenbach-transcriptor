import unittest
import tempfile
import wave
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from aa_transcript.jobs import Segment
from aa_transcript import gemini_backend, media


class TranscribeChunkTests(unittest.TestCase):
    def test_silence_detection_uses_pause_midpoints(self):
        stderr = "silence_start: 114.5\nsilence_end: 115.5 | silence_duration: 1\n"
        with patch.object(media.subprocess, "run", return_value=CompletedProcess([], 0, "", stderr)):
            self.assertEqual(media._silence_midpoints(Path("audio.wav")), [115.0])

    def test_real_ffmpeg_keeps_chunks_within_two_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\xe8\x03" * (114 * 16000))
                audio.writeframes(b"\x00\x00" * 16000)
                audio.writeframes(b"\xe8\x03" * (135 * 16000))

            chunks = media.split_for_transcribe(source, 120, Path(tmp) / "chunks")
            self.assertTrue(any(abs(chunk.keep_until - 114.5) < 1 for chunk in chunks))
            self.assertTrue(all(media.get_duration_seconds(chunk.path) <= 120.1
                                for chunk in chunks))

    def test_prefers_a_pause_near_the_cut_and_keeps_overlap(self):
        slices = []
        with (patch.object(media, "get_duration_seconds", return_value=300.0),
              patch.object(media, "_silence_midpoints", return_value=[115.0]),
              patch.object(media, "slice_audio", side_effect=lambda *args: slices.append(args)),
              patch.object(Path, "mkdir")):
            chunks = media.split_for_transcribe(Path("audio.wav"), 120, Path("chunks"))

        self.assertEqual(chunks[0].keep_until, 115.0)
        self.assertEqual(chunks[1].start, 113.0)
        self.assertEqual(chunks[1].keep_from, 115.0)
        self.assertEqual(chunks[-1].keep_until, 300.0)
        self.assertTrue(all(duration <= 120 for _, _, _, duration in slices))
        self.assertTrue(all(chunks[i].keep_until == chunks[i + 1].keep_from
                            for i in range(len(chunks) - 1)))

    def test_no_pause_still_preserves_both_sides_of_boundary(self):
        with (patch.object(media, "get_duration_seconds", return_value=300.0),
              patch.object(media, "_silence_midpoints", return_value=[]),
              patch.object(media, "slice_audio"),
              patch.object(Path, "mkdir")):
            chunks = media.split_for_transcribe(Path("audio.wav"), 120, Path("chunks"))

        self.assertEqual(chunks[0].keep_until, 116.0)
        self.assertEqual(chunks[1].start, 114.0)
        self.assertEqual(chunks[1].keep_from, 116.0)
        self.assertEqual(chunks[2].start, 230.0)

    def test_overlapping_words_are_kept_by_one_chunk(self):
        first = media.AudioChunk(Path("first.wav"), 0, 0, 116)
        second = media.AudioChunk(Path("second.wav"), 114, 116, 232)
        word = Segment("A", "exemplo", 115.8, 116.4)

        self.assertEqual(gemini_backend._segments_owned_by_chunk([word], first), [])
        self.assertEqual(gemini_backend._segments_owned_by_chunk([word], second), [word])


if __name__ == "__main__":
    unittest.main()
