import tempfile
import unittest
from pathlib import Path

from google.genai import _extra_utils

from aa_transcript import gemini_backend


class RecordingFiles:
    def __init__(self):
        self.stream = None
        self.headers = None
        self.mime_type = None

    def upload(self, *, file, config):
        self.stream = file
        options, size, self.mime_type = _extra_utils.prepare_resumable_upload(
            file, user_mime_type=config.mime_type,
        )
        self.headers = options.headers
        assert size == 4
        assert file.read() == b"data"
        return "uploaded"


class UploadTests(unittest.TestCase):
    def test_accented_filename_and_directory_do_not_enter_http_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "áudios"
            directory.mkdir()
            path = directory / "reunião.wav"
            path.write_bytes(b"data")
            files = RecordingFiles()
            client = type("Client", (), {"files": files})()

            result = gemini_backend._upload_audio(client, path)

            self.assertEqual(result, "uploaded")
            self.assertEqual(files.mime_type, "audio/wav")
            self.assertNotIn("X-Goog-Upload-File-Name", files.headers)
            self.assertTrue(files.stream.closed)


if __name__ == "__main__":
    unittest.main()
