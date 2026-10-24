#!/usr/bin/env python3
"""Exercise the built archive in the GitHub Actions runner with nonlocal requests blocked."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CAVEATS = ['Only the posts listed here are included', 'A limited selection of recovered posts',
           'Archival source material is unreviewed', 'Unreviewed source transcription',
           'Video archive prototype', 'Availability is unknown', 'Opening this link visits YouTube',
           'Historical motorcycle photograph is not included', 'Archive note:', 'Source and review notes']


def main(root=ROOT, base='', out='screenshots'):
    output = root / '_site'
    report = json.loads((root / 'build-report.json').read_text())
    records = [json.loads(path.read_text()) for path in sorted((root / 'content').glob('*.json'))]
    site = json.loads((root / 'archive.json').read_text())['site']
    first = records[0]
    missing_id = next(str(value) for value in range(1, len(records) + 2) if value not in {p['id'] for p in records})
    screenshots = root / out
    screenshots.mkdir(exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            clean = urlsplit(path).path
            if base:
                if not clean.startswith(base + '/'):
                    return str(output / '__outside_base_path__')
                clean = clean[len(base):]
            return super().translate_path(clean)

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(output)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}' + base
    blocked, errors, failed, metrics = [], [], [], []
    paths = [('home', '/'), ('post', '/' + first['slug'] + '/')]
    paths += [('post-' + str(post['id']), '/' + post['slug'] + '/') for post in records[1:]]
    paths += [('archive', '/archive/'), ('404', '/404.html')]
    if site == 'nighthacking':
        paths.append(('videos', '/videos/'))
    count = 0

    def watch(page):
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: failed.append(f'{response.status} {response.url}')
                if response.status >= 400 and not response.url.endswith('/favicon.ico') else None)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            def route_request(route):
                parsed = urlsplit(route.request.url)
                if parsed.scheme == 'http' and parsed.netloc == f'127.0.0.1:{server.server_port}':
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()
            for label, viewport in [('desktop', {'width': 1280, 'height': 900}), ('mobile', {'width': 390, 'height': 844})]:
                context = browser.new_context(viewport=viewport, service_workers='block')
                context.route('**/*', route_request)
                page = context.new_page()
                watch(page)
                for name, path in paths:
                    page.goto(origin + path, wait_until='networkidle')
                    assert page.locator('.prototype, .header-note, .dead-note, details').count() == 0
                    assert page.locator('iframe, form').count() == 0
                    assert page.locator('main h1').count() == 1
                    for phrase in CAVEATS:
                        assert phrase not in page.content(), (path, phrase)
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Horizontal overflow: {path}'
                    # Trigger lazy images and verify decoded pixels, then return to the initial viewport.
                    for image in page.locator('img').all():
                        image.scroll_into_view_if_needed()
                        image.evaluate("img => img.decode()")
                        assert image.evaluate('img => img.complete && img.naturalWidth > 0'), f'Broken image: {path}'
                    page.evaluate('window.scrollTo(0, 0)')
                    if label == 'desktop' and name == 'home':
                        if site == 'steveonjava':
                            box = page.locator('.site-shell').bounding_box()
                            assert abs(box['width'] - 880) < 2, box
                            photo = page.locator('.header-photo').bounding_box()
                            assert abs(photo['y'] - 87) < 3 and abs(photo['height'] - 200) < 2, photo
                            column = page.locator('#main').bounding_box()
                            side = page.locator('aside').bounding_box()
                            assert abs(column['width'] - 700) < 2 and abs(side['width'] - 180) < 2, (column, side)
                            entries = page.locator('#main > .entry').count()
                            assert entries == min(10, len(records)), entries
                            widgets = page.locator('aside h2').all_inner_texts()
                            assert widgets[-1] == 'Disclaimer' and 'Archives' in widgets, widgets
                            metrics.append({'shell': box, 'header_photo': photo, 'main': column, 'sidebar': side,
                                            'entries': entries, 'sidebar_headings': widgets})
                        else:
                            box = page.locator('.masthead-inner').bounding_box()
                            assert abs(box['width'] - 960) < 2, box
                            assert page.locator('.video-grid').evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length") == 3
                            stage = page.locator('.home-player').bounding_box()
                            assert abs(stage['width'] - 777) < 2, stage
                            panel = page.locator('.gallery-columns').bounding_box()
                            assert abs(panel['width'] - 960) < 2 and panel['y'] > stage['y'] + stage['height'], (stage, panel)
                            metrics.append({'masthead_inner': box, 'stage': stage, 'panel': panel})
                    page.screenshot(path=str(screenshots / f'{label}-{name}.png'), full_page=True)
                    count += 1
                page.goto(origin + '/?p=' + str(first['id']), wait_until='networkidle')
                page.wait_for_url(origin + '/' + first['slug'] + '/')
                for query in ['?p=' + missing_id, '?p=1&p=2', '?p=https%3A%2F%2Fevil.example', '?p=__proto__', '?p=01']:
                    page.goto(origin + '/' + query, wait_until='networkidle')
                    assert page.locator('#legacy-status').inner_text()
                    assert 'prototype' not in page.locator('#legacy-status').inner_text()
                    assert page.url.startswith(origin + '/?')
                context.close()
            context = browser.new_context(java_script_enabled=False, service_workers='block')
            context.route('**/*', route_request)
            page = context.new_page()
            watch(page)
            for _, path in paths:
                page.goto(origin + path)
                assert page.locator('main h1').count() == 1
            page.goto(origin + '/')
            page.keyboard.press('Tab')
            assert page.locator('.skip-link').evaluate('el => el === document.activeElement')
            context.close()
            browser.close()
        assert not errors, errors
        assert not blocked, f'Unexpected external resource requests: {blocked}'
        assert not failed, f'HTTP errors: {failed}'
        print(json.dumps({'screenshots': count, 'base_path': base, 'posts': report['posts'], 'javascript_errors': errors,
                          'external_requests': blocked, 'failed_local_requests': failed, 'no_js': 'passed',
                          'legacy_ids': 'passed', 'original_theme_geometry': metrics}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--base-path', default='')
    parser.add_argument('--out', default='screenshots')
    args = parser.parse_args()
    main(args.root, args.base_path, args.out)
