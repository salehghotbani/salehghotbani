import copy
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch
from urllib.error import URLError


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update-language-stats.py"
SPEC = importlib.util.spec_from_file_location("language_stats", SCRIPT)
sys.path.insert(0, str(SCRIPT.parent))
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
        environment = patch.dict(os.environ, {"LANGUAGE_STATS_TOKEN": "", "LANGUAGE_STATS_METRIC": "bytes"})
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
        self.assertIn("Python: 300 bytes", svg)
        self.assertIn("Java: 100 bytes", svg)

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
            self.repo(stats.USER, private=True),
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
        self.assertIn("Java: 300 bytes", published)

    def test_line_mode_checks_private_source_access_before_collecting(self):
        with patch.dict(os.environ, {"LANGUAGE_STATS_TOKEN": "test-credential", "LANGUAGE_STATS_METRIC": "lines"}), patch.object(stats, 'get_json', side_effect=[[self.repo('private-example', private=True)], URLError('not authorized')]) as api, patch.object(stats, 'repository_lines') as count:
            with self.assertRaises(URLError):
                stats.fetch_snapshot()
        self.assertIn('/contents', api.call_args.args[0])
        count.assert_not_called()

    def test_line_mode_publishes_only_combined_counts(self):
        responses = [[self.repo('public-example')]]
        with patch.dict(os.environ, {"LANGUAGE_STATS_METRIC": "lines"}), patch.object(stats, 'get_json', side_effect=responses), patch.object(stats, 'repository_lines', return_value={'Python': 12}):
            snapshot = stats.fetch_snapshot()
        self.assertEqual(snapshot['metric'], 'Non-empty source lines (comments included)')
        self.assertEqual(snapshot['languages'], {'Python': 12})
        self.assertNotIn('public-example', json.dumps(snapshot))
        self.assertIn('Python: 12 lines', stats.render_chart(snapshot))

    def test_chart_is_compact_and_has_no_footer_or_percentages(self):
        snapshot = copy.deepcopy(self.data)
        snapshot['languages'] = {f'Language-{i}': i + 1 for i in range(20)}
        svg = stats.render_chart(snapshot)
        self.assertEqual(svg.count('<rect x="290"'), 16)
        self.assertNotIn('%', svg)
        self.assertNotIn('Updated ', svg)
        self.assertNotIn('not proficiency', svg)
        self.assertIn('Language-0: 1 bytes', stats.render_chart(snapshot, all_languages=True))

    def test_private_repository_pagination(self):
        repos = [self.repo(f"private-project-{index}", private=True, fork=index % 2 == 0) for index in range(237)]
        pages = []

        def respond(path, **kwargs):
            if path.startswith(f"/users/{stats.USER}/repos?"):
                return []
            if path.startswith("/user/repos?"):
                page = int(path.rsplit("page=", 1)[1])
                pages.append(page)
                return repos[(page - 1) * 100:page * 100]
            if path.endswith("/languages"):
                return {"Python": 10, "Java": 5}
            self.fail("Unexpected API request")

        with patch.dict(os.environ, {"LANGUAGE_STATS_TOKEN": "test-credential"}), patch.object(stats, "get_json", side_effect=respond):
            snapshot = stats.fetch_snapshot()
        self.assertEqual(pages, [1, 2, 3])
        self.assertEqual(snapshot["languages"], {"Python": 2370, "Java": 1185})
        self.assertEqual(snapshot["repository_count"], 237)
        self.assertNotIn("private-project-", json.dumps(snapshot) + stats.render_chart(snapshot))

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
