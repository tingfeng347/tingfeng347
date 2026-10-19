"""Regression checks for pauses in the actual generated typing animations."""

import datetime as dt
import importlib.util
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


generator = Path(__file__).resolve().parents[1] / "scripts" / "generate_dashboard.py"
spec = importlib.util.spec_from_file_location("dashboard", generator)
dashboard = importlib.util.module_from_spec(spec)
with patch.object(sys, "argv", [str(generator)]):
    spec.loader.exec_module(dashboard)


class TypingMotionTests(unittest.TestCase):
    def test_opening_sweeps_without_steps_and_caret_stays_aligned(self):
        data = dict(top_starred=[], since="2023", languages=[], contributions=0,
                    commits=0, repos=0, prs=0, stars=0, weeks=[], active_days=0)
        ns = {"s": dashboard.SVG_NS}
        for theme in dashboard.THEMES:
            sources = [dashboard.render(theme, data, "test", dt.date(2026, 10, 18), []),
                       (dashboard.OUT / f"terminal-{theme}.svg").read_text()]
            for source in sources:
                root = ET.fromstring(source)
                css = root.find("s:style", ns).text
                for index in (0, 1):
                    with self.subTest(theme=theme, line=index):
                        clip = root.find(f'.//s:clipPath[@id="ic{index}"]/s:rect', ns)
                        clip_rule = next(line for line in css.splitlines()
                                         if line.startswith(f"@keyframes clipintro{index}{{"))
                        caret_rule = next(line for line in css.splitlines()
                                          if line.startswith(f"@keyframes caretintro{index}{{"))
                        self.assertNotIn("steps(", clip_rule)
                        self.assertIn("0%{transform:scaleX(0)}", clip_rule)
                        self.assertIn("s linear ", clip.get("style"))
                        # The full-width frame must paint before animation end.
                        finish = float(re.search(r"([\d.]+)%\{transform:scaleX\(1\)", clip_rule)[1]) / 100
                        duration = float(re.search(r"animation:\w+ ([\d.]+)s", clip.get("style"))[1])
                        typing_duration = finish * duration
                        self.assertAlmostEqual(duration - typing_duration, dashboard.TYPE_HOLD, delta=.001)
                        # The caret covers exactly the clip width in the same interval.
                        caret_width = float(re.search(r"100%\{transform:translateX\(([\d.]+)px", caret_rule)[1])
                        self.assertAlmostEqual(caret_width, float(clip.get("width")), places=3)
                        caret_span = dashboard.TYPE_LEAD + typing_duration
                        lead = float(re.search(r"([\d.]+)%\{transform:translateX\(0\)\}100%", caret_rule)[1]) / 100
                        self.assertAlmostEqual(lead * caret_span, dashboard.TYPE_LEAD, delta=.001)

    def test_rendered_words_do_not_inherit_another_sentences_pauses(self):
        data = dict(top_starred=[], since="2023", languages=[], contributions=0,
                    commits=0, repos=0, prs=0, stars=0, weeks=[], active_days=0)
        ns = {"s": "http://www.w3.org/2000/svg"}
        for theme in dashboard.THEMES:
            svg = dashboard.render(theme, data, "test", dt.date(2026, 10, 18), [])
            root = ET.fromstring(svg)
            css = root.find("s:style", ns).text
            for text_class, clip_id in (("i3", "ic2"), ("kc", "cc0")):
                with self.subTest(theme=theme, line=text_class):
                    text = "".join(root.find(f'.//s:text[@class="{text_class}"]', ns).itertext())
                    clip = root.find(f'.//s:clipPath[@id="{clip_id}"]/s:rect', ns)
                    animation = re.search(r"animation:(\w+) ([\d.]+)s", clip.get("style"))
                    name, duration = animation[1], float(animation[2])
                    rule = next(line for line in css.splitlines()
                                if line.startswith(f"@keyframes {name}" + "{"))
                    offsets = [float(n) / 100 for n in re.findall(r"([\d.]+)%\{", rule)]
                    self.assertGreaterEqual(len(offsets), len(text))
                    for k in range(1, len(text)):
                        if text_class != "i1" and " " in text[k - 1:k + 1]:
                            continue
                        gap = (offsets[k] - offsets[k - 1]) * duration
                        # Allow serialized-duration rounding, but not a word beat.
                        self.assertLessEqual(
                            gap, dashboard.TYPE_BASE + dashboard.TYPE_JITTER + .001,
                            f"Unexpected pause inside {text[max(0, k - 4):k + 4]!r}: {gap:.4f}s",
                        )


if __name__ == "__main__":
    unittest.main()
