"""Refresh aggregate language statistics without publishing repository identities."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
                totals.update(get_json(f"/repos/{USER}/{repo['name']}/languages", token=token))
                repository_count += 1
            if len(batch) < 100:
                break
            page += 1
    return {
        "schema_version": 2,
        "user": USER,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metric": "GitHub-reported language bytes",
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


def render_chart(snapshot):
    totals = Counter(snapshot["languages"])
    totals = Counter({name: size for name, size in totals.items() if size > 0})
    total = sum(totals.values())
    if not total:
        raise ValueError("No language bytes found; the existing chart was not replaced.")
    languages = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    shares = [(name, size / total * 100) for name, size in languages]
    axis_max = min(100, (int(shares[0][1] / 10) + 1) * 10)
    height = 268 + 55 * len(languages)
    plot_bottom = 176 + 55 * (len(languages) - 1) + 20
    footer = plot_bottom + 48
    tehran = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")
    date = datetime.fromisoformat(snapshot["retrieved_at"]).astimezone(tehran).date().isoformat()
    description = "; ".join(f"{name}: {share:.2f}%" for name, share in shares)
    coverage = "Public + authorized private repositories" if snapshot["visibility"] == "public_and_authorized_private" else "Public repositories"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Languages I use</title>',
        f'<desc id="desc">{escape(description)}. Share of GitHub-reported bytes; not proficiency. Public forks and the profile repository are excluded.</desc>',
        f'<rect x="1" y="1" width="1098" height="{height - 2}" rx="22" fill="#0D1925" stroke="#263D4B"/>',
        '<g font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        '<text x="36" y="57" font-size="27" font-weight="700" fill="#F2F6FA">Languages I use</text>',
        '<text x="36" y="91" font-size="18" fill="#A9BFCE">Share of GitHub-reported bytes</text>',
        '<text x="1060" y="135" text-anchor="end" font-size="15" fill="#A9BFCE">SHARE</text>',
    ]
    for tick in range(0, axis_max + 1, 10):
        x = 300 + 630 * tick / axis_max
        parts += [
            f'<path d="M{x:.2f} 154V{plot_bottom}" stroke="#A9BFCE" stroke-opacity=".12"/>',
            f'<text x="{x:.2f}" y="135" text-anchor="middle" font-size="15" fill="#A9BFCE">{tick}%</text>',
        ]
    for index, (name, share) in enumerate(shares):
        y = 176 + index * 55
        width = 630 * share / axis_max
        color = COLORS.get(name, "#91E5CD")
        label = escape(name)
        parts += [
            f'<text x="36" y="{y + 7}" font-size="21" fill="#E4EDF3">{label}</text>',
            f'<rect x="300" y="{y - 14}" width="630" height="24" rx="5" fill="#1A2B38"/>',
            f'<rect x="300" y="{y - 14}" width="{width:.3f}" height="24" rx="{min(5, width / 2):.3f}" fill="{color}"><title>{label}: {totals[name]:,} bytes ({share:.2f}%)</title></rect>',
            f'<text x="1060" y="{y + 7}" text-anchor="end" font-size="22" font-weight="600" fill="{color}">{share:.2f}%</text>',
        ]
    parts += [
        f'<path d="M36 {footer - 24}H1064" stroke="#263D4B"/>',
        f'<text x="36" y="{footer + 4}" font-size="16" fill="#A9BFCE">{coverage} · public forks and profile repository excluded</text>',
        f'<text x="36" y="{footer + 31}" font-size="16" fill="#A9BFCE">Notebook files are reported as Jupyter Notebook. These percentages do not measure proficiency.</text>',
        f'<text x="36" y="{footer + 58}" font-size="15" fill="#8096A7">Updated {date} (Tehran) · Source: GitHub languages API</text>',
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
    status = "Updated" if changed else "Unchanged"
    print(f"{status}: {CHART.relative_to(ROOT)} (aggregate language statistics).")


if __name__ == "__main__":
    main()
