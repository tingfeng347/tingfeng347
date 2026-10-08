#!/usr/bin/env python3
"""Render tingfeng347's profile as an animated, frameless terminal.

Everything shown is drawn from real GitHub data: the contribution calendar drives
the heatmap, commit history per repository drives the language ranking and the
"top repo" line, and the user profile fills the info block.

Flow, animated on load: the intro banner appears, a short coding session types
itself line by line (ending on `neofetch`), then the neofetch output — info block
and yearly heatmap — fades in. One self-contained SVG per colour scheme (no
scripts, no external resources), so it animates inside a README <img>.

Usage: GITHUB_TOKEN=... python scripts/generate_dashboard.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "tingfeng347"
OUT = Path(__file__).resolve().parent.parent / "assets"

W, H = 1160, 700
X0 = 40
ADV = 9.6  # monospace cell at 16px
MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"

# GitHub's own surfaces so the plate melts into the page.
THEMES = {
    "dark": dict(
        bg="#0d1117", fg="#e6edf3", muted="#8b949e",
        accent="#3fb950", accent2="#58a6ff", warn="#d29922", key="#39c5cf",
        prompt_user="#3fb950", prompt_path="#58a6ff",
        heat=["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"],
    ),
    "light": dict(
        bg="#ffffff", fg="#1f2328", muted="#656d76",
        accent="#1a7f37", accent2="#0969da", warn="#9a6700", key="#1b7c83",
        prompt_user="#1a7f37", prompt_path="#0969da",
        heat=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    ),
}

INTRO = [
    ("Hi There 👋, I'm tingfeng347", 24, "i1"),
    ("🎯 Focused · Full-Stack & AI Agent Developer", 17, "i2"),
    ("Building Coding Agents · Open Source · Knowledge Graphs", 16, "i3"),
]
COMMANDS = [
    'git add -A && git commit -m "feat: animated dashboard"',
    'python -m windcode --task "render my stats"',
    "git push origin main",
    "neofetch",
]


# ── data ──────────────────────────────────────────────────────────────

def graphql(token, query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": LOGIN},
    )
    for attempt in range(3):  # the API occasionally drops a handshake; a retry is enough
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 3)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]


META = """query($login:String!){user(login:$login){
  login name createdAt followers{totalCount} repositories(privacy:PUBLIC){totalCount}
  contributionsCollection{totalCommitContributions totalIssueContributions
    totalPullRequestContributions totalPullRequestReviewContributions
    contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""

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

    active = sorted(dt.date.fromisoformat(d) for d, n in
                    ((day, n) for week in weeks for day, n in week) if n > 0)
    streak = 0
    if active:
        cursor_day, present = active[-1], set(active)
        while cursor_day in present:
            streak += 1
            cursor_day -= dt.timedelta(days=1)

    return dict(
        login=user["login"], since=user["createdAt"][:4],
        followers=user["followers"]["totalCount"],
        repos=user["repositories"]["totalCount"],
        commits=cc["totalCommitContributions"],
        issues=cc["totalIssueContributions"],
        prs=cc["totalPullRequestContributions"],
        weeks=weeks,
        contributions=sum(n for week in weeks for _, n in week),
        active_days=len(active),
        streak=streak,
        languages=sorted(languages.items(), key=lambda kv: -kv[1])[:5],
        top_repos=sorted(repos.items(), key=lambda kv: -kv[1]["commits"])[:1],
    )


def head_hash():
    sha = os.environ.get("GITHUB_SHA")
    if not sha:
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                 text=True, cwd=OUT.parent).stdout.strip()
        except OSError:
            sha = ""
    return (sha or "-------")[:7]


# ── drawing helpers ───────────────────────────────────────────────────

def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def typed(text, x, y, cls, start, step):
    """One <text> per glyph on a fixed grid so every character can arrive alone."""
    return "".join(
        f'<text class="{cls}" x="{x + i * ADV:.1f}" y="{y}" '
        f'style="animation-delay:{start + i * step:.2f}s">{esc(ch)}</text>'
        for i, ch in enumerate(text)
    )


def level(count, top):
    if count <= 0:
        return 0
    for lvl, cut in ((4, 0.55), (3, 0.3), (2, 0.12)):
        if count >= max(1, top * cut):
            return lvl
    return 1


# ── plate ─────────────────────────────────────────────────────────────

def render(theme, d, sha, today):
    c = THEMES[theme]

    # 1) intro banner (the original typing-intro, now living inside the terminal)
    intro, iy = [], 54
    for idx, (text, size, cls) in enumerate(INTRO):
        delay = 0.2 + idx * 0.25
        intro.append(f'<text class="{cls}" x="{X0}" y="{iy}" style="animation-delay:{delay:.2f}s">'
                     f'{esc(text)}</text>')
        iy += 32 if size > 20 else 28

    # 2) a short coding session types itself, one prompt line at a time
    prompt = f"{LOGIN}@github ~ ❯ "
    session, t = [], 1.35
    for i, cmd in enumerate(COMMANDS):
        ly = 158 + i * 28
        session.append(f'<text class="pr" x="{X0}" y="{ly}" style="animation-delay:{t:.2f}s">{esc(prompt)}</text>')
        session.append(typed(cmd, X0 + len(prompt) * ADV, ly, "kc", t + 0.15, 0.015))
        t += 0.15 + len(cmd) * 0.015 + 0.3
    last_y = 158 + (len(COMMANDS) - 1) * 28
    caret_x = X0 + (len(prompt) + len(COMMANDS[-1])) * ADV + 3
    session.append(f'<rect class="blink" x="{caret_x:.1f}" y="{last_y - 13}" width="8" height="18" '
                   f'fill="{c["fg"]}" style="animation-delay:{t:.2f}s"/>')
    out = t + 0.25  # neofetch output begins

    # 3) neofetch output
    k1, v1, k2, v2 = X0, 274, 594, 824
    head = (f'<text class="host" x="{k1}" y="300" style="animation-delay:{out:.2f}s">{LOGIN}@github</text>'
            f'<text class="since" x="{v1}" y="300" style="animation-delay:{out:.2f}s">since {d["since"]}</text>'
            f'<line x1="{k1}" y1="314" x2="{k1 + 500}" y2="314" stroke="{c["key"]}" stroke-opacity=".35" '
            f'style="opacity:0;animation:fade .4s ease-out {out:.2f}s forwards"/>')

    langs = " · ".join(name for name, _ in d["languages"]) or "—"
    top = d["top_repos"][0] if d["top_repos"] else ("—", {"stars": 0})
    lang_row = (f'<text class="key" x="{k1}" y="350" style="animation-delay:{out + .1:.2f}s">Languages</text>'
                f'<text class="val" x="{v1}" y="350" fill="{c["accent2"]}" '
                f'style="animation-delay:{out + .15:.2f}s">{esc(langs)}</text>')

    grid = [
        (k1, v1, "Repos · Followers", f'{d["repos"]} · {d["followers"]}', c["fg"]),
        (k2, v2, "PRs / Issues", f'{d["prs"]} / {d["issues"]}', c["fg"]),
        (k1, v1, "Contributions", f'{d["contributions"]:,} / year', c["fg"]),
        (k2, v2, "Active days", f'{d["active_days"]} · streak {d["streak"]}d', c["fg"]),
        (k1, v1, "Commits", f'{d["commits"]:,}', c["fg"]),
        (k2, v2, "Top repo", f'{top[0].split("/")[-1]}  ★{top[1]["stars"]}', c["warn"]),
    ]
    rows = []
    for i, (kx, vx, key, val, col) in enumerate(grid):
        gy = 386 + (i // 2) * 34
        delay = out + 0.28 + i * 0.12
        rows.append(f'<text class="key" x="{kx}" y="{gy}" style="animation-delay:{delay:.2f}s">{key}</text>')
        rows.append(f'<text class="val" x="{vx}" y="{gy}" fill="{col}" '
                    f'style="animation-delay:{delay + 0.05:.2f}s">{esc(val)}</text>')

    weeks = d["weeks"]
    cell, gap = 13, 3
    step = cell + gap
    hx, hy = X0, 490
    top_count = max((n for w in weeks for _, n in w), default=1)
    heat = []
    for col, week in enumerate(weeks):
        for row, (_, n) in enumerate(week):
            heat.append(f'<rect class="pop" x="{hx + col * step}" y="{hy + row * step}" '
                        f'width="{cell}" height="{cell}" rx="2.5" fill="{c["heat"][level(n, top_count)]}" '
                        f'style="animation-delay:{out + 0.8 + col * 0.012:.2f}s"/>')
    months, seen = [], set()
    for col, week in enumerate(weeks):
        first = dt.date.fromisoformat(week[0][0])
        if first.month not in seen and first.day <= 14:
            seen.add(first.month)
            months.append(f'<text class="mo" x="{hx + col * step}" y="{hy - 10}" '
                          f'style="animation-delay:{out + .6:.2f}s">{first.strftime("%b")}</text>')

    legend_x = hx + len(weeks) * step + 28
    legend = f'<text class="lg" x="{legend_x}" y="{hy + 28}" style="animation-delay:{out + 1:.2f}s">Less</text>'
    legend += "".join(
        f'<rect class="pop" x="{legend_x + 34 + i * (cell + 3)}" y="{hy + 16}" width="{cell}" '
        f'height="{cell}" rx="2.5" fill="{col}" style="animation-delay:{out + 1 + i * 0.06:.2f}s"/>'
        for i, col in enumerate(c["heat"]))
    legend += (f'<text class="lg" x="{legend_x + 34 + 5 * (cell + 3) + 2}" y="{hy + 28}" '
               f'style="animation-delay:{out + 1:.2f}s">More</text>')

    cap_y = hy + 7 * step + 26
    cap = (f'<text class="cap" x="{hx}" y="{cap_y}" style="animation-delay:{out + 1.4:.2f}s">'
           f'{d["contributions"]:,} contributions in the last year · {len(weeks)} weeks</text>')
    footer = (f'<text class="ft" x="{X0}" y="{H - 24}" style="animation-delay:{out + 1.5:.2f}s">'
              f'{LOGIN}.github.io</text>'
              f'<text class="ft" x="{W - X0}" y="{H - 24}" text-anchor="end" '
              f'style="animation-delay:{out + 1.5:.2f}s">rendered {today:%Y-%m-%d} · {sha}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{LOGIN} — terminal dashboard</title>
<style>
text{{font-family:{MONO}}}
.i1{{font-size:24px;font-weight:700;fill:{c["fg"]};opacity:0;animation:rise .5s ease-out both}}
.i2{{font-size:17px;fill:{c["fg"]};opacity:0;animation:rise .5s ease-out both}}
.i3{{font-size:16px;fill:{c["muted"]};opacity:0;animation:rise .5s ease-out both}}
.pr{{font-size:16px;fill:{c["muted"]};opacity:0;animation:fade .01s linear forwards}}
.kc{{font-size:16px;fill:{c["fg"]};text-anchor:middle;opacity:0;animation:fade .01s linear forwards}}
.blink{{opacity:0;animation:blink 1.05s steps(1) infinite}}
.host{{font-size:19px;font-weight:700;fill:{c["accent"]};opacity:0;animation:rise .45s ease-out both}}
.since{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .4s ease-out both}}
.key{{font-size:15px;font-weight:700;fill:{c["key"]};opacity:0;animation:rise .4s ease-out both}}
.val{{font-size:15px;opacity:0;animation:rise .4s ease-out both}}
.mo{{font-size:11px;fill:{c["muted"]};text-anchor:middle;opacity:0;animation:fade .5s ease-out both}}
.lg{{font-size:12px;fill:{c["muted"]};opacity:0;animation:fade .5s ease-out both}}
.cap{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .5s ease-out both}}
.ft{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .5s ease-out both}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.5,.5,1) both}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@keyframes pop{{from{{transform:scale(0)}}to{{transform:scale(1)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.i1,.i2,.i3,.pr,.kc,.blink,.host,.since,.key,.val,.mo,.lg,.cap,.ft,.pop{{opacity:1}}}}
</style>
{"".join(intro)}
{"".join(session)}
{head}
{lang_row}
{"".join(rows)}
{"".join(heat)}
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
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"terminal-{theme}.svg").write_text(
            render(theme, d, sha, today), encoding="utf-8")
    langs = ", ".join(f"{n}({v})" for n, v in d["languages"])
    print(f"contributions={d['contributions']} repos={d['repos']} langs={langs}")


if __name__ == "__main__":
    main()
