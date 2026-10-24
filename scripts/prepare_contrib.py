#!/usr/bin/env python3
"""Set the generated rainbow chart to its entrance frame without changing its style."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def prepare(path: Path) -> None:
    root = ET.parse(path).getroot()
    changed = 0
    for parent in root.iter():
        for node in list(parent):
            if node.tag not in (f"{{{SVG_NS}}}animate", f"{{{SVG_NS}}}animateTransform"):
                continue
            initial = node.get("values", "").split(";")[0]
            if node.get("type"):
                initial = f'{node.get("type")}({initial})'
            parent.set(node.get("attributeName"), initial)
            changed += 1
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=False)
    print(f"prepared {path}: {changed} entrance attributes")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]) if len(sys.argv) > 1 else
            Path("profile-3d-contrib/profile-night-rainbow.svg"))
