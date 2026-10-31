#!/usr/bin/env python3
"""Regenerate the profile telemetry SVGs from the live GitHub API.

Runs in CI (GITHUB_TOKEN) and locally (GH_TOKEN). Stdlib only.

Outputs:
  assets/stats.svg     repos / stars / followers + language split by bytes
  assets/activity.svg  real contribution calendar (levels 0-4) for the last year
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

LOGIN = "muhammadsohaimmuqtada"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "assets"))

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("GH_TOKEN or GITHUB_TOKEN must be set")

LANG_COLORS = {
    "Python": "#3572A5", "C": "#8b8f9a", "C++": "#f34b7d", "Rust": "#dea584",
    "TypeScript": "#3178c6", "PHP": "#4F5D95", "CSS": "#663399", "JavaScript": "#f1e05a",
    "Shell": "#89e051", "HTML": "#e34c26", "Makefile": "#427819", "Dockerfile": "#384d54",
}
FALLBACK = "#8b8f9a"
INK, MUTED, ACCENT = "#e9eefb", "#9aa7c2", "#6fc3f7"
PANEL, BORDER = "#0b1122", "#253154"
LEVEL_FILL = {0: "#151c2c", 1: "rgba(111,195,247,.35)", 2: "rgba(111,195,247,.55)", 3: "rgba(111,195,247,.78)", 4: "#6fc3f7"}
MONO = "ui-monospace,'JetBrains Mono',Menlo,Consolas,monospace"


def api(path):
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-stats",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def graphql(query, variables):
    req = urllib.request.Request("https://api.github.com/graphql", data=json.dumps(
        {"query": query, "variables": variables}).encode(), headers={
        "Authorization": "Bearer " + TOKEN, "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors"):
        sys.exit("graphql error: %s" % data["errors"])
    return data["data"]


def collect():
    user = api("/users/" + LOGIN)
    repos, page = [], 1
    while True:
        batch = api("/users/%s/repos?per_page=100&page=%d" % (LOGIN, page))
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    stars = sum(r["stargazers_count"] for r in repos if not r["fork"])

    lang_bytes = {}
    for r in repos:
        if r["fork"] or r["size"] == 0:
            continue
        try:
            for k, v in api("/repos/%s/languages" % r["full_name"]).items():
                lang_bytes[k] = lang_bytes.get(k, 0) + v
        except Exception:
            continue

    cal = graphql(
        "query($l:String!){user(login:$l){contributionsCollection{"
        "contributionCalendar{totalContributions weeks{contributionDays{"
        "date contributionCount color}}}}}}", {"l": LOGIN})["user"]["contributionsCollection"]["contributionCalendar"]

    return {
        "followers": user["followers"], "repos": user["public_repos"], "stars": stars,
        "langs": sorted(lang_bytes.items(), key=lambda kv: -kv[1]),
        "total_contrib": cal["totalContributions"],
        "weeks": cal["weeks"], "asof": datetime.now(timezone.utc).strftime("%b %d, %Y"),
    }


def stats_svg(d):
    total = sum(v for _, v in d["langs"]) or 1
    top = d["langs"][:6]
    rest = d["langs"][6:]
    shown = top + ([("Other", sum(v for _, v in rest))] if rest else [])

    bar, x = [], 24.0
    for name, v in shown:
        w = max(2.0, 422.0 * v / total)
        bar.append('<rect x="%.1f" y="0" width="%.1f" height="6" rx="2" fill="%s"/>'
                   % (x, w - (2.0 if x + w < 446 else 0), LANG_COLORS.get(name, FALLBACK)))
        x += w
    legend, lx, ly = [], 24.0, 0
    for i, (name, v) in enumerate(shown):
        if i == 4:
            lx, ly = 24.0, 1
        label = "%s %d%%" % (name, round(100.0 * v / total))
        est = 14 + 6.4 * len(label) + 22
        if lx + est > 446 and ly == 0:
            lx, ly = 24.0, 1
        legend.append('<g transform="translate(%.1f,%d)"><circle cx="4" cy="4" r="4" fill="%s"/>'
                      '<text x="13" y="8.5" font-size="11.5" fill="%s" font-family="%s">%s</text></g>'
                      % (lx, ly * 20, LANG_COLORS.get(name, FALLBACK), MUTED, MONO, name))
        lx += est

    nums = "".join(
        '<g text-anchor="middle" font-family="%s">'
        '<text x="%d" y="86" font-size="26" font-weight="650" fill="%s">%s</text>'
        '<text x="%d" y="104" font-size="9.5" letter-spacing="2.5" fill="%s">%s</text></g>'
        % (MONO, cx, INK, val, cx, MUTED, lab)
        for cx, val, lab in ((102, d["repos"], "REPOS"), (235, d["stars"], "STARS"), (368, d["followers"], "FOLLOWERS")))

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 470 190" width="470" height="190" '
        'role="img" aria-label="GitHub stats: repos, stars, followers and language split">'
        '<rect x="0.5" y="0.5" width="469" height="189" rx="12" fill="%s" stroke="%s"/>'
        '<text x="24" y="30" font-size="11" letter-spacing="2.5" fill="%s" font-family="%s">STATS</text>'
        '<text x="446" y="30" text-anchor="end" font-size="10" fill="%s" font-family="%s">via GitHub API &#183; %s</text>'
        '<line x1="24" y1="40" x2="446" y2="40" stroke="%s" stroke-opacity=".6"/>'
        '%s'
        '<g transform="translate(24,126)">%s</g>'
        '<g transform="translate(24,146)">%s</g>'
        '</svg>'
    ) % (PANEL, BORDER, MUTED, MONO, MUTED, MONO, d["asof"], BORDER, nums,
         "".join(bar).replace('x="%.1f"' % 24, 'x="0"', 1), "".join(legend))


GITHUB_DAY_COLORS = {"#ebedf0": 0, "#9be9a8": 1, "#40c463": 2, "#30a14d": 3, "#216e39": 4}


def day_level(day, q1, q2, q3):
    """Map a calendar day to 0-4 via GitHub's own color scale, falling back to count quartiles."""
    lvl = GITHUB_DAY_COLORS.get((day.get("color") or "").lower())
    if lvl is not None:
        return lvl
    c = day.get("contributionCount") or 0
    if c == 0:
        return 0
    if c <= q1:
        return 1
    if c <= q2:
        return 2
    if c <= q3:
        return 3
    return 4


def activity_svg(d):
    cell, gap, x0, y0 = 12, 3, 24, 44
    cols = [[day for day in w["contributionDays"]] for w in d["weeks"]]
    counts = sorted(day["contributionCount"] for w in cols for day in w if day["contributionCount"] > 0)
    if counts:
        q1, q2, q3 = counts[len(counts) // 4], counts[len(counts) // 2], counts[3 * len(counts) // 4]
    else:
        q1 = q2 = q3 = 1
    rects = []
    for wi, week in enumerate(cols):
        for di, day in enumerate(week):
            lvl = day_level(day, q1, q2, q3)
            rects.append('<rect x="%d" y="%d" width="12" height="12" rx="2.5" fill="%s"/>'
                         % (x0 + wi * (cell + gap), y0 + di * (cell + gap), LEVEL_FILL[lvl]))
    gw = x0 + len(cols) * (cell + gap)
    W = max(720, gw + 24)
    H = y0 + 7 * (cell + gap) + 34
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
        'role="img" aria-label="Contribution activity heatmap for the last twelve months">'
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>'
        '<text x="24" y="30" font-size="11" letter-spacing="2.5" fill="%s" font-family="%s">COMMIT ACTIVITY &#8212; LAST 12 MONTHS</text>'
        '<text x="%d" y="30" text-anchor="end" font-size="10" fill="%s" font-family="%s">%s contributions</text>'
        '%s</svg>'
    ) % (W, H, W, H, W - 1, H - 1, PANEL, BORDER, MUTED, MONO, W - 24, MUTED, MONO,
         "{:,}".format(d["total_contrib"]), "".join(rects))


def main():
    d = collect()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats.svg", stats_svg(d)), ("activity.svg", activity_svg(d))):
        with open(os.path.join(OUT, name), "w") as f:
            f.write(svg)
        print("wrote assets/%s" % name)


if __name__ == "__main__":
    main()
