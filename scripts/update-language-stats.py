"""Refresh aggregate language statistics without publishing repository identities."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from source_lines import repository_lines


USER = "salehghotbani"
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "assets" / "language-stats.json"
CHART = ROOT / "assets" / "language-stats.svg"
COLORS = {
    "Jupyter Notebook": "#F08B52",
    "Java": "#C69B60",
    "TypeScript": "#65A9FF",
    "JavaScript": "#F4D75E",
    "PowerShell": "#B49CFF",
    "CSS": "#DE8CDA",
    "HTML": "#FF786A",
    "Dockerfile": "#65D4CE",
    "Python": "#69C99D", "C": "#CBD5E1", "C#": "#C8A2F2",
    "C++": "#F19BC1", "GDScript": "#79B8DB", "TeX": "#92BD7E",
    "Shell": "#B5CD78", "SCSS": "#CF8EC4", "Swift": "#F5A374",
    "CMake": "#8AB0FF", "Rust": "#DBAB8C", "Mako": "#BC9F84",
}


def get_json(path, *, token=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER + "-profile"}
    token = (token or os.environ.get("GH_TOKEN") or "").strip()
    if "\r" in token or "\n" in token:
        raise ValueError("GitHub API credential has an invalid format.")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        "https://api.github.com" + path,
        headers=headers,
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_snapshot():
    totals = Counter()
    repository_count = 0
    private_token = os.environ.get("LANGUAGE_STATS_TOKEN", "").strip()
    mode = os.environ.get('LANGUAGE_STATS_METRIC', 'auto')
    if mode == 'auto':
        saved = json.loads(SNAPSHOT.read_text(encoding='utf-8')) if SNAPSHOT.exists() else {}
        mode = 'lines' if saved.get('metric', '').startswith('Non-empty source lines') else 'bytes'
    if mode not in ('bytes', 'lines'):
        raise ValueError('Unknown language statistics metric.')
    if mode == 'lines' and private_token:
        # Check source access before downloading any archives. Metadata alone is insufficient.
        sample = get_json('/user/repos?visibility=private&affiliation=owner&per_page=1&page=1', token=private_token)
        if sample:
            from urllib.parse import quote
            try:
                get_json(f"/repos/{USER}/{quote(sample[0]['name'], safe='')}/contents", token=private_token)
            except HTTPError as error:
                if error.code in (401, 403, 404):
                    raise ValueError(f'Private source access denied (HTTP {error.code}). LANGUAGE_STATS_TOKEN needs Contents: Read-only on All repositories. Previous chart preserved.') from None
                raise
    sources = [(f"/users/{USER}/repos?type=owner", None, False)]
    if private_token:
        sources.append(("/user/repos?visibility=private&affiliation=owner", private_token, True))
    for path, token, private in sources:
        page = 1
        while True:
            batch = get_json(f"{path}&per_page=100&page={page}", token=token)
            for repo in batch:
                if (
                    repo["private"] != private
                    or (repo["fork"] and not private)
                    or repo["name"].lower() == USER.lower()
                    or repo["owner"]["login"].lower() != USER.lower()
                ):
                    continue
                # Repository identifiers stay in memory; only combined counts are saved.
                if mode == 'lines':
                    totals.update(repository_lines(USER, repo, token or os.environ.get('GH_TOKEN', '').strip()))
                else:
                    totals.update(get_json(f"/repos/{USER}/{repo['name']}/languages", token=token))
                repository_count += 1
            if len(batch) < 100:
                break
            page += 1
    return {
        "schema_version": 2,
        "user": USER,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metric": "Non-empty source lines (comments included)" if mode == 'lines' else "GitHub-reported language bytes",
        "scope": "Owned repositories; public forks and profile repository excluded",
        "visibility": "public_and_authorized_private" if private_token else "public",
        "repository_count": repository_count,
        "languages": dict(sorted(totals.items())),
    }


def normalize_snapshot(snapshot):
    """Migrate the previous public-only snapshot to the anonymous aggregate format."""
    if "repositories" not in snapshot:
        return snapshot
    totals = Counter()
    for repo in snapshot["repositories"]:
        totals.update(repo["languages"])
    return {
        "schema_version": 2,
        "user": snapshot["user"],
        "retrieved_at": snapshot["retrieved_at"],
        "metric": snapshot["metric"],
        "scope": "Owned repositories; forks and profile repository excluded",
        "visibility": "public",
        "repository_count": len(snapshot["repositories"]),
        "languages": dict(sorted(totals.items())),
    }


def render_chart(snapshot, *, all_languages=False):
    totals = Counter(snapshot["languages"])
    totals = Counter({name: size for name, size in totals.items() if size > 0})
    if not sum(totals.values()):
        raise ValueError("No language bytes found; the existing chart was not replaced.")
    languages = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    languages = languages if all_languages else languages[:8]
    lines = snapshot['metric'].startswith('Non-empty source lines')
    unit = 'lines' if lines else 'bytes'
    heading = 'Source lines' if lines else 'Source size (bytes)'
    height = 116 + 57 * len(languages)
    description = '; '.join(f'{name}: {size:,} {unit}' for name, size in languages)
    maximum = max(totals.values())
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Languages I use</title>',
        f'<desc id="desc">{escape(description)}. {escape(snapshot["metric"])}. Bar lengths use a shared linear scale.</desc>',
        f'<rect x="1" y="1" width="1098" height="{height - 2}" rx="22" fill="#0D1925" stroke="#263D4B"/>',
        '<g font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        f'<text x="36" y="55" font-size="26" font-weight="700" fill="#F2F6FA">{heading}</text>',
        f'<text x="1064" y="55" text-anchor="end" font-size="15" letter-spacing="2" fill="#91E5CD">{"ALL LANGUAGES" if all_languages else "MOST USED"}</text>',
        '<path d="M36 80H1064" stroke="#263D4B"/>',
    ]
    for index, (name, size) in enumerate(languages):
        y = 121 + index * 57
        width = 570 * size / maximum
        if name in COLORS:
            color = COLORS[name]
        else:
            import hashlib, colorsys
            hue = int(hashlib.sha256(name.encode()).hexdigest()[:4], 16) / 65535
            color = '#%02X%02X%02X' % tuple(round(v * 255) for v in colorsys.hls_to_rgb(hue, .72, .6))
        label = escape(name)
        parts += [
            f'<text x="36" y="{y + 7}" font-size="21" fill="#E4EDF3">{label}</text>',
            f'<rect x="290" y="{y - 13}" width="570" height="20" rx="5" fill="#1A2B38"/>',
            f'<rect x="290" y="{y - 13}" width="{width:.3f}" height="20" rx="{min(5, width / 2):.3f}" fill="{color}"><title>{label}: {size:,} {unit}</title></rect>',
            f'<text x="1064" y="{y + 7}" text-anchor="end" font-size="23" font-weight="600" fill="{color}">{size:,}</text>',
        ]
    parts += [
        '</g>',
        '</svg>',
    ]
    return "\n".join(parts) + "\n"


def write_if_changed(path, content):
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-snapshot", action="store_true", help="Render saved data without network access")
    args = parser.parse_args()
    try:
        snapshot = normalize_snapshot(json.loads(SNAPSHOT.read_text(encoding="utf-8"))) if args.from_snapshot else fetch_snapshot()
        if not args.from_snapshot and SNAPSHOT.exists():
            previous = normalize_snapshot(json.loads(SNAPSHOT.read_text(encoding="utf-8")))
            if previous["visibility"] == "public_and_authorized_private" and snapshot["visibility"] == "public":
                raise ValueError("Private statistics credential is missing; keeping the previous chart.")
            fields = ("user", "metric", "scope", "visibility", "repository_count", "languages")
            if all(previous.get(field) == snapshot.get(field) for field in fields):
                snapshot["retrieved_at"] = previous["retrieved_at"]
        svg = render_chart(snapshot)
    except (HTTPError, URLError, TimeoutError):
        # API exceptions can contain private URLs. Keep workflow logs anonymous.
        parser.exit(1, "Language chart update failed: GitHub API unavailable. Check credentials, permissions, and network. Previous chart preserved.\n")
    except ValueError as error:
        parser.exit(1, f"Language chart update failed: {error}\n")
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    changed = write_if_changed(SNAPSHOT, json.dumps(snapshot, indent=2) + "\n")
    changed = write_if_changed(CHART, svg) or changed
    changed = write_if_changed(CHART.with_name('language-stats-all.svg'), render_chart(snapshot, all_languages=True)) or changed
    status = "Updated" if changed else "Unchanged"
    print(f"{status}: {CHART.relative_to(ROOT)} (aggregate language statistics).")


if __name__ == "__main__":
    main()
