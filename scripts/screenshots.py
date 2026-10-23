#!/usr/bin/env python3
"""Exercise the actual built archive with a loopback-only browser preview."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main(root=ROOT, base="", out="screenshots"):
    output = root / "_site"
    report = json.loads((output / "build-report.json").read_text())
    records = [json.loads(path.read_text()) for path in sorted((root / "content").glob("*.json"))]
    first = records[0]
    missing_id = next(str(value) for value in range(1, len(records) + 2) if value not in {p["id"] for p in records})
    screenshots = root / out
    screenshots.mkdir(exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        """Serve the build under the project prefix only, as GitHub Pages does for a project site."""
        def translate_path(self, path):
            clean = urlsplit(path).path
            if base:
                if not clean.startswith(base + "/"):
                    return str(output / "__outside_base_path__")  # does not exist, so the browser sees a 404
                clean = clean[len(base):]
            return super().translate_path(clean)

    handler = partial(Handler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}" + base
    blocked, errors, failed = [], [], []

    def watch(page):
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: failed.append(f"{response.status} {response.url}")
                if response.status >= 400 and not response.url.endswith("/favicon.ico") else None)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            def route_request(route):
                parsed = urlsplit(route.request.url)
                if parsed.scheme == "http" and parsed.netloc == f"127.0.0.1:{server.server_port}":
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()
            for label, viewport in [("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})]:
                context = browser.new_context(viewport=viewport, service_workers="block")
                context.route("**/*", route_request)
                page = context.new_page()
                watch(page)
                for name, path in [("home", "/"), ("post", "/" + first["slug"] + "/"), ("404", "/404.html")]:
                    page.goto(origin + path, wait_until="networkidle")
                    assert page.locator(".prototype").count() == 1
                    assert page.locator("iframe, form").count() == 0
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"
                    page.screenshot(path=str(screenshots / f"{label}-{name}.png"), full_page=True)
                page.goto(origin + "/?p=" + str(first["id"]), wait_until="networkidle")
                page.wait_for_url(origin + "/" + first["slug"] + "/")
                for query in ["?p=" + missing_id, "?p=1&p=2", "?p=https%3A%2F%2Fevil.example", "?p=__proto__", "?p=01"]:
                    page.goto(origin + "/" + query, wait_until="networkidle")
                    assert page.locator("#legacy-status").inner_text()
                    assert page.url.startswith(origin + "/?")
                context.close()
            context = browser.new_context(java_script_enabled=False, service_workers="block")
            context.route("**/*", route_request)
            page = context.new_page()
            watch(page)
            paths = ["/", "/archive/", "/" + first["slug"] + "/", "/archive/" + first["date"][:4] + "/"]
            if first["categories"]:
                paths.append("/category/" + first["categories"][0]["slug"] + "/")
            for path in paths:
                page.goto(origin + path)
                assert page.locator("main h1").count() == 1
            page.goto(origin + "/")
            page.keyboard.press("Tab")
            assert page.locator(".skip-link").evaluate("el => el === document.activeElement")
            context.close()
            browser.close()
        assert not errors, errors
        assert not blocked, f"Unexpected external resource requests: {blocked}"
        assert not failed, f"Local requests that returned an HTTP error: {failed}"
        print(json.dumps({"screenshots": 6, "base_path": base, "posts": report["posts"], "javascript_errors": errors, "external_requests": blocked, "failed_local_requests": failed, "no_js": "passed", "legacy_ids": "passed"}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-path", default="", help="serve under this prefix, as a project site")
    parser.add_argument("--out", default="screenshots", help="screenshot directory inside the root")
    args = parser.parse_args()
    main(args.root, args.base_path, args.out)
