from __future__ import annotations

import json
import unittest
from urllib.error import HTTPError

from rosbagel.core.update_check import check_for_update


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class UpdateCheckTests(unittest.TestCase):
    def test_latest_release_reports_newer_version_and_changes(self) -> None:
        def fake_urlopen(_request: object, timeout: float) -> FakeResponse:
            self.assertEqual(timeout, 5.0)
            return FakeResponse(
                {
                    "tag_name": "v1.4.4",
                    "html_url": "https://example.invalid/release",
                    "body": "Added GUI update dialog.",
                }
            )

        info = check_for_update(current="1.4.3", urlopen_factory=fake_urlopen)

        self.assertTrue(info.update_available)
        self.assertEqual(info.latest_version, "1.4.4")
        self.assertEqual(info.latest_ref, "v1.4.4")
        self.assertIn("GUI update", info.changes)

    def test_release_404_falls_back_to_tags(self) -> None:
        calls = []

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            calls.append(str(getattr(request, "full_url", "")))
            if len(calls) == 1:
                raise HTTPError(calls[0], 404, "not found", hdrs=None, fp=None)
            return FakeResponse([{"name": "v1.4.5", "zipball_url": "https://example.invalid/tag"}])

        info = check_for_update(current="1.4.3", urlopen_factory=fake_urlopen)

        self.assertTrue(info.update_available)
        self.assertEqual(info.source, "github_tags")
        self.assertEqual(info.latest_ref, "v1.4.5")

    def test_same_version_is_not_update(self) -> None:
        def fake_urlopen(_request: object, timeout: float) -> FakeResponse:
            return FakeResponse({"tag_name": "v1.4.3", "body": ""})

        info = check_for_update(current="1.4.3", urlopen_factory=fake_urlopen)

        self.assertFalse(info.update_available)


if __name__ == "__main__":
    unittest.main()
