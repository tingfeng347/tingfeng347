#!/usr/bin/env python3
"""Render tingfeng347's profile as an animated, frameless terminal.

Layout, animated on load: a centred intro banner, the tech-stack badges, a short
self-typing coding session (ending on `neofetch`), then the neofetch output — a
language bar, five headline numbers and a yearly contribution heatmap — all
driven by real GitHub data.

Motion is choreographed on one timeline: the headline is static; subtitles and
commands share the
same per-character typing engine. Complete glyphs appear at each keystroke
(lightly jittered, with a beat after every space) while the caret glides
from cell to cell instead of snapping, handing over to the next prompt at the
exact moment that prompt appears. The language bar and heatmap each use a single
continuous clip reveal.
All motion uses CSS, so reduced-motion readers see the complete static plate.

One self-contained SVG per colour scheme. shields.io badges are fetched once and
inlined as data URIs (with a flat-chip fallback), so nothing external is needed
at render time and it animates inside a README <img>.

Usage: GITHUB_TOKEN=... python scripts/generate_dashboard.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "tingfeng347"
OUT = Path(__file__).resolve().parent.parent / "assets"

W, H = 1160, 800
X0 = 40
ADV = 9.6  # monospace cell at 16px
PLAYBACK_SPEED = 2.0  # double all typing and handover speeds together
TYPE_BASE = 0.045 / PLAYBACK_SPEED  # steady pace between keystrokes
TYPE_JITTER = 0.008 / PLAYBACK_SPEED  # small human variation
WORD_BEAT = 0.04 / PLAYBACK_SPEED  # a breath after every space
TYPE_LEAD = 0.16 / PLAYBACK_SPEED  # caret lead-in before the first keystroke
TYPE_TAIL = 0.30 / PLAYBACK_SPEED  # beat between commands
TYPE_HOLD = 0.08  # paint the last glyph before an embedded SVG's animation ends
TYPE_START = 0.26 / PLAYBACK_SPEED  # first subtitle keystroke
BADGE_FADE = 0.14 / PLAYBACK_SPEED
SUBTITLE_SIZE = 18
MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"

THEMES = {
    "dark": dict(
        fg="#e6edf3", muted="#8b949e",
        accent="#3fb950", accent2="#58a6ff", warn="#d29922", key="#39c5cf",
        stat_colors=["#3fb950", "#58a6ff", "#a371f7", "#f0883e", "#d29922"],
        heat=["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"],
    ),
    "light": dict(
        fg="#1f2328", muted="#656d76",
        accent="#1a7f37", accent2="#0969da", warn="#9a6700", key="#1b7c83",
        stat_colors=["#1a7f37", "#0969da", "#8250df", "#bc4c00", "#9a6700"],
        heat=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    ),
}

LANG_COLORS = ["#3b82f6", "#f97316", "#22c55e", "#eab308", "#a855f7", "#ec4899"]

INTRO = [
    ("Hi There 👋, I'm tingfeng347", 34, "i1"),
    ("🎯 Focused · Full-Stack & AI Agent Developer", SUBTITLE_SIZE, "i2"),
    ("Building Coding Agents · Open Source · Knowledge Graphs", SUBTITLE_SIZE, "i3"),
]

# tech-stack badges: (url_label, hex, logo, logoColor)
BADGE_ROWS = [
    [("Python", "3776AB", "python", "white"), ("Java", "F89820", "openjdk", "white"),
     ("TypeScript", "3178C6", "typescript", "white"), ("Node.js", "339933", "nodedotjs", "white"),
     ("Shell", "4EAA25", "gnubash", "white")],
    [("FastAPI", "009688", "fastapi", "white"), ("Vue.js", "4FC08D", "vuedotjs", "white"),
     ("React", "61DAFB", "react", "black"), ("LangGraph", "2C3E50", "langchain", "white"),
     ("LlamaIndex", "6A0DAD", "openai", "white"), ("PyTorch", "EE4C2C", "pytorch", "white")],
    [("vLLM", "000000", "nvidia", "white"), ("Git", "F05032", "git", "white"),
     ("Neo4j", "4581C3", "neo4j", "white"), ("MySQL", "4479A1", "mysql", "white"),
     ("Docker", "2496ED", "docker", "white"), ("Linux", "FCC624", "linux", "black"),
     ("VS_Code", "007ACC", "visualstudiocode", "white"), ("Agent", "6C5CE7", "robotframework", "white")],
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
  starRepos: repositories(privacy:PUBLIC, ownerAffiliations:OWNER, isFork:false, first:100){
    nodes{stargazerCount}}
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

    own = {k: v for k, v in repos.items() if k.lower().startswith(LOGIN.lower() + "/")}
    return dict(
        login=user["login"], since=user["createdAt"][:4],
        followers=user["followers"]["totalCount"],
        repos=user["repositories"]["totalCount"],
        stars=sum(n["stargazerCount"] for n in user["starRepos"]["nodes"]),
        commits=cc["totalCommitContributions"],
        issues=cc["totalIssueContributions"],
        prs=cc["totalPullRequestContributions"],
        weeks=weeks,
        contributions=sum(n for week in weeks for _, n in week),
        active_days=len(active),
        languages=sorted(languages.items(), key=lambda kv: -kv[1])[:5],
        top_starred=sorted((own or repos).items(),
                           key=lambda kv: (-kv[1]["stars"], -kv[1]["commits"]))[:1],
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


def fetch_badge(label, color, logo, logo_color):
    """Return (data_uri, width, height) for a shields.io flat-square badge, or None."""
    url = (f"https://img.shields.io/badge/{label}-{color}"
           f"?style=flat-square&logo={logo}&logoColor={logo_color}")
    req = urllib.request.Request(url, headers={"User-Agent": LOGIN})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                svg = resp.read()
            w = re.search(rb'width="([0-9.]+)"', svg)
            h = re.search(rb'height="([0-9.]+)"', svg)
            if not w:
                return None
            return ("data:image/svg+xml;base64," + base64.b64encode(svg).decode(),
                    float(w.group(1)), float(h.group(1)) if h else 20.0)
        except OSError:
            if attempt == 0:
                time.sleep(1)
    return None


def load_badges():
    rows = []
    for row in BADGE_ROWS:
        built = []
        for label, color, logo, logo_color in row:
            got = fetch_badge(label, color, logo, logo_color)
            if got:
                built.append(("img", got[0], got[1], got[2], color))
            else:  # flat-chip fallback: keep the shape if shields is unreachable
                text = label.replace("_", " ")
                built.append(("chip", text, 18 + len(text) * 7.4, 20.0, color))
        rows.append(built)
    return rows


# ── drawing helpers ───────────────────────────────────────────────────

def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wipe(cid, x, y, w, h, begin, dur):
    """Reveal a fixed-size clip with a transform; CSS can disable it accessibly."""
    return (f'<clipPath id="{cid}" clipPathUnits="userSpaceOnUse">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'style="transform-origin:{x:.1f}px {y:.1f}px;'
            f'animation:reveal {dur:.2f}s cubic-bezier(.25,1,.4,1) {begin:.2f}s both"/>'
            f'</clipPath>')


def keystroke_times(text, start, rng):
    """Build the terminal's lightly varied character landing times."""
    lands, at = [], start
    for k, ch in enumerate(text):
        if k:
            at += TYPE_BASE + rng.uniform(-TYPE_JITTER, TYPE_JITTER)
            if ch == " " or text[k - 1] == " ":
                at += WORD_BEAT
        lands.append(at)
    return lands


def typing_track(text, advances, start, key, rng):
    """Shared glyph landing times, stepped reveal and continuously moving caret.

    Advances are explicit so a wide emoji is revealed in one complete cell,
    just like an ASCII letter. All sections use the same PLAYBACK_SPEED,
    keystroke intervals and word pauses, regardless of their font size.
    """
    lands = keystroke_times(text, start, rng)
    dur = max(lands[-1] - start, TYPE_HOLD)
    span = TYPE_LEAD + dur
    clip_dur = dur + TYPE_HOLD
    width = sum(advances)
    glide = ['0%{transform:translateX(0)}',
             f'{TYPE_LEAD * 0.55 / span * 100:.4f}%{{transform:translateX(0)}}']
    reveal, edge = [], 0.0
    for advance, when in zip(advances, lands):
        edge += advance
        glide.append(f'{(TYPE_LEAD + when - start) / span * 100:.4f}%'
                     f'{{transform:translateX({edge:.3f}px)}}')
        reveal.append(f'{(when - start) / clip_dur * 100:.4f}%'
                      f'{{transform:scaleX({edge / width:.8f});'
                      f'animation-timing-function:steps(1,end)}}')
    # Paint full width inside the active interval, not just at its endpoint:
    # embedded SVG images can otherwise retain the penultimate stepped frame.
    reveal.append('100%{transform:scaleX(1)}')
    rules = [f'@keyframes caret{key}{{{"".join(glide)}}}',
             f'@keyframes clip{key}{{{"".join(reveal)}}}']
    return rules, dur, lands[-1], lands


def typing_session(c, start):
    """Bake one timeline per command so glyphs, clip and caret cannot drift.

    Every character gets its own landing time — lightly jittered, with a beat
    after each space — and all three moving parts are generated from that one
    list: the clip jump that reveals the glyph, the caret, and how long the
    caret lives. The caret interpolates between cell boundaries rather than
    snapping to them, so nothing on screen ever jumps a whole character, and
    each caret is retired at the instant the next prompt fades in, so two
    carets are never visible at once.
    """
    prompt = f"{LOGIN}@github ~ ❯ "
    prompt_w = len(prompt) * ADV
    cmd_x = X0 + prompt_w
    clips, session, rules = [], [], []
    rng = random.Random(20261018)  # identical timing across themes and renders
    t = start
    for i, cmd in enumerate(COMMANDS):
        ly = 252 + i * 26
        n = len(cmd)
        width = n * ADV
        p = t - TYPE_LEAD  # prompt and caret appear here, typing starts at t
        track_rules, dur, end, _ = typing_track(cmd, [ADV] * n, t, i, rng)
        rules.extend(track_rules)
        span = TYPE_LEAD + dur  # caret timeline: prompt → last glyph lands
        clip_dur = dur + TYPE_HOLD

        clips.append(
            f'<clipPath id="cc{i}" clipPathUnits="userSpaceOnUse">'
            f'<rect class="cc" x="{cmd_x:.1f}" y="{ly - 16}" width="{width:.1f}" height="24" '
            f'style="transform-origin:{cmd_x:.1f}px {ly - 16:.1f}px;'
            f'animation:clip{i} {clip_dur:.3f}s linear {t:.3f}s forwards"/></clipPath>')
        session.append(
            f'<text class="pr" x="{X0}" y="{ly}" xml:space="preserve" '
            f'textLength="{prompt_w:.1f}" lengthAdjust="spacingAndGlyphs" '
            f'style="animation-delay:{p:.3f}s">{esc(prompt)}</text>')
        session.append(
            f'<g clip-path="url(#cc{i})">'
            f'<text class="kc" x="{cmd_x:.1f}" y="{ly}" '
            f'textLength="{width:.1f}" lengthAdjust="spacingAndGlyphs">{esc(cmd)}</text></g>')
        # last caret hands over to the blinking one; earlier ones to the next prompt
        life = TYPE_LEAD + dur if i == len(COMMANDS) - 1 else dur + TYPE_TAIL
        session.append(
            f'<rect class="typing-caret" x="{cmd_x + 2:.1f}" y="{ly - 13}" width="2" height="17" '
            f'rx="1" fill="{c["fg"]}" style="animation:caret{i} {span:.3f}s linear {p:.3f}s forwards,'
            f'caret-presence {life:.3f}s linear {p:.3f}s forwards"/>')
        t = end + TYPE_TAIL

    typing_end = t - TYPE_TAIL
    last_y = 252 + (len(COMMANDS) - 1) * 26
    caret_x = cmd_x + len(COMMANDS[-1]) * ADV + 2
    session.append(
        f'<rect class="blink" x="{caret_x:.1f}" y="{last_y - 13}" width="2" height="17" rx="1" '
        f'fill="{c["fg"]}" style="animation-delay:{typing_end:.3f}s"/>')
    return clips, "".join(session), rules, typing_end + 0.16


def level(count, top):
    if count <= 0:
        return 0
    for lvl, cut in ((4, 0.55), (3, 0.3), (2, 0.12)):
        if count >= max(1, top * cut):
            return lvl
    return 1


# ── plate ─────────────────────────────────────────────────────────────

def render(theme, d, sha, today, badges):
    c = THEMES[theme]
    mid = W / 2
    defs = []

    # 1) Show the headline immediately; type subtitles with the command engine.
    intro, iy = [], 46
    intro_rules = []
    intro_rng = random.Random(20261018)
    t = TYPE_START
    for idx, (text, size, cls) in enumerate(INTRO):
        advances = [size * (1.25 if unicodedata.east_asian_width(ch) in "WF" else .6)
                    for ch in text]
        width = sum(advances)
        x = mid - width / 2
        # Match the terminal's prompt + single text run. The emoji is a fixed
        # prefix, not a double-width keystroke; only the prose is typed.
        if cls == "i2":
            prefix, text = text.split(" ", 1)
            prefix_width = sum(advances[:len(prefix) + 1])
            intro.append(f'<text class="subtitle-icon" x="{x:.3f}" y="{iy}" '
                         f'textLength="{prefix_width:.3f}" lengthAdjust="spacingAndGlyphs" '
                         f'xml:space="preserve" style="animation-delay:{t - TYPE_LEAD:.3f}s">'
                         f'{esc(prefix)} </text>')
            x += prefix_width
            advances = advances[len(prefix) + 1:]
            width = sum(advances)
            line = (f'<text class="{cls}" x="{x:.3f}" y="{iy}" '
                    f'textLength="{width:.3f}" lengthAdjust="spacingAndGlyphs">{esc(text)}</text>')
        else:
            # Preserve the existing static headline and accepted second line.
            glyphs, gx = [], x
            for ch, advance in zip(text, advances):
                glyphs.append(f'<tspan x="{gx:.3f}" textLength="{advance:.3f}" '
                              f'lengthAdjust="spacingAndGlyphs">{esc(ch)}</tspan>')
                gx += advance
            line = (f'<text class="{cls}" y="{iy}" xml:space="preserve">'
                    f'{"".join(glyphs)}</text>')
        if idx == 0:
            intro.append(line)
            iy += 40
            continue

        key = f'intro{idx}'
        track_rules, dur, end, _ = typing_track(text, advances, t, key, intro_rng)
        intro_rules.extend(track_rules)
        defs.append(f'<clipPath id="ic{idx}" clipPathUnits="userSpaceOnUse">'
                    f'<rect class="cc intro-clip" x="{x:.3f}" y="{iy - size}" '
                    f'width="{width:.3f}" height="{size * 1.5:.3f}" '
                    f'style="transform-origin:{x:.3f}px {iy - size}px;'
                    f'animation:clip{key} {dur + TYPE_HOLD:.3f}s linear {t:.3f}s forwards"/>'
                    f'</clipPath>')
        intro.append(f'<g clip-path="url(#ic{idx})">{line}</g>')
        intro.append(f'<rect class="typing-caret" x="{x + 2:.3f}" y="{iy - size * .8:.3f}" '
                     f'width="2" height="{size * 1.05:.3f}" rx="1" fill="{c["fg"]}" '
                     f'style="animation:caret{key} {TYPE_LEAD + dur:.3f}s linear '
                     f'{t - TYPE_LEAD:.3f}s forwards,caret-presence {dur + TYPE_TAIL:.3f}s '
                     f'linear {t - TYPE_LEAD:.3f}s forwards"/>')
        t = end + TYPE_TAIL
        iy += 40 if size > 24 else 28

    # 2) Compact reading-order cascade, matching the shared typing beat.
    badge_svg = []
    badge_idx = 0
    badge_start = t - TYPE_LEAD
    for r, row in enumerate(badges):
        total = sum(w for _, _, w, _, _ in row) + 8 * (len(row) - 1)
        x = (W - total) / 2
        row_svg = []
        for kind, payload, bw, bh, color in row:
            delay = badge_start + badge_idx * TYPE_BASE
            badge_idx += 1
            if kind == "img":
                inner = f'<image href="{payload}" width="{bw:.0f}" height="{bh:.0f}"/>'
            else:
                inner = (f'<rect width="{bw:.0f}" height="{bh:.0f}" rx="3" fill="#{color}"/>'
                         f'<text x="{bw / 2:.0f}" y="13.5" text-anchor="middle" font-size="11" '
                         f'font-family="{MONO}" fill="#fff">{esc(payload)}</text>')
            row_svg.append(f'<g transform="translate({x:.1f},{146 + r * 26})">'
                           f'<g class="badge" style="animation-delay:{delay:.3f}s">{inner}</g></g>')
            x += bw + 8
        badge_svg.append("".join(row_svg))

    # 3) per-character typing, one gliding caret on screen at a time
    command_start = badge_start + (badge_idx - 1) * TYPE_BASE + BADGE_FADE + TYPE_LEAD
    command_clips, session, caret_rules, out = typing_session(c, command_start)
    defs.extend(command_clips)

    # 4) neofetch header
    ranked = d["top_starred"] or [("—", {"stars": 0})]
    top = ranked[0]
    head = (
        f'<text class="host" x="{X0}" y="392" style="animation-delay:{out:.2f}s">{LOGIN}@github</text>'
        f'<text class="since" x="{X0 + 244}" y="392" style="animation-delay:{out + 0.05:.2f}s">since {d["since"]}</text>'
        f'<text class="since" x="{W - X0}" y="392" text-anchor="end" '
        f'style="animation-delay:{out + 0.05:.2f}s">top repo · {esc(top[0].split("/")[-1])} ★{top[1]["stars"]}</text>'
        f'<line x1="{X0}" y1="406" x2="{W - X0}" y2="406" stroke="{c["key"]}" stroke-opacity=".35" '
        f'style="opacity:0;animation:fade .4s ease-out {out:.2f}s forwards"/>'
    )

    # 5) stacked language bar (single wipe) + packed legend
    langs = d["languages"]
    total_lang = sum(v for _, v in langs) or 1
    bar_x, bar_y, bar_w, bar_h = X0, 440, W - 2 * X0, 12
    bar, cursor_x = [], bar_x
    for i, (name, count) in enumerate(langs):
        seg = max(3.0, count / total_lang * bar_w - 3)
        bar.append(f'<rect x="{cursor_x:.1f}" y="{bar_y}" width="{seg:.1f}" height="{bar_h}" '
                   f'rx="3" fill="{LANG_COLORS[i % len(LANG_COLORS)]}"/>')
        cursor_x += seg + 3
    defs.append(wipe("bar", bar_x, bar_y, bar_w, bar_h, out + 0.16, 0.62))
    legend, lx = [], bar_x
    for i, (name, count) in enumerate(langs):
        col = LANG_COLORS[i % len(LANG_COLORS)]
        text = f"{name} {count / total_lang * 100:.0f}%"
        delay = out + 0.35 + i * 0.09
        legend.append(
            f'<circle cx="{lx + 5:.1f}" cy="{bar_y + 44}" r="4.5" fill="{col}" '
            f'style="opacity:0;animation:fade .4s ease-out {delay:.2f}s forwards"/>'
            f'<text class="lg" x="{lx + 15:.1f}" y="{bar_y + 48}" '
            f'style="animation-delay:{delay:.2f}s">{esc(name)} '
            f'<tspan fill="{c["muted"]}">{count / total_lang * 100:.0f}%</tspan></text>'
        )
        lx += 15 + len(text) * 7.6 + 26
    langs_svg = f'<g clip-path="url(#bar)">{"".join(bar)}</g>' + "".join(legend)

    # 6) five headline numbers, each its own colour
    stats = [
        (f'{d["contributions"]:,}', "contributions / year"),
        (f'{d["commits"]:,}', "commits"),
        (f'{d["repos"]}', "public repos"),
        (f'{d["prs"]}', "pull requests"),
        (f'{d["stars"]:,}', "stars"),
    ]
    num, lab = [], []
    for i, (value, label) in enumerate(stats):
        sx = X0 + i * (W - 2 * X0) / 5
        delay = out + 0.42 + i * 0.08
        num.append(f'<text class="num" x="{sx}" y="540" fill="{c["stat_colors"][i % 5]}" '
                   f'style="animation-delay:{delay:.2f}s">{esc(value)}</text>')
        lab.append(f'<text class="nl" x="{sx}" y="564" style="animation-delay:{delay + 0.05:.2f}s">{esc(label)}</text>')

    # 7) yearly heatmap, revealed by a single left→right wipe
    weeks = d["weeks"]
    cell, gap = 13, 3
    step = cell + gap
    hx, hy = X0, 604
    top_count = max((n for w in weeks for _, n in w), default=1)
    heat = []
    for col in range(len(weeks)):
        for row, (_, n) in enumerate(weeks[col]):
            heat.append(f'<rect x="{hx + col * step}" y="{hy + row * step}" width="{cell}" '
                        f'height="{cell}" rx="2.5" fill="{c["heat"][level(n, top_count)]}"/>')
    defs.append(wipe("heat", hx, hy - 1, len(weeks) * step + 1, 7 * step + 2, out + 0.5, 0.66))
    months, seen = [], set()
    for col, week in enumerate(weeks):
        first = dt.date.fromisoformat(week[0][0])
        if first.month not in seen and first.day <= 14:
            seen.add(first.month)
            months.append(f'<text class="mo" x="{hx + col * step}" y="{hy - 8}" '
                          f'style="animation-delay:{out + 0.6:.2f}s">{first.strftime("%b")}</text>')

    legend_x = hx + len(weeks) * step + 28
    hleg = f'<text class="lg" x="{legend_x}" y="{hy + 26}" style="animation-delay:{out + 1.0:.2f}s">Less</text>'
    hleg += "".join(
        f'<rect x="{legend_x + 34 + i * (cell + 3)}" y="{hy + 14}" width="{cell}" height="{cell}" '
        f'rx="2.5" fill="{col}" style="opacity:0;animation:fade .4s ease-out {out + 1.0 + i * 0.06:.2f}s forwards"/>'
        for i, col in enumerate(c["heat"]))
    hleg += (f'<text class="lg" x="{legend_x + 34 + 5 * (cell + 3) + 2}" y="{hy + 26}" '
             f'style="animation-delay:{out + 1.0:.2f}s">More</text>')

    cap = (f'<text class="cap" x="{X0}" y="{hy + 7 * step + 30}" style="animation-delay:{out + 1.05:.2f}s">'
           f'{d["contributions"]:,} contributions in the last year · {len(weeks)} weeks · '
           f'{d["active_days"]} active days</text>')
    footer = (f'<text class="ft" x="{X0}" y="{H - 24}" style="animation-delay:{out + 1.1:.2f}s">'
              f'{LOGIN}.github.io</text>'
              f'<text class="ft" x="{W - X0}" y="{H - 24}" text-anchor="end" '
              f'style="animation-delay:{out + 1.1:.2f}s">rendered {today:%Y-%m-%d} · {sha}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{LOGIN} — terminal dashboard</title>
<style>
text{{font-family:{MONO}}}
.i1{{font-size:34px;font-weight:700;fill:{c["fg"]}}}
.i2,.i3{{font-size:{SUBTITLE_SIZE}px}}
.i2{{fill:{c["fg"]}}}
.i3{{fill:{c["muted"]}}}
.subtitle-icon{{font-size:{SUBTITLE_SIZE}px;fill:{c["fg"]};opacity:0;animation:fade .2s cubic-bezier(.22,1,.36,1) both}}
.badge{{animation:badge-in {BADGE_FADE:.3f}s cubic-bezier(.22,1,.36,1) both}}
.pr{{font-size:16px;fill:{c["muted"]};opacity:0;animation:fade .2s cubic-bezier(.22,1,.36,1) both}}
.pr,.kc,.i1,.i2,.i3{{font-kerning:none;font-variant-ligatures:none}}
.kc{{font-size:16px;fill:{c["fg"]}}}
.cc{{transform:scaleX(0)}}
.typing-caret{{opacity:0}}
.blink{{opacity:0;animation:blink 1.1s steps(1,end) infinite}}
.host{{font-size:20px;font-weight:700;fill:{c["accent"]};opacity:0;animation:rise .55s cubic-bezier(.16,1,.3,1) both}}
.since{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .5s cubic-bezier(.22,1,.36,1) both}}
.lg{{font-size:13px;fill:{c["fg"]};opacity:0;animation:fade .5s cubic-bezier(.22,1,.36,1) both}}
.num{{font-size:30px;font-weight:700;letter-spacing:-.5px;opacity:0;animation:rise .6s cubic-bezier(.16,1,.3,1) both}}
.nl{{font-size:12px;fill:{c["muted"]};opacity:0;animation:fade .5s cubic-bezier(.22,1,.36,1) both}}
.mo{{font-size:11px;fill:{c["muted"]};text-anchor:middle;opacity:0;animation:fade .55s cubic-bezier(.22,1,.36,1) both}}
.cap{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .55s cubic-bezier(.22,1,.36,1) both}}
.ft{{font-size:13px;fill:{c["muted"]};opacity:0;animation:fade .55s cubic-bezier(.22,1,.36,1) both}}
{"\n".join(caret_rules)}
{"\n".join(intro_rules)}
@keyframes badge-in{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes reveal{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes caret-presence{{0%{{opacity:0}}3%{{opacity:1}}99.5%{{opacity:1}}100%{{opacity:0}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}
.pr,.blink,.host,.since,.lg,.num,.nl,.mo,.cap,.ft,.i1,.i2,.i3,.subtitle-icon,.badge{{opacity:1}}
.cc,.intro-clip{{transform:none!important}}.typing-caret{{display:none}}}}
</style>
<defs>{"".join(defs)}</defs>
{"".join(intro)}
{"".join(badge_svg)}
{session}
{head}
{langs_svg}
{"".join(num)}
{"".join(lab)}
<g clip-path="url(#heat)">{"".join(heat)}</g>
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
    badges = load_badges()
    n_img = sum(1 for row in badges for b in row if b[0] == "img")
    today = dt.date.fromisoformat(d["weeks"][-1][-1][0])
    sha = head_hash()
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"terminal-{theme}.svg").write_text(
            render(theme, d, sha, today, badges), encoding="utf-8")
    print(f"contributions={d['contributions']} repos={d['repos']} stars={d['stars']} "
          f"badges={n_img}/{sum(len(r) for r in badges)}")


if __name__ == "__main__":
    main()
