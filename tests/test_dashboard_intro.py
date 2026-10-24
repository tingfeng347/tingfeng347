"""Keep the centered opening and sequence the 3D preview after every badge."""

import datetime as dt
import re
import unittest
import xml.etree.ElementTree as ET

from test_dashboard_motion import dashboard


class IntroDockTests(unittest.TestCase):
    def test_preview_is_embedded_and_keeps_its_styles_isolated(self):
        ns = {"s": dashboard.SVG_NS}
        for theme, filenames in dashboard.CONTRIBUTION_THEMES.items():
            for filename in filenames:
                with self.subTest(theme=theme, filename=filename):
                    panel = ET.fromstring(f'<svg xmlns="{dashboard.SVG_NS}">'
                                          f'{dashboard.contribution_preview(theme, 4.5, filename)}</svg>')
                    group = panel.find('s:g', ns)
                    self.assertEqual(group.get('style'), 'animation-delay:4.500s')
                    self.assertEqual(group.get('data-contrib-theme'), filename)
                    chart = group.find('s:g/s:svg', ns)
                    self.assertEqual(chart.get('class'), 'contrib-art')
                    animations = chart.findall('.//s:animate', ns) + chart.findall('.//s:animateTransform', ns)
                    self.assertGreater(len(animations), 0)
                    for animation in animations:
                        self.assertEqual(animation.get('repeatCount'), '1')
                        self.assertEqual(animation.get('fill'), 'freeze')
                        self.assertEqual(animation.get('begin'), '4.930s')
                        self.assertEqual(animation.get('dur'), '3s')
                        parent = next(n for n in chart.iter() if animation in list(n))
                        # The motion layer starts from frame zero; its static
                        # sibling keeps the finished chart for reduced motion.
                        final_value = animation.get('values').split(';')[0]
                        if animation.get('type'):
                            final_value = f"{animation.get('type')}({final_value})"
                        self.assertEqual(parent.get(animation.get('attributeName')), final_value)
                    static = group.find('s:svg', ns)
                    self.assertFalse(static.findall('.//s:animate', ns))
                    self.assertFalse(static.findall('.//s:animateTransform', ns))
                    original = ET.parse(dashboard.OUT.parent / 'profile-3d-contrib' / filename).getroot()
                    animated = {f'{{{dashboard.SVG_NS}}}animate', f'{{{dashboard.SVG_NS}}}animateTransform'}
                    expected = ET.fromstring(ET.tostring(original))
                    for parent in expected.iter():
                        for node in list(parent):
                            if node.tag not in animated:
                                continue
                            final = node.get('values').split(';')[-1]
                            if node.get('type'):
                                final = f"{node.get('type')}({final})"
                            parent.set(node.get('attributeName'), final)
                            parent.remove(node)
                    geometry = lambda tree: [(n.tag, n.attrib, (n.text or '').strip())
                                             for n in tree.iter() if n is not tree
                                             and n.tag not in animated
                                             and n.tag != f'{{{dashboard.SVG_NS}}}style'
                                             and 'fill-bg' not in n.get('class', '').split()]
                    self.assertEqual(geometry(static), geometry(expected))
                    self.assertFalse(chart.findall('s:rect[@class="fill-bg"]', ns))
                    css = chart.find('s:style', ns).text
                    self.assertIn('.contrib-art *{', css)
                    self.assertIn('.contrib-art .fill-fg{', css)
                    if filename == 'profile-night-rainbow.svg':
                        self.assertNotIn('.contrib-art @keyframes', css)
                        self.assertIn('.contrib-art .rb-l0-top{fill:rgb(77, 77, 25);}', css)
                        self.assertIn('.contrib-art .rb-l4-top{fill:rgb(64, 191, 64);}', css)
                        self.assertNotIn('infinite', css)
                    self.assertLessEqual(float(chart.get('x')) + float(chart.get('width')), dashboard.W - 20)

    def test_theme_is_selected_at_generation_time(self):
        from unittest.mock import patch
        for theme, choices in dashboard.CONTRIBUTION_THEMES.items():
            with patch.object(dashboard.random, 'choice', return_value=choices[-1]) as choose:
                svg = dashboard.contribution_preview(theme, 0)
                choose.assert_called_once_with(choices)
                self.assertIn(f'data-contrib-theme="{choices[-1]}"', svg)

    def test_rainbow_source_keeps_original_dynamic_style(self):
        source_path = dashboard.OUT.parent / 'profile-3d-contrib' / 'profile-night-rainbow.svg'
        source = source_path.read_text(encoding='utf-8')
        self.assertIn('animation:rb-l0-top 10s linear infinite;', source)
        self.assertIn('@keyframes rb-l0-top{', source)
        root = ET.parse(source_path).getroot()
        for parent in root.iter():
            for animation in list(parent):
                if animation.tag.endswith('animateTransform'):
                    initial = animation.get('values').split(';')[0]
                    self.assertEqual(parent.get('transform'),
                                     f"{animation.get('type')}({initial})")
                    return
        self.fail('rainbow source has no animated entrance frame')

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
        self.assertIn('from{transform:translateX(0)}to{transform:translateX(-240px)}', css)
        # With animations disabled the base styles retain the final two-column view.
        self.assertIn('.intro-layout{transform:translateX(-240px)', css)
        self.assertIn('.contrib-preview{opacity:1;', css)
        self.assertIn('@media (prefers-reduced-motion:reduce)', css)
        self.assertIn('.contrib-static{display:none}', css)
        self.assertIn('.contrib-motion{display:none}.contrib-static{display:inline}', css)


if __name__ == '__main__':
    unittest.main()
