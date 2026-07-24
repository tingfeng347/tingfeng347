from __future__ import annotations

import re
import sys
from pathlib import Path


SECTION_RE = re.compile(
    r"(?P<start><!--START_SECTION:waka-->)(?P<body>.*?)(?P<end><!--END_SECTION:waka-->)",
    re.DOTALL,
)
ACTIVITY_RE = re.compile(
    r"\b(?P<period>Morning|Daytime|Evening|Night)\s+"
    r"(?P<commits>\d+)\s+commits\b"
)
HEADING_RE = re.compile(
    r"^\*\*I'm (?:an Early|a Night|most active (?:in the Morning|during the Daytime|in the Evening|at Night))[^\n]*\*\*$",
    re.MULTILINE,
)

HEADINGS = {
    "Morning": "**I'm most active in the Morning 🌞**",
    "Daytime": "**I'm most active during the Daytime 🌆**",
    "Evening": "**I'm most active in the Evening 🌃**",
    "Night": "**I'm most active at Night 🌙**",
}


def fix_heading(readme: str) -> str:
    section_match = SECTION_RE.search(readme)
    if section_match is None:
        raise ValueError("WakaTime section markers were not found")

    body = section_match.group("body")
    activity = {
        match.group("period"): int(match.group("commits"))
        for match in ACTIVITY_RE.finditer(body)
    }
    missing = HEADINGS.keys() - activity.keys()
    if missing:
        raise ValueError(f"Missing commit periods: {', '.join(sorted(missing))}")

    dominant_period = max(HEADINGS, key=activity.__getitem__)
    updated_body, replacements = HEADING_RE.subn(HEADINGS[dominant_period], body, count=1)
    if replacements != 1:
        raise ValueError("Generated commit activity heading was not found")

    return (
        readme[: section_match.start("body")]
        + updated_body
        + readme[section_match.end("body") :]
    )


def main() -> int:
    readme_path = Path(sys.argv[1] if len(sys.argv) > 1 else "README.md")
    original = readme_path.read_text(encoding="utf-8")
    updated = fix_heading(original)

    if updated != original:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"Corrected the WakaTime activity heading in {readme_path}")
    else:
        print(f"The WakaTime activity heading in {readme_path} is already correct")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
