#!/usr/bin/env python3
"""Render tingfeng347's profile as an animated terminal dashboard (neofetch style).

Everything shown is drawn from real GitHub data: the contribution calendar drives
the heatmap, commit history per repository drives the language ranking and the
"top repo" line, and the user profile fills the small info block.

The output is one self-contained SVG per colour scheme (no scripts, no external
resources beyond an inlined avatar), so it animates inside a README <img>.

Usage: GITHUB_TOKEN=... python scripts/generate_dashboard.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "tingfeng347"
OUT = Path(__file__).resolve().parent.parent / "assets"

W, H = 1160, 604
MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"

# GitHub's own surfaces so the plate melts into the page.
THEMES = {
    "dark": dict(
        bg="#0d1117", panel="#161b22", border="#30363d", fg="#e6edf3", muted="#8b949e",
        accent="#3fb950", accent2="#58a6ff", warn="#d29922", key="#39c5cf",
        dots=["#ff5f56", "#ffbd2e", "#27c93f"],
        heat=["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"],
        grid="#21262d",
    ),
    "light": dict(
        bg="#ffffff", panel="#f6f8fa", border="#d0d7de", fg="#1f2328", muted="#656d76",
        accent="#1a7f37", accent2="#0969da", warn="#9a6700", key="#1b7c83",
        dots=["#ff5f56", "#ffbd2e", "#27c93f"],
        heat=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        grid="#d8dee4",
    ),
}


# ── data ──────────────────────────────────────────────────────────────

def graphql(token, query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": LOGIN},
    )
    last = None
    for attempt in range(3):  # the API occasionally drops a handshake; a retry is enough
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            break
        except OSError as exc:  # noqa: PERF203
            last = exc
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 3)
    else:  # pragma: no cover
        raise last
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]


META = """query($login:String!){user(login:$login){
  login name createdAt followers{totalCount} repositories(privacy:PUBLIC){totalCount}
  contributionsCollection{totalCommitContributions totalIssueContributions
    totalPullRequestContributions totalPullRequestReviewContributions
    contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""

# One window per quarter keeps every repository under 100 active days,
# so no nested paging is needed.
BY_REPO = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
  contributionsCollection(from:$from,to:$to){commitContributionsByRepository(maxRepositories:100){
    repository{nameWithOwner stargazerCount primaryLanguage{name}}
    contributions(first:100){nodes{occurredAt commitCount}}}}}}"""


def fetch(token):
    user = graphql(token, META, {"login": LOGIN})["user"]
    cc = user["contributionsCollection"]
    weeks = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]]
             for w in cc["contributionCalendar"]["weeks"]]

    start = dt.date.fromisoformat(weeks[0][0][0])
    end = dt.date.fromisoformat(weeks[-1][-1][0]) + dt.timedelta(days=1)

    languages: dict[str, int] = {}
    repos: dict[str, dict] = {}
    cursor = start
    while cursor < end:
        upto = min(cursor + dt.timedelta(days=91), end)
        span = {"login": LOGIN, "from": f"{cursor}T00:00:00Z", "to": f"{upto}T00:00:00Z"}
        data = graphql(token, BY_REPO, span)["user"]["contributionsCollection"]
        for entry in data["commitContributionsByRepository"]:
            repo = entry["repository"]
            name = repo["nameWithOwner"]
            lang = (repo.get("primaryLanguage") or {}).get("name")
            total = sum(n["commitCount"] for n in entry["contributions"]["nodes"])
            if not total:
                continue
            repos.setdefault(name, {"commits": 0, "stars": repo.get("stargazerCount", 0)})
            repos[name]["commits"] += total
            if lang:
                languages[lang] = languages.get(lang, 0) + total
        cursor = upto

    days = [(date, n) for week in weeks for date, n in week if n > 0]
    dates = sorted(dt.date.fromisoformat(d) for d, _ in days)
    streak = 0
    if dates:
        cursor_day = dates[-1]
        present = set(dates)
        while cursor_day in present:
            streak += 1
            cursor_day -= dt.timedelta(days=1)

    return dict(
        login=user["login"], name=user.get("name") or user["login"],
        since=user["createdAt"][:4],
        followers=user["followers"]["totalCount"],
        repos=user["repositories"]["totalCount"],
        commits=cc["totalCommitContributions"],
        issues=cc["totalIssueContributions"],
        prs=cc["totalPullRequestContributions"],
        reviews=cc["totalPullRequestReviewContributions"],
        weeks=weeks,
        contributions=sum(n for _, n in days),
        active_days=len(days),
        streak=streak,
        languages=sorted(languages.items(), key=lambda kv: -kv[1])[:5],
        top_repos=sorted(repos.items(), key=lambda kv: -kv[1]["commits"])[:3],
    )


def avatar_data_uri(login):
    try:
        with urllib.request.urlopen(f"https://github.com/{login}.png?size=240", timeout=30) as resp:
            return "data:image/png;base64," + base64.b64encode(resp.read()).decode()
    except OSError:
        return None


def head_hash():
    sha = os.environ.get("GITHUB_SHA")
    if not sha:
        try:
            import subprocess
            sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True,
                                 cwd=OUT.parent).stdout.strip()
        except OSError:
            sha = ""
    return sha or "-------"


# ── layout helpers ────────────────────────────────────────────────────

def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def typed(text, x, y, advance, cls, start, step=0.035, fill=None):
    """One <text> per glyph on a fixed grid so every character can arrive alone."""
    paint = f' fill="{fill}"' if fill else ""
    cells = []
    for i, ch in enumerate(text):
        delay = start + i * step
        cells.append(
            f'<text class="{cls}"{paint} x="{x + i * advance:.1f}" y="{y}" '
            f'style="animation-delay:{delay:.2f}s">{esc(ch)}</text>'
        )
    return "".join(cells)


def level(count, top):
    if count <= 0:
        return 0
    for lvl, cut in ((4, 0.55), (3, 0.3), (2, 0.12)):
        if count >= max(1, top * cut):
            return lvl
    return 1


# ── plate ─────────────────────────────────────────────────────────────

def render(theme, d, sha, today, avatar):
    c = THEMES[theme]
    pad = 8
    win = f'<rect x="{pad}" y="{pad}" width="{W - 2 * pad}" height="{H - 2 * pad}" rx="14" ' \
          f'fill="{c["panel"]}" stroke="{c["border"]}"/>'

    dots = "".join(f'<circle cx="{34 + i * 20}" cy="30" r="6" fill="{col}"/>'
                   for i, col in enumerate(c["dots"]))
    titlebar = (f'{dots}'
                f'<text class="ttl" x="116" y="35">{LOGIN}@github — zsh</text>'
                f'<line x1="{pad}" y1="50" x2="{W - pad}" y2="50" stroke="{c["border"]}"/>')

    # prompt: the command types itself, then a caret keeps blinking
    ch = 9.6
    cmd = "neofetch"
    ux, uy = 30, 84
    user_label = f"{LOGIN}@github"
    prompt = (
        f'<text class="puser" x="{ux}" y="{uy}">{user_label}</text>'
        f'<text class="ppath" x="{ux + len(user_label) * ch + 6:.1f}" y="{uy}">~</text>'
        f'<text class="pcaret" x="{ux + len(user_label) * ch + 22:.1f}" y="{uy}">❯</text>'
        + typed(cmd, ux + len(user_label) * ch + 44, uy, ch, "pcmd", 0.5, 0.06)
    )
    caret = (f'<rect class="blink" x="{ux + len(user_label) * ch + 44 + len(cmd) * ch + 2:.1f}" '
             f'y="{uy - 13}" width="8" height="18" fill="{c["fg"]}" style="animation-delay:1.4s"/>')

    # avatar tile (left) — inlined so it survives GitHub's camo sandbox
    ax, ay, asz = 66, 116, 190
    if avatar:
        art = (f'<image x="{ax}" y="{ay}" width="{asz}" height="{asz}" preserveAspectRatio="xMidYMid slice" '
               f'href="{avatar}" clip-path="url(#avatarClip)"/>')
    else:
        art = (f'<rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" fill="{c["bg"]}"/>'
               f'<text class="mono2" x="{ax + asz / 2:.1f}" y="{ay + asz / 2 + 16:.1f}">'
               f'{esc(d["login"][:2].upper())}</text>')
    avatar_tile = (
        f'<g><rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" rx="16" fill="{c["bg"]}" stroke="{c["border"]}"/>'
        f'{art}'
        f'<rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" rx="16" fill="none" '
        f'stroke="{c["accent"]}" stroke-width="1.6" opacity=".75"/></g>'
    )

    # info block (right)
    ix, vx = 300, 500
    rows = [
        ("Languages", " · ".join(name for name, _ in d["languages"]) or "—", c["accent2"]),
        ("Repos · Followers", f'{d["repos"]} · {d["followers"]}', c["fg"]),
        ("Contributions", f'{d["contributions"]:,} / year', c["fg"]),
        ("Commits", f'{d["commits"]:,}', c["fg"]),
        ("PRs / Issues", f'{d["prs"]} / {d["issues"]}', c["fg"]),
        ("Active days", f'{d["active_days"]} · streak {d["streak"]}d', c["fg"]),
    ]
    if d["top_repos"]:
        name, meta = d["top_repos"][0]
        rows.append(("Top repo", f'{name.split("/")[-1]}  ★{meta["stars"]}', c["warn"]))

    info = [f'<text class="host" x="{ix}" y="150">{LOGIN}@github</text>'
            f'<text class="since" x="{ix + 250}" y="150">since {d["since"]}</text>',
            f'<line x1="{ix}" y1="163" x2="{ix + 300}" y2="163" stroke="{c["border"]}"/>']
    y = 194
    for i, (key, val, col) in enumerate(rows):
        delay = 1.1 + i * 0.16
        info.append(f'<text class="key" x="{ix}" y="{y}" style="animation-delay:{delay:.2f}s">{key}</text>')
        info.append(f'<text class="val" x="{vx}" y="{y}" fill="{col}" '
                    f'style="animation-delay:{delay + 0.06:.2f}s">{esc(val)}</text>')
        y += 30

    # contribution heatmap (a full year, newest on the right)
    weeks = d["weeks"]
    cell, gap = 12, 3
    step = cell + gap
    hx, hy = 66, 430
    top = max((n for w in weeks for _, n in w), default=1)
    cells = []
    for col, week in enumerate(weeks):
        for row, (_, n) in enumerate(week):
            lvl = level(n, top)
            delay = 2.0 + col * 0.012
            cells.append(f'<rect class="pop" x="{hx + col * step}" y="{hy + row * step}" '
                         f'width="{cell}" height="{cell}" rx="2.5" fill="{c["heat"][lvl]}" '
                         f'style="animation-delay:{delay:.2f}s"/>')
    # months across the top of the heatmap
    months = []
    seen = set()
    for col, week in enumerate(weeks):
        first = dt.date.fromisoformat(week[0][0])
        if first.month not in seen and first.day <= 14:
            seen.add(first.month)
            months.append(f'<text class="mo" x="{hx + col * step}" y="{hy - 8}">{first.strftime("%b")}</text>')

    legend_x = hx + len(weeks) * step + 26
    legend = (f'<text class="lg" x="{legend_x}" y="{hy + 30}">Less</text>')
    for i, col in enumerate(c["heat"]):
        legend += (f'<rect x="{legend_x + 34 + i * (cell + 3)}" y="{hy + 18}" width="{cell}" '
                   f'height="{cell}" rx="2.5" fill="{col}"/>')
    legend += f'<text class="lg" x="{legend_x + 34 + 5 * (cell + 3) + 2}" y="{hy + 30}">More</text>'

    cap = (f'<text class="cap" x="{hx}" y="{hy + 7 * step + 26}">'
           f'{d["contributions"]:,} contributions in the last year · {len(weeks)} weeks</text>')

    footer = (f'<text class="ft" x="{pad + 24}" y="{H - 22}">{LOGIN}.github.io</text>'
              f'<text class="ft" x="{W - pad - 24}" y="{H - 22}" text-anchor="end">'
              f'rendered {today:%Y-%m-%d} · {sha}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{LOGIN} — terminal dashboard</title>
<style>
text{{font-family:{MONO}}}
.ttl{{font-size:14px;fill:{c["muted"]}}}
.puser{{font-size:16px;fill:{c["accent"]};font-weight:700}}
.ppath{{font-size:16px;fill:{c["accent2"]};font-weight:700}}
.pcaret{{font-size:16px;fill:{c["fg"]}}}
.pcmd{{font-size:16px;fill:{c["fg"]};text-anchor:middle;opacity:0;animation:fade .01s linear forwards}}
.blink{{opacity:0;animation:blink 1.05s steps(1) infinite}}
.mono2{{font-size:64px;font-weight:700;fill:{c["muted"]};text-anchor:middle}}
.host{{font-size:19px;font-weight:700;fill:{c["accent"]}}}
.since{{font-size:13px;fill:{c["muted"]}}}
.key{{font-size:15px;font-weight:700;fill:{c["key"]};opacity:0;animation:slide .4s ease-out both}}
.val{{font-size:15px;opacity:0;animation:slide .4s ease-out both}}
.mo{{font-size:11px;fill:{c["muted"]};text-anchor:middle}}
.lg{{font-size:12px;fill:{c["muted"]}}}
.cap{{font-size:13px;fill:{c["muted"]}}}
.ft{{font-size:13px;fill:{c["muted"]}}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.5,.5,1) both}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes slide{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:translateX(0)}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@keyframes pop{{from{{transform:scale(0)}}to{{transform:scale(1)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.pcmd,.key,.val,.pop,.blink{{opacity:1}}}}
</style>
<defs>
<clipPath id="avatarClip"><rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" rx="16"/></clipPath>
</defs>
{win}
{titlebar}
{prompt}{caret}
{avatar_tile}
{"".join(info)}
{"".join(cells)}
{"".join(months)}
{legend}
{cap}
{footer}
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    d = fetch(token)
    today = dt.date.fromisoformat(d["weeks"][-1][-1][0])
    sha = head_hash()
    avatar = avatar_data_uri(LOGIN)
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"terminal-{theme}.svg").write_text(
            render(theme, d, sha, today, avatar), encoding="utf-8")
    langs = ", ".join(f"{n}({v})" for n, v in d["languages"])
    print(f"contributions={d['contributions']} repos={d['repos']} langs={langs}")


if __name__ == "__main__":
    main()
