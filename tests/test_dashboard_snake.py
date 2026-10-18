"""Check self-contained snake embedding and the network-failure fallback."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_dashboard_motion import dashboard


class SnakeEmbeddingTests(unittest.TestCase):
    def test_embedded_animation_is_namespaced_and_delayed(self):
        for theme in dashboard.THEMES:
            with self.subTest(theme=theme):
                source = (dashboard.OUT / f"snake-{theme}.svg").read_text()
                panel = ET.fromstring(dashboard.embed_snake(source, 8.25))
                ns = {"s": dashboard.SVG_NS}
                art = panel.find("s:svg", ns)
                css = art.find("s:style", ns).text
                classes = {c for node in art.iter() for c in node.get("class", "").split()}
                self.assertIn("snk-s", classes)
                self.assertNotIn("cc", classes)  # terminal clip class must not hit cells
                self.assertTrue(all(c.startswith("snk-") or c == "snake-art" for c in classes))
                self.assertNotIn(":root", css)
                names = set(re.findall(r"@keyframes\s+([\w-]+)", css))
                referenced = set(re.findall(r"animation-name:([\w-]+)", css))
                self.assertTrue(referenced <= names)
                self.assertTrue(all(name.startswith("snk-") for name in names))
                self.assertIn("animation-delay:8.250s", css)
                self.assertIn("animation-fill-mode:backwards", css)
                self.assertFalse(art.findall(".//s:image", ns))
                self.assertLess(float(art.get("y")) + float(art.get("height")), 848)

    def test_refresh_preserves_cached_animation_on_network_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            for theme in dashboard.THEMES:
                (destination / f"snake-{theme}.svg").write_text(f"cached {theme}")
            with (patch.object(dashboard, "OUT", destination),
                  patch.object(dashboard.urllib.request, "urlopen", side_effect=OSError("offline")),
                  redirect_stderr(io.StringIO())):
                dashboard.refresh_snakes()
            for theme in dashboard.THEMES:
                self.assertEqual((destination / f"snake-{theme}.svg").read_text(), f"cached {theme}")

    def test_refresh_preserves_cached_animation_on_invalid_response(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            for theme in dashboard.THEMES:
                (destination / f"snake-{theme}.svg").write_text(f"cached {theme}")
            with (patch.object(dashboard, "OUT", destination),
                  patch.object(dashboard.urllib.request, "urlopen",
                               side_effect=lambda *args, **kwargs: io.BytesIO(b"<html/>")),
                  redirect_stderr(io.StringIO())):
                dashboard.refresh_snakes()
            for theme in dashboard.THEMES:
                self.assertEqual((destination / f"snake-{theme}.svg").read_text(), f"cached {theme}")


if __name__ == "__main__":
    unittest.main()
