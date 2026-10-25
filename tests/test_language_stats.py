import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
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
            "schema_version": 2,
            "user": stats.USER,
            "retrieved_at": "2026-10-23T20:31:09+00:00",
            "metric": "GitHub-reported language bytes",
            "scope": "Owned repositories; forks and profile repository excluded",
            "visibility": "public",
            "repository_count": 1,
            "languages": {"Python": 100},
        }
        self.snapshot.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        self.chart.write_text(stats.render_chart(self.data), encoding="utf-8")
        environment = patch.dict(os.environ, {"LANGUAGE_STATS_TOKEN": ""})
        environment.start()
        self.addCleanup(environment.stop)
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
        later["languages"] = {"Python": 300, "Java": 100}
        self.run_refresh(later)
        self.assertEqual(json.loads(self.snapshot.read_text(encoding="utf-8")), later)
        svg = self.chart.read_text(encoding="utf-8")
        self.assertIn("Python: 75.00%", svg)
        self.assertIn("Java: 25.00%", svg)

    def test_failed_request_preserves_published_files(self):
        before = (self.snapshot.read_bytes(), self.chart.read_bytes())
        stderr = io.StringIO()
        with patch.object(stats, "fetch_snapshot", side_effect=URLError("https://api.github.com/repos/example/private-example/languages")), patch("sys.argv", ["update-language-stats.py"]), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                stats.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(before, (self.snapshot.read_bytes(), self.chart.read_bytes()))
        self.assertNotIn("private-example", stderr.getvalue())

    def test_only_public_owned_projects_are_fetched(self):
        repos = [
            self.repo("public-example"),
            self.repo("private-example", private=True),
            self.repo("fork-example", fork=True),
            self.repo(stats.USER),
        ]
        with patch.object(stats, "get_json", side_effect=[repos, {"Python": 100}]) as request:
            snapshot = stats.fetch_snapshot()
        self.assertEqual(snapshot["languages"], {"Python": 100})
        self.assertEqual(snapshot["visibility"], "public")
        self.assertEqual(snapshot["repository_count"], 1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0], f"/repos/{stats.USER}/public-example/languages")

    @staticmethod
    def repo(name, *, private=False, fork=False, owner=stats.USER):
        return {"name": name, "private": private, "fork": fork, "owner": {"login": owner}}

    def test_private_counts_are_aggregated_without_repository_identifiers(self):
        private_repos = [
            self.repo("private-example", private=True),
            self.repo("foreign-example", private=True, owner="another-owner"),
            self.repo("private-fork", private=True, fork=True),
        ]
        responses = [[self.repo("public-example")], {"Python": 100}, private_repos, {"Java": 300}]
        with patch.dict(os.environ, {"LANGUAGE_STATS_TOKEN": "test-credential"}), patch.object(stats, "get_json", side_effect=responses) as request:
            snapshot = stats.fetch_snapshot()
        self.assertEqual(snapshot["languages"], {"Java": 300, "Python": 100})
        self.assertEqual(snapshot["visibility"], "public_and_authorized_private")
        self.assertEqual(snapshot["repository_count"], 2)
        for call in request.call_args_list[2:]:
            self.assertEqual(call.kwargs["token"], "test-credential")
        published = json.dumps(snapshot) + stats.render_chart(snapshot)
        for identifier in ["private-example", "foreign-example", "private-fork", "test-credential"]:
            self.assertNotIn(identifier, published)
        self.assertNotIn('"repositories"', json.dumps(snapshot))
        self.assertIn("Java: 75.00%", published)

    def test_private_repository_pagination(self):
        skipped = [self.repo(f"fork-{index}", private=True, fork=True) for index in range(100)]
        responses = [[], skipped, [self.repo("last-example", private=True)], {"Java": 100}]
        with patch.dict(os.environ, {"LANGUAGE_STATS_TOKEN": "test-credential"}), patch.object(stats, "get_json", side_effect=responses) as request:
            snapshot = stats.fetch_snapshot()
        self.assertIn("page=2", request.call_args_list[2].args[0])
        self.assertEqual(snapshot["languages"], {"Java": 100})
        self.assertEqual(snapshot["repository_count"], 1)

    def test_missing_private_credential_does_not_replace_private_totals(self):
        previous = copy.deepcopy(self.data)
        previous["visibility"] = "public_and_authorized_private"
        self.snapshot.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
        self.chart.write_text(stats.render_chart(previous), encoding="utf-8")
        before = (self.snapshot.read_bytes(), self.chart.read_bytes())
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_refresh(copy.deepcopy(self.data))
        self.assertEqual(before, (self.snapshot.read_bytes(), self.chart.read_bytes()))

    def test_legacy_snapshot_migrates_to_anonymous_totals(self):
        legacy = {key: self.data[key] for key in ["user", "retrieved_at", "metric", "scope"]}
        legacy["repositories"] = [{"repository": "public-example", "languages": {"Python": 100}}]
        migrated = stats.normalize_snapshot(legacy)
        self.assertEqual(migrated, self.data)
        self.assertNotIn("public-example", json.dumps(migrated))


if __name__ == "__main__":
    unittest.main()
