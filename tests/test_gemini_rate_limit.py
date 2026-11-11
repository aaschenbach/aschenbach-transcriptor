import unittest
from unittest.mock import patch

from google.genai import errors

from aa_transcript import gemini_backend


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Models:
    def __init__(self, failures=()):
        self.failures = list(failures)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        return object()


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        gemini_backend._last_sync_request_at = None
        self.clock = Clock()
        self.monotonic = patch.object(gemini_backend.time, "monotonic", self.clock.monotonic)
        self.sleep = patch.object(gemini_backend.time, "sleep", self.clock.sleep)
        self.monotonic.start()
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.monotonic.stop()
        gemini_backend._last_sync_request_at = None

    def test_requests_are_spaced_across_jobs(self):
        models = Models()
        client = type("Client", (), {"models": models})()
        for _ in range(2):
            gemini_backend._generate_sync_with_rate_limit(client, "model", "audio", "config")
        self.assertEqual(len(models.calls), 2)
        self.assertEqual(self.clock.now, 1060.0)

    def test_429_waits_for_both_api_retry_and_local_slot(self):
        rate_error = errors.ClientError(429, {"error": {"message": "Please retry in 75.5s"}})
        models = Models([rate_error])
        client = type("Client", (), {"models": models})()
        gemini_backend._generate_sync_with_rate_limit(client, "model", "audio", "config")
        self.assertEqual(len(models.calls), 2)
        self.assertEqual(self.clock.now, 1075.5)

    def test_short_api_retry_still_respects_local_minute(self):
        rate_error = errors.ClientError(429, {"error": {"message": "Please retry in 4.475638875s"}})
        models = Models([rate_error])
        client = type("Client", (), {"models": models})()
        gemini_backend._generate_sync_with_rate_limit(client, "model", "audio", "config")
        self.assertEqual(len(models.calls), 2)
        self.assertEqual(self.clock.now, 1060.0)

    def test_daily_quota_does_not_loop(self):
        rate_error = errors.ClientError(429, {"error": {"message": "Requests per day limit exceeded"}})
        models = Models([rate_error])
        client = type("Client", (), {"models": models})()
        with self.assertRaisesRegex(RuntimeError, "Cota diária"):
            gemini_backend._generate_sync_with_rate_limit(client, "model", "audio", "config")
        self.assertEqual(len(models.calls), 1)


if __name__ == "__main__":
    unittest.main()
