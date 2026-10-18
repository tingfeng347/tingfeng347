"""Keep the centered opening and sequence the 3D preview after every badge."""

import base64
import datetime as dt
import re
import unittest
import xml.etree.ElementTree as ET

from test_dashboard_motion import dashboard


class IntroDockTests(unittest.TestCase):
    def test_preview_is_embedded_and_keeps_its_styles_isolated(self):
        ns = {"s": dashboard.SVG_NS}
        for theme, filename in (("dark", "profile-night-view.svg"),
                                ("light", "profile-season.svg")):
            with self.subTest(theme=theme):
                panel = ET.fromstring(f'<svg xmlns="{dashboard.SVG_NS}">'
                                      f'{dashboard.contribution_preview(theme, 4.5)}</svg>')
                group = panel.find('s:g', ns)
                self.assertEqual(group.get('style'), 'animation-delay:4.500s')
                image = group.find('s:image', ns)
                prefix, encoded = image.get('href').split(',', 1)
                self.assertEqual(prefix, 'data:image/svg+xml;base64')
                chart = ET.fromstring(base64.b64decode(encoded))
                original = ET.parse(dashboard.OUT.parent / 'profile-3d-contrib' / filename).getroot()
                # All original final geometry, text and styles survive, but no
                # nested SMIL can freeze the preview on its incomplete frame.
                animated = {f'{{{dashboard.SVG_NS}}}animate',
                            f'{{{dashboard.SVG_NS}}}animateTransform'}
                self.assertFalse(any(n.tag in animated for n in chart.iter()))
                geometry = lambda tree: [(n.tag, n.attrib, (n.text or '').strip())
                                         for n in tree.iter() if n.tag not in animated]
                self.assertEqual(geometry(chart), geometry(original))
                self.assertFalse(group.findall('.//s:style', ns))
                self.assertLessEqual(float(image.get('x')) + float(image.get('width')),
                                     dashboard.W - dashboard.X0)

    def test_intro_docks_only_after_badges_then_terminal_starts(self):
        data = dict(top_starred=[], since='2023', languages=[], contributions=0,
                    commits=0, repos=0, prs=0, stars=0, weeks=[], active_days=0)
        badges = [[('fallback', 'Python', 60, 20, '3572A5')] * 3] * 3
        root = ET.fromstring(dashboard.render('dark', data, 'test', dt.date(2026, 10, 18), badges))
        ns = {'s': dashboard.SVG_NS}
        css = root.find('s:style', ns).text
        dock = float(re.search(r'animation:intro-dock [^;]+? ([\d.]+)s both', css)[1])
        intro = root.find('s:g[@class="intro-layout"]', ns)
        self.assertIsNotNone(intro.find('.//s:text[@class="i1"]', ns))
        badge_nodes = intro.findall('.//s:g[@class="badge"]', ns)
        self.assertEqual(len(badge_nodes), 9)
        last_badge = max(float(re.search(r'([\d.]+)s', b.get('style'))[1]) for b in badge_nodes)
        self.assertGreaterEqual(dock, last_badge + dashboard.BADGE_FADE)
        preview = root.find('s:g[@class="contrib-preview"]', ns)
        preview_start = float(re.search(r'([\d.]+)s', preview.get('style'))[1])
        self.assertGreater(preview_start, dock)
        first_command = root.find('.//s:clipPath[@id="cc0"]/s:rect', ns)
        command_start = float(re.search(r'linear ([\d.]+)s', first_command.get('style'))[1])
        self.assertGreaterEqual(command_start, dock + dashboard.INTRO_DOCK_DURATION)
        self.assertIn('from{transform:translateX(0)}to{transform:translateX(-220px)}', css)
        # With animations disabled the base styles retain the final two-column view.
        self.assertIn('.intro-layout{transform:translateX(-220px)', css)
        self.assertIn('.contrib-preview{opacity:1;', css)
        self.assertIn('@media (prefers-reduced-motion:reduce)', css)


if __name__ == '__main__':
    unittest.main()
