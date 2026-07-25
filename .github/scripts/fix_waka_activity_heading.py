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
BOLD_HEADING_RE = re.compile(r"^[ \t]*\*\*[^\r\n]+\*\*[ \t]*$", re.MULTILINE)

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
    commit_block_start = body.find("```text")
    if commit_block_start == -1:
        raise ValueError("Generated commit activity block was not found")

    heading_matches = list(BOLD_HEADING_RE.finditer(body, 0, commit_block_start))
    if len(heading_matches) != 1:
        raise ValueError("Generated commit activity heading was not found")

    heading_match = heading_matches[0]
    updated_body = (
        body[: heading_match.start()]
        + HEADINGS[dominant_period]
        + body[heading_match.end() :]
    )

    updated_body = "\n".join(line.rstrip() for line in updated_body.split("\n"))

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
