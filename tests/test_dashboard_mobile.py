"""The phone plate: legible at 308 px, stacked, and wired into the README."""

import datetime as dt
import re
import unittest
import xml.etree.ElementTree as ET

from test_dashboard_motion import dashboard

NS = {"s": dashboard.SVG_NS}
TODAY = dt.date(2026, 10, 20)


def badges():
    """The full fetched set, shaped like load_badges() returns them."""
    widths = [65, 68, 75, 72, 64, 70, 72, 64, 100, 97, 86, 60, 48, 80, 80, 80, 74, 80, 74]
    chip = lambda w: ("img", "data:image/svg+xml;base64,PHN2Zy8+", float(w), 20.0, "3776AB")
    return [chip(w) for w in widths[:5]], [chip(w) for w in widths[5:11]], [chip(w) for w in widths[11:]]


def data():
    return dict(
        top_starred=[("tingfeng347/zst_agent", {"stars": 26})], since="2023",
        followers=15,
        languages=[("Python", 646), ("TypeScript", 144), ("HTML", 130),
                   ("Shell", 64), ("Ruby", 14)],
        contributions=1771, commits=1246, repos=98, prs=53, stars=78,
        weeks=[[("2026-10-18", 0)]] * 53, active_days=133,
    )


class PhonePlateTests(unittest.TestCase):
    def test_plate_is_a_portrait_column_not_a_scaled_desktop(self):
        for theme in dashboard.THEMES:
            with self.subTest(theme=theme):
                root = ET.fromstring(
                    dashboard.render_mobile(theme, data(), "test", TODAY, badges()))
                width, height = root.get("viewBox").split()[2:]
                self.assertEqual((width, root.get("width")), ("620", "620"))
                self.assertEqual((height, root.get("height")), (height, height))
                self.assertGreaterEqual(float(height), 900)
                # The 3D preview and the snake stay on the wide plate: below
                # half scale they are texture and they bury the numbers.
                self.assertFalse(root.findall(".//s:g[@class='contrib-preview']", NS))
                self.assertFalse(root.findall(".//s:g[@class='snake-panel']", NS))

    def test_all_nineteen_badges_are_kept_and_wrap_inside_the_column(self):
        root = ET.fromstring(
            dashboard.render_mobile("light", data(), "test", TODAY, badges()))
        groups = root.findall(".//s:g[@class='badge']", NS)
        self.assertEqual(len(groups), 19)
        spans = []
        # The wrapping group carries the transform; the vignette carries width.
        for wrapper in root.iter(f"{{{dashboard.SVG_NS}}}g"):
            transform = wrapper.get("transform") or ""
            if not transform.startswith("translate("):
                continue
            badge = wrapper.find("s:g[@class='badge']", NS)
            if badge is None:
                continue
            x = float(transform[len("translate("):].split(",")[0])
            inner = list(badge)[0]
            w = float(inner.get("width"))
            self.assertGreaterEqual(x, dashboard.MX0 - 0.5)
            self.assertLessEqual(x + w, dashboard.MW - dashboard.MX0 + 0.5)
            spans.append((x, x + w))
        self.assertEqual(len(spans), 19)

    def test_every_size_survives_the_phone_render(self):
        for theme in dashboard.THEMES:
            root = ET.fromstring(
                dashboard.render_mobile(theme, data(), "test", TODAY, badges()))
            css = root.find("s:style", NS).text
            sizes = [float(v) for v in re.findall(r"font-size:([\d.]+)px", css)]
            self.assertTrue(sizes)
            # 620 units render at ~308 px, so 17 SVG px is ~8.4 CSS px: the
            # floor for the footer and legend, everything else stays above it.
            self.assertGreaterEqual(min(sizes), 17.0)
            self.assertIn("font-size:44px", css)

    def test_text_stays_inside_the_column(self):
        root = ET.fromstring(
            dashboard.render_mobile("light", data(), "test", TODAY, badges()))
        for node in root.findall(".//s:text", NS):
            x = float(node.get("x", 0))
            self.assertGreaterEqual(x, 0)
            length = node.get("textLength")
            if length and node.get("text-anchor") != "end":
                self.assertLessEqual(x + float(length), dashboard.MW - dashboard.MX0 + 1)

    def test_commands_and_intro_keep_their_copy(self):
        root = ET.fromstring(
            dashboard.render_mobile("dark", data(), "test", TODAY, badges()))
        text = "".join(root.itertext())
        for word in ("Hi There", "I'm tingfeng347", "Building Coding Agents",
                     "Knowledge Graphs", "vim agent.py", "neofetch",
                     "zst_agent", "contributions / year"):
            self.assertIn(word, text)
        # The prompt and command share one line on the phone plate.
        prompt = root.find(".//s:text[@class='pr']", NS)
        self.assertLessEqual(float(prompt.get("x")) + float(prompt.get("textLength")),
                             dashboard.MW - dashboard.MX0)

    def test_reduced_motion_leaves_nothing_hidden(self):
        css = ET.fromstring(
            dashboard.render_mobile("light", data(), "test", TODAY, badges())
        ).find("s:style", NS).text
        block = css.split("@media (prefers-reduced-motion:reduce)", 1)[1]
        # Every class that starts at opacity 0 must be restored, including the
        # rule and legend dots, which the wide plate forgets.
        for cls in (".pr", ".host", ".since", ".lg", ".num", ".nl", ".cap", ".ft",
                    ".i1", ".i2", ".i3", ".badge", ".mdot", ".mrule", ".blink"):
            self.assertIn(cls, block)
        self.assertIn(".cc,.mclip{transform:none!important}", block)

    def test_theme_variants_share_structure(self):
        light = ET.fromstring(
            dashboard.render_mobile("light", data(), "test", TODAY, badges()))
        dark = ET.fromstring(
            dashboard.render_mobile("dark", data(), "test", TODAY, badges()))
        for tree in (light, dark):
            for node in tree.iter():
                node.attrib.pop("fill", None)
                node.attrib.pop("stroke", None)
                node.attrib.pop("href", None)
                node.text = None
        self.assertEqual(ET.tostring(light), ET.tostring(dark))


class PhoneAssetWiringTests(unittest.TestCase):
    def test_readme_serves_the_phone_plate_below_the_breakpoint(self):
        readme = (dashboard.OUT.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn('media="(prefers-color-scheme: dark) and (max-width: 640px)"', readme)
        self.assertIn('media="(prefers-color-scheme: light) and (max-width: 640px)"', readme)
        self.assertLess(readme.index("terminal-dark-mobile.svg"),
                        readme.index('media="(prefers-color-scheme: dark)"'))
        for name in ("terminal-dark-mobile.svg", "terminal-light-mobile.svg"):
            path = dashboard.OUT / name
            self.assertTrue(path.exists(), f"{name} has not been rendered yet")
            root = ET.fromstring(path.read_text(encoding="utf-8"))
            _, _, width, height = root.get("viewBox").split()
            self.assertEqual(width, "620")
            self.assertGreaterEqual(float(height), 900)


if __name__ == "__main__":
    unittest.main()