import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update-language-stats.py"
SPEC = importlib.util.spec_from_file_location("language_stats", SCRIPT)
stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stats)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "assets" / "language-stats.json"
        self.chart = self.root / "assets" / "language-stats.svg"
        self.snapshot.parent.mkdir()
        self.data = {
            "user": stats.USER,
            "retrieved_at": "2026-10-23T20:31:09+00:00",
            "metric": "GitHub-reported language bytes",
            "scope": "Public owned repositories; forks and profile repository excluded",
            "repositories": [{"repository": "example", "languages": {"Python": 100}}],
        }
        self.snapshot.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        self.chart.write_text(stats.render_chart(self.data), encoding="utf-8")
        for name, value in [("ROOT", self.root), ("SNAPSHOT", self.snapshot), ("CHART", self.chart)]:
            patcher = patch.object(stats, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_refresh(self, data):
        with patch.object(stats, "fetch_snapshot", return_value=data), patch("sys.argv", ["update-language-stats.py"]):
            stats.main()

    def test_unchanged_counts_preserve_files_and_timestamp(self):
        before = (self.snapshot.read_bytes(), self.chart.read_bytes())
        later = copy.deepcopy(self.data)
        later["retrieved_at"] = "2026-10-24T20:31:09+00:00"
        self.run_refresh(later)
        self.assertEqual(before, (self.snapshot.read_bytes(), self.chart.read_bytes()))

    def test_changed_counts_refresh_bars_and_data(self):
        later = copy.deepcopy(self.data)
        later["retrieved_at"] = "2026-10-24T20:31:09+00:00"
        later["repositories"][0]["languages"] = {"Python": 300, "Java": 100}
        self.run_refresh(later)
        self.assertEqual(json.loads(self.snapshot.read_text(encoding="utf-8")), later)
        svg = self.chart.read_text(encoding="utf-8")
        self.assertIn("Python: 75.00%", svg)
        self.assertIn("Java: 25.00%", svg)

    def test_failed_request_preserves_published_files(self):
        before = (self.snapshot.read_bytes(), self.chart.read_bytes())
        with patch.object(stats, "fetch_snapshot", side_effect=URLError("offline")), patch("sys.argv", ["update-language-stats.py"]):
            with self.assertRaises(SystemExit) as error:
                stats.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(before, (self.snapshot.read_bytes(), self.chart.read_bytes()))

    def test_only_public_owned_projects_are_fetched(self):
        repos = [
            {"name": "public-example", "private": False, "fork": False},
            {"name": "private-example", "private": True, "fork": False},
            {"name": "fork-example", "private": False, "fork": True},
            {"name": stats.USER, "private": False, "fork": False},
        ]
        with patch.object(stats, "get_json", side_effect=[repos, {"Python": 100}]) as request:
            snapshot = stats.fetch_snapshot()
        self.assertEqual(snapshot["repositories"], [{"repository": "public-example", "languages": {"Python": 100}}])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0], f"/repos/{stats.USER}/public-example/languages")


if __name__ == "__main__":
    unittest.main()
