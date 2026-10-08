#!/usr/bin/env python3
"""Render tingfeng347's profile as an animated, frameless terminal.

A centred intro banner sits above a short, self-typing coding session (ending on
`neofetch`). The neofetch output is deliberately sparse and punchy: a language
bar, five headline numbers, and a yearly contribution heatmap — all driven by
real GitHub data.

One self-contained SVG per colour scheme (no scripts, no external resources), so
it animates inside a README <img>.

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

W, H = 1160, 730
X0 = 40
ADV = 9.6  # monospace cell at 16px
MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"

THEMES = {
    "dark": dict(
        fg="#e6edf3", muted="#8b949e",
        accent="#3fb950", accent2="#58a6ff", warn="#d29922", key="#39c5cf",
        prompt_user="#3fb950", prompt_path="#58a6ff",
        heat=["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"],
    ),
    "light": dict(
        fg="#1f2328", muted="#656d76",
        accent="#1a7f37", accent2="#0969da", warn="#9a6700", key="#1b7c83",
        prompt_user="#1a7f37", prompt_path="#0969da",
        heat=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    ),
}

# vibrant, hue-separated language colours (the legend carries the names)
LANG_COLORS = ["#3b82f6", "#f97316", "#22c55e", "#eab308", "#a855f7", "#ec4899"]

INTRO = [
    ("Hi There 👋, I'm tingfeng347", 34, "i1"),
    ("🎯 Focused · Full-Stack & AI Agent Developer", 19, "i2"),
    ("Building Coding Agents · Open Source · Knowledge Graphs", 18, "i3"),
]
COMMANDS = [
    "vim agent.py",
    "python3 -m pytest -q",
    'git commit -am "feat: profile"',
    "neofetch",
]


# ── data ──────────────────────────────────────────────────────────────

def graphql(token, query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": LOGIN},
    )
    for attempt in range(3):
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
    mid = W / 2

    # 1) centred intro banner
    intro, iy = [], 50
    for idx, (text, size, cls) in enumerate(INTRO):
        intro.append(f'<text class="{cls}" x="{mid}" y="{iy}" text-anchor="middle" '
                     f'style="animation-delay:{0.1 + idx * 0.15:.2f}s">{esc(text)}</text>')
        iy += 40 if size > 24 else 30

    # 2) a short coding session types itself, ending on neofetch
    prompt = f"{LOGIN}@github ~ ❯ "
    session, t = [], 0.7
    for i, cmd in enumerate(COMMANDS):
        ly = 166 + i * 28
        session.append(f'<text class="pr" x="{X0}" y="{ly}" style="animation-delay:{t:.2f}s">{esc(prompt)}</text>')
        session.append(typed(cmd, X0 + len(prompt) * ADV, ly, "kc", t + 0.1, 0.01))
        t += 0.1 + len(cmd) * 0.01 + 0.12
    last_y = 166 + (len(COMMANDS) - 1) * 28
    caret_x = X0 + (len(prompt) + len(COMMANDS[-1])) * ADV + 3
    session.append(f'<rect class="blink" x="{caret_x:.1f}" y="{last_y - 13}" width="8" height="18" '
                   f'fill="{c["fg"]}" style="animation-delay:{t:.2f}s"/>')
    out = t + 0.2  # neofetch output begins

    # 3) neofetch header
    top = d["top_repos"][0] if d["top_repos"] else ("—", {"stars": 0})
    head = (
        f'<text class="host" x="{X0}" y="286" style="animation-delay:{out:.2f}s">{LOGIN}@github</text>'
        f'<text class="since" x="{X0 + 244}" y="286" style="animation-delay:{out + 0.05:.2f}s">since {d["since"]}</text>'
        f'<text class="since" x="{W - X0}" y="286" text-anchor="end" '
        f'style="animation-delay:{out + 0.05:.2f}s">top repo · {esc(top[0].split("/")[-1])} ★{top[1]["stars"]}</text>'
        f'<line x1="{X0}" y1="300" x2="{W - X0}" y2="300" stroke="{c["key"]}" stroke-opacity=".35" '
        f'style="opacity:0;animation:fade .4s ease-out {out:.2f}s forwards"/>'
    )

    # 4) stacked language bar + legend
    langs = d["languages"]
    total = sum(v for _, v in langs) or 1
    bar_x, bar_y, bar_w, bar_h = X0, 336, W - 2 * X0, 12
    bar, cursor_x = [], bar_x
    for i, (name, count) in enumerate(langs):
        seg = max(3.0, count / total * bar_w - 3)
        col = LANG_COLORS[i % len(LANG_COLORS)]
        delay = out + 0.2 + i * 0.09
        bar.append(
            f'<rect x="{cursor_x:.1f}" y="{bar_y}" width="{seg:.1f}" height="{bar_h}" rx="3" fill="{col}" '
            f'style="transform-box:fill-box;transform-origin:left;animation:grow .6s ease-out {delay:.2f}s both"/>'
        )
        cursor_x += seg + 3
    legend, lx = [], bar_x
    for i, (name, count) in enumerate(langs):
        col = LANG_COLORS[i % len(LANG_COLORS)]
        text = f"{name} {count / total * 100:.0f}%"
        delay = out + 0.3 + i * 0.09
        legend.append(
            f'<circle cx="{lx + 5:.1f}" cy="{bar_y + 44}" r="4.5" fill="{col}" '
            f'style="opacity:0;animation:fade .4s ease-out {delay:.2f}s forwards"/>'
            f'<text class="lg" x="{lx + 15:.1f}" y="{bar_y + 48}" '
            f'style="animation-delay:{delay:.2f}s">{esc(name)} '
            f'<tspan fill="{c["muted"]}">{count / total * 100:.0f}%</tspan></text>'
        )
        lx += 15 + len(text) * 7.6 + 26
    langs_svg = "".join(bar) + "".join(legend)

    # 5) five headline numbers
    stats = [
        (f'{d["contributions"]:,}', "contributions / year", c["accent"]),
        (f'{d["commits"]:,}', "commits", c["fg"]),
        (f'{d["repos"]}', "public repos", c["fg"]),
        (f'{d["prs"]}', "pull requests", c["fg"]),
        (f'{d["streak"]}d', "current streak", c["fg"]),
    ]
    num, lab = [], []
    for i, (value, label, col) in enumerate(stats):
        sx = X0 + i * (W - 2 * X0) / 5
        delay = out + 0.45 + i * 0.09
        num.append(f'<text class="num" x="{sx}" y="446" fill="{col}" '
                   f'style="animation-delay:{delay:.2f}s">{esc(value)}</text>')
        lab.append(f'<text class="nl" x="{sx}" y="470" style="animation-delay:{delay + 0.06:.2f}s">{esc(label)}</text>')

    # 6) yearly heatmap
    weeks = d["weeks"]
    cell, gap = 13, 3
    step = cell + gap
    hx, hy = X0, 516
    top_count = max((n for w in weeks for _, n in w), default=1)
    heat = []
    for col in range(len(weeks)):
        for row, (_, n) in enumerate(weeks[col]):
            heat.append(f'<rect class="pop" x="{hx + col * step}" y="{hy + row * step}" '
                        f'width="{cell}" height="{cell}" rx="2.5" fill="{c["heat"][level(n, top_count)]}" '
                        f'style="animation-delay:{out + 0.7 + col * 0.008:.2f}s"/>')
    months, seen = [], set()
    for col, week in enumerate(weeks):
        first = dt.date.fromisoformat(week[0][0])
        if first.month not in seen and first.day <= 14:
            seen.add(first.month)
            months.append(f'<text class="mo" x="{hx + col * step}" y="{hy - 8}" '
                          f'style="animation-delay:{out + 0.55:.2f}s">{first.strftime("%b")}</text>')

    legend_x = hx + len(weeks) * step + 28
    hleg = f'<text class="lg" x="{legend_x}" y="{hy + 26}" style="animation-delay:{out + 0.85:.2f}s">Less</text>'
    hleg += "".join(
        f'<rect class="pop" x="{legend_x + 34 + i * (cell + 3)}" y="{hy + 14}" width="{cell}" '
        f'height="{cell}" rx="2.5" fill="{col}" style="animation-delay:{out + 0.85 + i * 0.06:.2f}s"/>'
        for i, col in enumerate(c["heat"]))
    hleg += (f'<text class="lg" x="{legend_x + 34 + 5 * (cell + 3) + 2}" y="{hy + 26}" '
             f'style="animation-delay:{out + 0.85:.2f}s">More</text>')

    cap = (f'<text class="cap" x="{X0}" y="{hy + 7 * step + 30}" style="animation-delay:{out + 1.0:.2f}s">'
           f'{d["contributions"]:,} contributions in the last year · {len(weeks)} weeks · '
           f'{d["active_days"]} active days</text>')
    footer = (f'<text class="ft" x="{X0}" y="{H - 24}" style="animation-delay:{out + 1.05:.2f}s">'
              f'{LOGIN}.github.io</text>'
              f'<text class="ft" x="{W - X0}" y="{H - 24}" text-anchor="end" '
              f'style="animation-delay:{out + 1.05:.2f}s">rendered {today:%Y-%m-%d} · {sha}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{LOGIN} — terminal dashboard</title>
<style>
text{{font-family:{MONO}}}
.i1{{font-size:34px;font-weight:700;fill:{c["fg"]};opacity:0;animation:rise .55s ease-out both}}
.i2{{font-size:19px;fill:{c["fg"]};opacity:0;animation:rise .55s ease-out both}}
.i3{{font-size:18px;fill:{c["muted"]};opacity:0;animation:rise .55s ease-out both}}
.pr{{font-size:16px;fill:{c["muted"]};opacity:0;animation:fade .01s linear forwards}}
.kc{{font-size:16px;fill:{c["fg"]};text-anchor:middle;opacity:0;animation:fade .01s linear forwards}}
.blink{{opacity:0;animation:blink 1.05s steps(1) infinite}}
.host{{font-size:20px;font-weight:700;fill:{c["accent"]};opacity:0;animation:rise .45s ease-out both}}
.since{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .4s ease-out both}}
.lg{{font-size:13px;fill:{c["fg"]};opacity:0;animation:fade .5s ease-out both}}
.num{{font-size:30px;font-weight:700;letter-spacing:-.5px;opacity:0;animation:rise .5s ease-out both}}
.nl{{font-size:12px;fill:{c["muted"]};opacity:0;animation:fade .5s ease-out both}}
.mo{{font-size:11px;fill:{c["muted"]};text-anchor:middle;opacity:0;animation:fade .5s ease-out both}}
.cap{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .5s ease-out both}}
.ft{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .5s ease-out both}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.5,.5,1) both}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@keyframes pop{{from{{transform:scale(0)}}to{{transform:scale(1)}}}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.i1,.i2,.i3,.pr,.kc,.blink,.host,.since,.lg,.num,.nl,.mo,.cap,.ft,.pop{{opacity:1}}}}
</style>
{"".join(intro)}
{"".join(session)}
{head}
{langs_svg}
{"".join(num)}
{"".join(lab)}
{"".join(heat)}
{"".join(months)}
{hleg}
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
