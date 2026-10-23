"""Refresh the profile's public-repository language chart using GitHub's REST API."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import json
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


def get_json(path):
    request = Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER + "-profile"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_snapshot():
    repositories = []
    page = 1
    while True:
        batch = get_json(f"/users/{USER}/repos?type=owner&per_page=100&page={page}")
        for repo in batch:
            if repo["private"] or repo["fork"] or repo["name"].lower() == USER.lower():
                continue
            languages = get_json(f"/repos/{USER}/{repo['name']}/languages")
            repositories.append({"repository": repo["name"], "languages": languages})
        if len(batch) < 100:
            break
        page += 1
    return {
        "user": USER,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metric": "GitHub-reported language bytes",
        "scope": "Public owned repositories; forks and profile repository excluded",
        "repositories": sorted(repositories, key=lambda item: item["repository"].lower()),
    }


def render_chart(snapshot):
    totals = Counter()
    for repo in snapshot["repositories"]:
        totals.update(repo["languages"])
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
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Languages in my public code</title>',
        f'<desc id="desc">{escape(description)}. Share of GitHub-reported bytes; not proficiency. Forks and the profile repository are excluded.</desc>',
        f'<rect x="1" y="1" width="1098" height="{height - 2}" rx="22" fill="#0D1925" stroke="#263D4B"/>',
        '<g font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        '<text x="36" y="57" font-size="27" font-weight="700" fill="#F2F6FA">Languages in my public code</text>',
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
        f'<text x="36" y="{footer + 4}" font-size="16" fill="#A9BFCE">{len(snapshot["repositories"])} public repositories · forks and profile repository excluded</text>',
        f'<text x="36" y="{footer + 31}" font-size="16" fill="#A9BFCE">Notebook files are reported as Jupyter Notebook. These percentages do not measure proficiency.</text>',
        f'<text x="36" y="{footer + 58}" font-size="15" fill="#8096A7">Updated {date} (Tehran) · Source: public GitHub languages API</text>',
        '</g>',
        '</svg>',
    ]
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-snapshot", action="store_true", help="Render saved data without network access")
    args = parser.parse_args()
    try:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if args.from_snapshot else fetch_snapshot()
        svg = render_chart(snapshot)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        parser.exit(1, f"Language chart update failed: {error}\n")
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    if not args.from_snapshot:
        SNAPSHOT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    CHART.write_text(svg, encoding="utf-8")
    print(f"Updated {CHART.relative_to(ROOT)} from {len(snapshot['repositories'])} public repositories.")


if __name__ == "__main__":
    main()
