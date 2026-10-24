#!/usr/bin/env python3
"""Measure the actual README SVG-as-image rendering path in Chromium.

Optional local dependency: playwright (not needed by dashboard generation/CI).
Example: python scripts/benchmark_dashboard.py assets/terminal-dark.svg \
    --browser-executable /opt/google/chrome/chrome --max-p95-ms 33.4
Use --settle-ms 5700 to sample the 3D entrance, or the default for steady motion.
Compare revisions sequentially in the same environment; timings are device-specific.
"""

import argparse
import base64
import json
from pathlib import Path


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path, nargs="?", default=Path("assets/terminal-dark.svg"))
    parser.add_argument("--browser-executable")
    parser.add_argument("--settle-ms", type=int, default=15000)
    parser.add_argument("--sample-ms", type=int, default=3000)
    parser.add_argument("--max-p95-ms", type=float, default=33.4)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser_executable)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        image = base64.b64encode(args.svg.read_bytes()).decode()
        page.set_content('<body style="margin:0;background:#0d1117">'
                         f'<img width="1160" src="data:image/svg+xml;base64,{image}">')
        page.locator("img").evaluate("image => image.decode()")
        cdp = page.context.new_cdp_session(page)
        cdp.send("Performance.enable")
        page.wait_for_timeout(args.settle_ms)
        before = {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
        gaps = page.evaluate("""duration => new Promise(resolve => {
            const gaps = []; let start, last;
            function frame(t) {
                if (start === undefined) start = t;
                else gaps.push(t - last);
                last = t;
                if (t - start < duration) requestAnimationFrame(frame);
                else resolve(gaps);
            }
            requestAnimationFrame(frame);
        })""", args.sample_ms)
        after = {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
        p95 = sorted(gaps)[int(len(gaps) * .95)]
        print(json.dumps({
            "svg": str(args.svg), "browser": browser.version,
            "settle_ms": args.settle_ms, "frames": len(gaps),
            "fps": round(1000 * len(gaps) / sum(gaps), 1),
            "p95_frame_ms": round(p95, 1),
            "renderer_task_ms": round((after["TaskDuration"] - before["TaskDuration"]) * 1000),
            "pass": p95 <= args.max_p95_ms,
        }), flush=True)
        browser.close()
    return 0 if p95 <= args.max_p95_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
