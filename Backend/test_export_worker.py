from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.tasks import export_worker as target


class DatasetExportTests(unittest.IsolatedAsyncioTestCase):
    def test_dataset_slug_is_unique_and_valid(self):
        day = dt.date(2026, 8, 16)
        first = target._dataset_slug("A competition with spaces", day, "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb")
        second = target._dataset_slug("A competition with spaces", day, "cccccccc-1111-2222-3333-bbbbbbbbbbbb")
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), 50)
        self.assertRegex(first, r"^[a-z0-9-]+$")

    async def test_publish_creates_one_dataset_from_the_complete_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / "manifest.csv").write_text("rank,zip_file\n1,player.zip\n", encoding="utf-8")
            (stage / "player.zip").write_bytes(b"zip")
            job = SimpleNamespace(
                job_uuid="aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
                dataset_ref=None,
                result_url=None,
                is_public=True,
            )
            user = SimpleNamespace(kaggle_user="tester")
            competition = SimpleNamespace(slug="example-comp", title="Example Competition")
            snapshot = SimpleNamespace(snapshot_date=dt.date(2026, 8, 16))
            db = SimpleNamespace(commit=AsyncMock())
            process = AsyncMock(return_value=(0, "created"))
            status = AsyncMock(side_effect=[None, "ready"])

            with (
                patch.object(target, "_kaggle_cli", return_value="kaggle"),
                patch.object(target, "_kaggle_status", status),
                patch.object(target, "_process", process),
            ):
                await target._publish_kaggle(db, job, user, competition, snapshot, stage)

            process.assert_awaited_once_with(
                "kaggle", "datasets", "create", "-p", str(stage), "-t", "-r", "skip", "--public"
            )
            self.assertEqual(job.result_url, f"https://www.kaggle.com/datasets/{job.dataset_ref}")
            self.assertTrue((stage / "dataset-metadata.json").is_file())

    async def test_publish_reuses_a_ready_dataset_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            job = SimpleNamespace(
                job_uuid="aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
                dataset_ref="tester/existing-dataset",
                result_url=None,
                is_public=False,
            )
            user = SimpleNamespace(kaggle_user="tester")
            competition = SimpleNamespace(slug="example-comp", title="Example Competition")
            snapshot = SimpleNamespace(snapshot_date=dt.date(2026, 8, 16))
            db = SimpleNamespace(commit=AsyncMock())
            process = AsyncMock()
            status = AsyncMock(side_effect=["ready", "ready"])

            with (
                patch.object(target, "_kaggle_cli", return_value="kaggle"),
                patch.object(target, "_kaggle_status", status),
                patch.object(target, "_process", process),
            ):
                await target._publish_kaggle(db, job, user, competition, snapshot, stage)

            process.assert_not_awaited()
            self.assertEqual(job.result_url, "https://www.kaggle.com/datasets/tester/existing-dataset")


class KaggleStatusTests(unittest.TestCase):
    def test_status_parser_accepts_cli_output(self):
        self.assertEqual(target._parse_kaggle_status('{"status": "ready"}'), "ready")
        self.assertEqual(target._parse_kaggle_status("pending"), "pending")
        self.assertIsNone(target._parse_kaggle_status("unknown"))


if __name__ == "__main__":
    unittest.main()
