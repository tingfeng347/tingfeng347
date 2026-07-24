#!/usr/bin/env python3
import re
import sys
from pathlib import Path


START_MARKER = "<!--START_SECTION:waka-->"
END_MARKER = "<!--END_SECTION:waka-->"
BAR_PATTERN = re.compile(
    r"^(?P<prefix>.*?)(?P<bar>[█░⣿⣀⬛⬜]{25})[ \t]+"
    r"(?P<percent>\d{2}\.\d{2})[ \t]+%[ \t]*$",
    re.MULTILINE,
)
DAYTIME_ICONS = ("🌞 ", "🌆 ", "🌃 ", "🌙 ")
BAR_LENGTH = 15


def compact_line(match: re.Match[str]) -> str:
    prefix = match.group("prefix")
    name = prefix[:25].rstrip()
    detail = prefix[25:45].strip()

    for icon in DAYTIME_ICONS:
        if name.startswith(icon):
            name = name.removeprefix(icon)
            break

    percent = float(match.group("percent"))
    filled = round(percent * BAR_LENGTH / 100)
    bar = "█" * filled + "░" * (BAR_LENGTH - filled)
    return f"{name[:18]:<18}{detail[:16]:<16}{bar}  {percent:05.2f} %"


def compact_waka_stats(readme: str) -> str:
    start = readme.find(START_MARKER)
    end = readme.find(END_MARKER, start)
    if start == -1 or end == -1:
        return readme

    section = readme[start:end]
    compact_section = BAR_PATTERN.sub(compact_line, section)
    return readme[:start] + compact_section + readme[end:]


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--write":
        path = Path(sys.argv[2])
        original = path.read_text(encoding="utf-8")
        path.write_text(compact_waka_stats(original), encoding="utf-8", newline="")
        return

    original = sys.stdin.read()
    sys.stdout.write(compact_waka_stats(original))


if __name__ == "__main__":
    main()
