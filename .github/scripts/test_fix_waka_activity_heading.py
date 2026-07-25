from __future__ import annotations

import unittest

from fix_waka_activity_heading import fix_heading


def make_readme(heading: str) -> str:
    return f"""before
<!--START_SECTION:waka-->
{heading}

```text
Morning 23 commits
Daytime 75 commits
Evening 77 commits
Night 14 commits
```
📅 **I'm Most Productive on Thursday**
<!--END_SECTION:waka-->
after
"""


class FixHeadingTests(unittest.TestCase):
    def test_accepts_upstream_heading_with_trailing_space(self) -> None:
        result = fix_heading(make_readme("**I'm an Early 🐤** "))

        self.assertIn("**I'm most active in the Evening 🌃**", result)
        self.assertNotIn("I'm an Early", result)

    def test_does_not_depend_on_upstream_heading_copy(self) -> None:
        result = fix_heading(make_readme("**Commit chronotype changed**"))

        self.assertIn("**I'm most active in the Evening 🌃**", result)

    def test_preserves_later_bold_headings(self) -> None:
        result = fix_heading(make_readme("**I'm a Night 🦉**"))

        self.assertIn("📅 **I'm Most Productive on Thursday**", result)


if __name__ == "__main__":
    unittest.main()
