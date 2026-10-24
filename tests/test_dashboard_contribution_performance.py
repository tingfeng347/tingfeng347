"""Keep rainbow motion shared without changing any face's color or phase."""

from collections import Counter
import re
import unittest
import xml.etree.ElementTree as ET

from test_dashboard_motion import dashboard


class ContributionPaintTests(unittest.TestCase):
    def test_rainbow_faces_share_identical_color_tracks(self):
        ns = {"s": dashboard.SVG_NS}
        source = ET.parse(dashboard.OUT.parent / "profile-3d-contrib" /
                          "profile-night-rainbow.svg").getroot()
        root = ET.fromstring(f'<svg xmlns="{dashboard.SVG_NS}">'
                            f'{dashboard.contribution_preview("dark", 4.5, "profile-night-rainbow.svg")}'
                            '</svg>')
        original = [n for n in source.iter() if n.get("class", "").startswith("rb-")]
        stops = root.findall(".//s:linearGradient/s:stop", ns)
        self.assertTrue(stops, "Rainbow faces still animate separately instead of sharing paint")
        expected = Counter((n.get("class"), n.get("style")) for n in original)
        self.assertEqual(len(stops), len(expected))
        self.assertLess(len(stops), len(original) / 2)
        paints = {g.get("id"): (g[0].get("class"), g[0].get("style"))
                  for g in root.findall(".//s:linearGradient", ns)}
        faces = [n for n in root.iter() if n.get("fill", "").startswith("url(#contrib-paint-")]
        self.assertEqual(len(faces), len(original))
        for old, new in zip(original, faces):
            self.assertEqual(paints[new.get("fill")[5:-1]], (old.get("class"), old.get("style")))
            for attribute in ("x", "y", "width", "transform", "stroke"):
                self.assertEqual(new.get(attribute), old.get(attribute))
            self.assertNotIn("animation", new.get("style", ""))
        old_css = source.find("s:style", ns).text
        new_css = root.find(".//s:svg/s:style", ns).text
        for rule in re.findall(r"@keyframes rb-[^\n]+", old_css):
            self.assertIn(rule.replace("fill:", "stop-color:"), new_css)

    def test_committed_dashboard_uses_shared_paints(self):
        root = ET.parse(dashboard.OUT / "terminal-dark.svg").getroot()
        faces = [n for n in root.iter()
                 if n.tag.endswith("}rect") and n.get("class", "").startswith("rb-")]
        self.assertEqual(len(faces), 0, "Regenerate the committed dashboard after optimizing its generator")


if __name__ == "__main__":
    unittest.main()
