"""Regression checks for pauses in the actual generated typing animations."""

import datetime as dt
import importlib.util
from pathlib import Path
import re
import statistics
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
    def test_large_heading_moves_at_the_subtitles_visual_speed(self):
        ns = {"s": dashboard.SVG_NS}
        for theme in dashboard.THEMES:
            root = ET.parse(dashboard.OUT / f"terminal-{theme}.svg").getroot()
            css = root.find("s:style", ns).text
            speeds = []
            for index in range(3):
                clip = root.find(f'.//s:clipPath[@id="ic{index}"]/s:rect', ns)
                glyphs = list(root.find(f'.//s:text[@class="i{index + 1}"]', ns))
                duration = float(re.search(r"animation:\w+ ([\d.]+)s", clip.get("style"))[1])
                rule = next(line for line in css.splitlines()
                            if line.startswith(f"@keyframes clipintro{index}{{"))
                times = [float(t) / 100 * duration for t in re.findall(r"([\d.]+)%\{", rule)]
                speeds.append(statistics.median(
                    float(glyphs[k].get("textLength")) / (times[k] - times[k - 1])
                    for k in range(1, len(glyphs))
                    if glyphs[k].text.isascii() and not any(
                        g.text.isspace() for g in glyphs[k - 1:k + 1])))
            self.assertAlmostEqual(speeds[0] / speeds[2], 1, delta=.2)
            self.assertAlmostEqual(speeds[1] / speeds[2], 1, delta=.2)

    def test_headline_hands_over_without_a_stationary_tail(self):
        ns = {"s": dashboard.SVG_NS}
        data = dict(top_starred=[], since="2023", languages=[], contributions=0,
                    commits=0, repos=0, prs=0, stars=0, weeks=[], active_days=0)
        for theme in dashboard.THEMES:
            root = ET.fromstring(dashboard.render(theme, data, "test", dt.date(2026, 10, 18), []))
            css = root.find("s:style", ns).text
            first = root.find('.//s:clipPath[@id="ic0"]/s:rect', ns)
            second = root.find('.//s:clipPath[@id="ic1"]/s:rect', ns)
            duration, start = map(float, re.search(r"animation:\w+ ([\d.]+)s linear ([\d.]+)s", first.get("style")).groups())
            rule = next(line for line in css.splitlines() if line.startswith("@keyframes clipintro0{"))
            finish = float(re.search(r"([\d.]+)%\{transform:scaleX\(1(?:\.0+)?\)", rule)[1]) / 100
            next_start = float(re.search(r"linear ([\d.]+)s", second.get("style"))[1])
            self.assertAlmostEqual(next_start, start + duration * finish, delta=.001)

    def test_intro_reveals_complete_glyphs_and_caret_stays_aligned(self):
        data = dict(top_starred=[], since="2023", languages=[], contributions=0,
                    commits=0, repos=0, prs=0, stars=0, weeks=[], active_days=0)
        ns = {"s": dashboard.SVG_NS}
        for theme in dashboard.THEMES:
            sources = [dashboard.render(theme, data, "test", dt.date(2026, 10, 18), []),
                       (dashboard.OUT / f"terminal-{theme}.svg").read_text()]
            for source in sources:
                root = ET.fromstring(source)
                css = root.find("s:style", ns).text
                for index in range(3):
                    with self.subTest(theme=theme, line=index):
                        clip = root.find(f'.//s:clipPath[@id="ic{index}"]/s:rect', ns)
                        text = root.find(f'.//s:text[@class="i{index + 1}"]', ns)
                        clip_rule = next(line for line in css.splitlines()
                                         if line.startswith(f"@keyframes clipintro{index}{{"))
                        caret_rule = next(line for line in css.splitlines()
                                          if line.startswith(f"@keyframes caretintro{index}{{"))
                        edges, edge = [], 0
                        for glyph in text:
                            edge += float(glyph.get("textLength"))
                            edges.append(edge)
                        frames = re.findall(r"([\d.]+)%\{transform:scaleX\(([\d.]+)\)([^}]*)", clip_rule)
                        self.assertEqual(len(frames), len(edges) + 1)
                        for (_, scale, timing), expected in zip(frames, edges):
                            self.assertIn("steps(1,end)", timing)
                            self.assertAlmostEqual(float(scale) * edge, expected, places=4)
                        duration = float(re.search(r"animation:\w+ ([\d.]+)s", clip.get("style"))[1])
                        finish = float(frames[-2][0]) / 100
                        self.assertAlmostEqual(duration * (1 - finish), dashboard.TYPE_HOLD, delta=.001)
                        caret_edges = re.findall(r"translateX\(([\d.]+)px\)", caret_rule)
                        self.assertEqual(len(caret_edges), len(edges))
                        for actual, expected in zip(caret_edges, edges):
                            self.assertAlmostEqual(float(actual), expected, places=3)

    def test_rendered_words_do_not_inherit_another_sentences_pauses(self):
        data = dict(top_starred=[], since="2023", languages=[], contributions=0,
                    commits=0, repos=0, prs=0, stars=0, weeks=[], active_days=0)
        ns = {"s": "http://www.w3.org/2000/svg"}
        for theme in dashboard.THEMES:
            svg = dashboard.render(theme, data, "test", dt.date(2026, 10, 18), [])
            root = ET.fromstring(svg)
            css = root.find("s:style", ns).text
            for text_class, clip_id in (("i1", "ic0"), ("i2", "ic1"), ("i3", "ic2"), ("kc", "cc0")):
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
                        if " " in text[k - 1:k + 1]:
                            continue
                        gap = (offsets[k] - offsets[k - 1]) * duration
                        # Allow serialized-duration rounding, but not a word beat.
                        self.assertLessEqual(
                            gap, (dashboard.TYPE_BASE + dashboard.TYPE_JITTER) *
                            (34 / dashboard.SUBTITLE_SIZE if text_class == "i1" else 1) + .001,
                            f"Unexpected pause inside {text[max(0, k - 4):k + 4]!r}: {gap:.4f}s",
                        )


if __name__ == "__main__":
    unittest.main()
