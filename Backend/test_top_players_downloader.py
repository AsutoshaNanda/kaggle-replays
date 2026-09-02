from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import top_players_downloader as target


class FakePage:
    def __init__(self, responses):
        self.responses = list(responses)

    async def evaluate(self, script, payload):
        return self.responses.pop(0)


class TopPlayersDownloaderTests(unittest.TestCase):
    def test_snapshot_date_never_passes_deadline(self):
        deadline = dt.datetime(2026, 8, 20, 23, 59, tzinfo=dt.timezone.utc)
        after = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(target.snapshot_date(after, deadline), dt.date(2026, 8, 20))

    def test_competition_deadline_prefers_kaggle_value(self):
        competition = {"deadline": "2026-08-20T23:59:00Z"}
        result = target.competition_deadline(competition, "2026-08-21")
        self.assertEqual(result.date(), dt.date(2026, 8, 20))

    def test_top_count_is_bounded(self):
        self.assertEqual(target.top_count("100"), 100)
        with self.assertRaises(Exception):
            target.top_count("101")

    def test_archive_contains_exact_episode_json_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "10.json").write_text(json.dumps({"id": 10}), encoding="utf-8")
            (stage / "20.json").write_text(json.dumps({"id": 20}), encoding="utf-8")
            archive = root / "player" / "2026-08-20.zip"
            target.create_archive(archive, stage, ["10", "20"])
            self.assertEqual(target.archive_episode_count(archive, ["10", "20"]), 2)
            self.assertIsNone(target.archive_episode_count(archive, ["10", "20", "30"]))

    def test_snapshot_listing_ignores_dates_after_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for day in ("2026-08-19", "2026-08-20", "2026-08-21"):
                (root / f"{day}.json").write_text("{}", encoding="utf-8")
            paths = target.existing_snapshot_paths(root, dt.date(2026, 8, 20))
            self.assertEqual([path.stem for path in paths], ["2026-08-19", "2026-08-20"])


class KaggleClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_pauses_and_continues(self):
        page = FakePage(
            [
                {"status": 429, "text": "", "retryAfter": "0"},
                {"status": 200, "text": '{"ok": true}', "retryAfter": None},
            ]
        )
        client = target.KaggleClient(
            page,
            {"xsrf": "x", "build_hash": "b"},
            target.RequestSettings(delay=0.1, max_retries=1, retry_base=0.1, retry_cap=1.0),
        )
        client._pace = AsyncMock()
        with patch.object(target.asyncio, "sleep", new=AsyncMock()) as sleep:
            result = await client.post_json("/test", {})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleep.await_count, 1)


if __name__ == "__main__":
    unittest.main()
