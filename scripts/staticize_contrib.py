#!/usr/bin/env python3
"""Keep the generated rainbow contribution asset colourful and lightweight.

The upstream generator gives every cell an infinite CSS colour animation. That
looks lively in a browser but makes profile README renderers repaint hundreds
of SVG layers forever. A static palette keeps the reference look and is safe
for GitHub's SVG rasterizer.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


STATIC_RAINBOW_FILLS = {
    "rb-l0-top": "#59632e", "rb-l0-left": "#4b5426", "rb-l0-right": "#3b431f",
    "rb-l1-top": "#8b4059", "rb-l1-left": "#75354c", "rb-l1-right": "#5d2c3d",
    "rb-l2-top": "#4b5c9f", "rb-l2-left": "#40508e", "rb-l2-right": "#334073",
    "rb-l3-top": "#3e9b9b", "rb-l3-left": "#358585", "rb-l3-right": "#2c6d6d",
    "rb-l4-top": "#58b957", "rb-l4-left": "#4a9f4b", "rb-l4-right": "#3b803f",
}


def staticize(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    updated = source
    for cls, color in STATIC_RAINBOW_FILLS.items():
        updated, count = re.subn(
            rf"\.{re.escape(cls)}\{{animation:{re.escape(cls)} 10s linear infinite;\}}",
            f".{cls}{{fill:{color};}}",
            updated,
        )
        if count > 1:
            raise ValueError(f"{cls}: expected at most one rule, got {count}")

    spans = []
    cursor = 0
    while True:
        match = re.search(r"@keyframes\s+rb-[\w-]+\s*\{", updated[cursor:])
        if not match:
            break
        start = cursor + match.start()
        opening = cursor + match.end() - 1
        depth, end = 1, opening + 1
        while end < len(updated) and depth:
            if updated[end] == "{":
                depth += 1
            elif updated[end] == "}":
                depth -= 1
            end += 1
        if depth:
            raise ValueError("Unclosed rainbow keyframe block")
        spans.append((start, end))
        cursor = end
    for start, end in reversed(spans):
        updated = updated[:start] + updated[end:]

    if updated != source:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "profile-3d-contrib/profile-night-rainbow.svg"
    )
    print(f"staticized {target}" if staticize(target) else f"already static: {target}")
