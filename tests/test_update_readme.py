import importlib.util
import io
import json
import os
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

os.environ.setdefault("REPO_TOKEN", "test-token")
os.environ.setdefault("GITHUB_REPOSITORY", "owner/repo")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "update_readme.py"
spec = importlib.util.spec_from_file_location("update_readme", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self, *args):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(code, headers=None):
    return urllib.error.HTTPError(
        "https://api.github.com/test", code, "error", headers or {}, io.BytesIO(b"")
    )


class ApiRetryTests(unittest.TestCase):
    def test_retries_after_rate_limit_then_succeeds(self):
        reset = str(int(time.time()) + 5)
        responses = [
            http_error(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset}),
            FakeResponse([{"ok": True}]),
        ]
        with mock.patch.object(mod.urllib.request, "urlopen", side_effect=responses), \
                mock.patch.object(mod.time, "sleep") as fake_sleep:
            result = mod.api("/test")
        self.assertEqual(result, [{"ok": True}])
        fake_sleep.assert_called_once()
        self.assertLessEqual(fake_sleep.call_args[0][0], 60)

    def test_gives_up_after_max_retries(self):
        responses = [http_error(500) for _ in range(4)]
        with mock.patch.object(mod.urllib.request, "urlopen", side_effect=responses), \
                mock.patch.object(mod.time, "sleep") as fake_sleep:
            with self.assertRaises(SystemExit):
                mod.api("/test")
        self.assertEqual(fake_sleep.call_count, 3)

    def test_does_not_retry_not_found(self):
        with mock.patch.object(mod.urllib.request, "urlopen", side_effect=[http_error(404)]), \
                mock.patch.object(mod.time, "sleep") as fake_sleep:
            with self.assertRaises(SystemExit):
                mod.api("/test")
        fake_sleep.assert_not_called()


class BuildSectionTests(unittest.TestCase):
    @staticmethod
    def fake_commit(sha, message):
        return {
            "sha": sha * 40,
            "html_url": f"https://example.com/{sha}",
            "commit": {
                "message": message,
                "author": {"date": "2026-10-05T00:00:00Z", "name": "tester"},
            },
            "author": {"login": "tester"},
        }

    def test_bot_commits_are_filtered_out(self):
        commits = [
            self.fake_commit("a", "chore(readme): update recent activity"),
            self.fake_commit("b", "feat: real change"),
        ]
        with mock.patch.object(mod, "api", return_value=commits):
            section = mod.build_section()
        self.assertNotIn("chore(readme)", section)
        self.assertIn("feat: real change", section)

    def test_limit_is_ten(self):
        commits = [self.fake_commit(str(i % 10), f"commit {i}") for i in range(30)]
        with mock.patch.object(mod, "api", return_value=commits):
            section = mod.build_section()
        self.assertEqual(len(section.splitlines()), 10)


if __name__ == "__main__":
    unittest.main()