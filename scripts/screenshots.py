#!/usr/bin/env python3
"""Shard complete route coverage in CI; no nonlocal browser requests are permitted.

--plan-only and --finalize-status never import Playwright or start a server.
Normal execution belongs in GitHub Actions, not on the operator's workstation.
"""
import argparse
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CAVEATS = ['Only the posts listed here are included', 'A limited selection of recovered posts',
           'Archival source material is unreviewed', 'Unreviewed source transcription',
           'Video archive prototype', 'Availability is unknown', 'Opening this link visits YouTube',
           'Historical motorcycle photograph is not included', 'Archive note:', 'Source and review notes']
CSP = "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
VIEWPORTS = {'desktop': {'width': 1280, 'height': 900}, 'mobile': {'width': 390, 'height': 844}}
MODES = ('desktop', 'mobile', 'desktop-nojs', 'mobile-nojs')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def uri_route(value):
    """Canonicalize each path segment, not slashes, and reject ambiguous paths."""
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        raise ValueError('Route must be a root-relative URI')
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment or parsed.netloc or parsed.scheme:
        raise ValueError('Route cannot include an origin, query or fragment')
    if re.search(r'%(?![0-9a-fA-F]{2})', value):
        raise ValueError('Invalid percent escape in route')
    parts = []
    for part in value.split('/'):
        decoded = unquote(part, errors='strict')
        if decoded in ('.', '..') or any(c in decoded for c in '/\\') or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
            raise ValueError('Unsafe route segment')
        parts.append(quote(decoded, safe='-._~'))
    route = '/'.join(parts)
    if '//' in route:
        raise ValueError('Empty route segment')
    return route


def disk_routes(output):
    if not output.is_dir() or output.is_symlink():
        raise ValueError('Missing or unsafe _site directory')
    routes = set()
    for path in sorted(output.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink in generated site')
        if path.is_file() and path.suffix == '.html':
            relative = path.relative_to(output).as_posix()
            if relative == 'index.html':
                route = '/'
            elif relative.endswith('/index.html'):
                route = '/' + relative[:-len('index.html')]
            else:
                route = '/' + relative
            # Filesystem names are decoded, so quote literal percent characters too.
            routes.add('/'.join(quote(part, safe='-._~') for part in route.split('/')))
    if not routes:
        raise ValueError('Generated site has no HTML routes')
    return routes


def plan(root, base, shard_index, shard_count, allow_fallback=False):
    if type(shard_count) is not int or not 1 <= shard_count <= 64 or not 0 <= shard_index < shard_count:
        raise ValueError('Require 1..64 shards and a zero-based index smaller than the count')
    if not re.fullmatch(r'(?:/[a-z0-9]+(?:-[a-z0-9]+)*)?', base):
        raise ValueError('Invalid base path')
    output = root / '_site'
    actual = disk_routes(output)
    report_path = root / 'build-report.json'
    report = json.loads(report_path.read_text()) if report_path.is_file() else {}
    records = [json.loads(path.read_text()) for path in sorted((root / 'content').glob('*.json'))]
    ids = [str(record['id']) for record in records]
    if not ids or len(ids) != len(set(ids)) or any(not re.fullmatch(r'[1-9][0-9]*', value) for value in ids):
        raise ValueError('Missing, invalid or duplicate content record IDs')
    if 'routes' not in report or 'record_routes' not in report:
        if not allow_fallback:
            raise ValueError('build-report.json must contain all routes and record_routes; fallback is opt-in')
        routes = sorted(actual)
        record_routes = {str(record['id']): uri_route('/' + record['slug'] + '/') for record in records}
        source = 'explicit filesystem fallback'
    else:
        if not isinstance(report['routes'], list) or not isinstance(report['record_routes'], dict):
            raise ValueError('Invalid route report schema')
        routes = [uri_route(route) for route in report['routes']]
        record_routes = {key: uri_route(route) for key, route in report['record_routes'].items()}
        if report.get('base_path', base) != base:
            raise ValueError('Route report base_path differs from served path')
        source = 'build-report.json, cross-checked against every generated HTML file'
    if len(routes) != len(set(routes)) or set(routes) != actual:
        raise ValueError('Reported routes do not match ALL generated HTML routes')
    if set(record_routes) != set(ids) or len(set(record_routes.values())) != len(ids):
        raise ValueError('record_routes must map every content ID to a unique route')
    if not set(record_routes.values()).issubset(actual):
        raise ValueError('A content record has no generated route')
    record_types = {str(record['id']): record['type'] for record in records}
    if any(kind not in ('post', 'page') for kind in record_types.values()):
        raise ValueError('Invalid record type')
    by_route = {route: key for key, route in record_routes.items()}
    ordered = sorted(actual)
    tasks = []
    for ordinal, route in enumerate(ordered):
        record_id = by_route.get(route)
        # Record IDs, not slugs, keep filenames stable across encoded/Unicode routes.
        name = 'post-' + record_id if record_id else {'/': 'home', '/archive/': 'archive', '/videos/': 'videos', '/404.html': '404'}.get(route, f'route-{ordinal:04d}')
        captures, aliases = {}, {}
        for viewport in VIEWPORTS:
            captures[viewport] = f'{name}-{viewport}.png' if record_id else f'{viewport}-{name}.png'
            aliases[viewport] = []
            if record_id:
                aliases[viewport].append(f'{viewport}-post.png' if record_id == ids[0] else f'{viewport}-post-{record_id}.png')
        tasks.append({'ordinal': ordinal, 'route': route, 'record_id': record_id,
                      'record_type': record_types.get(record_id),
                      'shard': ordinal % shard_count, 'captures': captures, 'aliases': aliases})
    site = json.loads((root / 'archive.json').read_text())['site']
    if site not in ('steveonjava', 'nighthacking'):
        raise ValueError('Unknown archive theme')
    return {'schema_version': 1, 'base_path': base, 'source': source, 'shard_index': shard_index,
            'shard_count': shard_count, 'route_count': len(tasks), 'record_count': len(ids),
            'record_routes': record_routes, 'tasks': tasks,
            'selected': [task for task in tasks if task['shard'] == shard_index],
            'site': site, 'post_count': sum(record.get('type') == 'post' for record in records)}


def write_review(output, manifest):
    """Checkpoint evidence after each visit so assertion failures retain review artifacts."""
    output.mkdir(parents=True, exist_ok=True)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + '\n')
    errors = {'status': manifest['status'], 'errors': manifest['errors'],
              'route_errors': [{'route': row['route'], 'mode': mode, 'errors': result['errors']}
                               for row in manifest['routes'] for mode, result in row['checks'].items()
                               if result['errors']]}
    (output / 'errors.json').write_text(json.dumps(errors, indent=2, ensure_ascii=True) + '\n')
    sections, nav = [], []
    for index, row in enumerate(manifest['routes']):
        anchor = f'route-{index}'
        title = escape(row['route']) + (f" (record {escape(row['record_id'])})" if row['record_id'] else '')
        nav.append(f'<li><a href="#{anchor}">{title}</a></li>')
        checks = ''.join(f'<li>{escape(mode)}: <strong>{escape(result["status"])}</strong>'
                         + '<pre>' + escape('\n'.join(result['errors'])) + '</pre></li>'
                         for mode, result in row['checks'].items())
        captures = ''.join(f'<figure><a href="{quote(filename)}"><img loading="lazy" src="{quote(filename)}" alt="{escape(mode)} capture"></a><figcaption>{escape(mode)}: {escape(filename)}</figcaption></figure>'
                           for mode, filename in row['captures'].items() if (output / filename).is_file())
        sections.append(f'<section id="{anchor}"><h2>{title}</h2><ul>{checks}</ul><div class="captures">{captures}</div><a href="#top">Back to route list</a></section>')
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Archive route review</title><style>body{font:16px system-ui;margin:2rem;overflow-wrap:anywhere}section{border-top:1px solid #aaa;margin-top:2rem}.captures{display:flex;gap:1rem;align-items:flex-start}figure{margin:0;max-width:48%}img{width:100%;height:auto;max-height:70vh;object-fit:contain;object-position:top}pre{white-space:pre-wrap}li{margin:.3rem 0}</style></head><body id="top"><h1>Archive route review</h1>'
    html += f'<p>Shard {manifest["shard_index"]} of {manifest["shard_count"]}. Status: <strong>{escape(manifest["status"])}</strong>.</p><p><a href="manifest.json">Status manifest</a> · <a href="errors.json">Errors</a> · <a href="route-plan.json">Full deterministic route plan</a></p><pre>'
    html += escape('\n'.join(manifest['errors'])) + '</pre><nav aria-label="Routes"><ul>' + ''.join(nav) + '</ul></nav>' + ''.join(sections) + '</body></html>'
    (output / 'index.html').write_text(html)


def prepare(root, base, output, index, count, fallback):
    manifest = {'schema_version': 1, 'status': 'planning', 'base_path': base,
                'shard_index': index, 'shard_count': count, 'errors': [], 'routes': [],
                'legacy_ids': {'status': 'not_assigned'}, 'original_theme_geometry': []}
    write_review(output, manifest)
    try:
        route_plan = plan(root, base, index, count, fallback)
        (output / 'route-plan.json').write_text(json.dumps(route_plan, indent=2, ensure_ascii=True) + '\n')
        manifest.update(status='planned', total_routes=route_plan['route_count'], total_records=route_plan['record_count'])
        for task in route_plan['selected']:
            manifest['routes'].append({'route': task['route'], 'record_id': task['record_id'],
                                       'record_type': task['record_type'],
                                       'planned_captures': task['captures'], 'captures': {}, 'aliases': task['aliases'],
                                       'checks': {mode: {'status': 'pending', 'errors': []} for mode in MODES}})
        write_review(output, manifest)
        return route_plan, manifest
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['errors'].append(f'Route planning: {type(error).__name__}: {error}')
        write_review(output, manifest)
        raise


def local_resources_ready(page):
    # One load boundary, then explicit stylesheet, lazy-image decode and font readiness.
    # Playwright evaluation works even in a java_script_enabled=False browsing context.
    page.evaluate("""async () => {
        const ready = async () => {
            for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
                if (!link.sheet) throw new Error('Stylesheet not ready: ' + link.href);
            }
            await Promise.all(Array.from(document.images, async img => {
                img.loading = 'eager';
                await img.decode();
                if (!img.complete || img.naturalWidth < 1) throw new Error('Broken image: ' + img.src);
            }));
            await document.fonts.ready;
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        };
        let timer;
        try {
            await Promise.race([ready(), new Promise((_, reject) => {
                timer = setTimeout(() => reject(new Error('Local resource readiness timeout')), 10000);
            })]);
        } finally { clearTimeout(timer); }
    }""")


def check_page(page, origin, base):
    require(page.locator('.prototype, .header-note, .dead-note, details, iframe, form, object, embed, base').count() == 0,
            'Unexpected caveat or active/embed element')
    require(page.locator('main h1').count() == 1, 'Expected exactly one main h1')
    require(page.locator('meta[name="robots"]').get_attribute('content') == 'noindex,nofollow', 'Missing robots policy')
    require(page.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute('content') == CSP, 'Unexpected CSP')
    content = page.content()
    for phrase in CAVEATS:
        require(phrase not in content, 'Reader-facing caveat: ' + phrase)
    require(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Horizontal overflow')
    resources = page.locator('img[src], script[src], link[rel="stylesheet"][href]').evaluate_all(
        "els => els.map(el => el.src || el.href)")
    for resource in resources:
        parsed = urlsplit(resource)
        require(f'{parsed.scheme}://{parsed.netloc}' == origin and parsed.path.startswith(base + '/'),
                'Nonlocal or base-escaping resource: ' + resource)
    for link in page.locator('a[href]').evaluate_all("els => els.map(el => ({href:el.href, rel:el.rel}))"):
        parsed = urlsplit(link['href'])
        if parsed.scheme in ('http', 'https') and f'{parsed.scheme}://{parsed.netloc}' != origin:
            require({'nofollow', 'noopener', 'noreferrer'}.issubset(set(link['rel'].split())), 'Unsafe external link attributes')
    page.keyboard.press('Tab')
    require(page.locator('.skip-link').evaluate('el => el === document.activeElement'), 'Keyboard skip link not first')
    page.keyboard.press('Enter')
    require(page.locator('#main').evaluate('el => el === document.activeElement'), 'Keyboard skip link does not reach main')
    page.locator('#main').evaluate('el => el.blur()')
    page.evaluate('window.scrollTo(0, 0)')


def theme_geometry(page, site, post_count):
    metrics = {'site': site}
    if site == 'steveonjava':
        box = page.locator('.site-shell').bounding_box()
        require(box and abs(box['width'] - 880) < 2, f'Shell geometry: {box}')
        photo = page.locator('.header-photo')
        metrics['header_photo'] = None
        if photo.count():
            usable = photo.evaluate('img => img.complete && img.naturalWidth > 0')
            require(usable, 'Header artwork does not decode')
            image_box = photo.bounding_box()
            require(image_box and abs(image_box['y'] - 87) < 3 and abs(image_box['height'] - 200) < 2, f'Header geometry: {image_box}')
            metrics['header_photo'] = image_box
        column, side = page.locator('#main').bounding_box(), page.locator('aside').bounding_box()
        require(column and side and abs(column['width'] - 700) < 2 and abs(side['width'] - 180) < 2,
                f'Column geometry: {column}, {side}')
        entries = page.locator('#main > .entry').count()
        require(entries == min(10, post_count), f'Home entry count: {entries}')
        widgets = page.locator('aside h2').all_inner_texts()
        require(widgets and widgets[-1] == 'Disclaimer' and 'Archives' in widgets, f'Sidebar headings: {widgets}')
        metrics.update(shell=box, main=column, sidebar=side, entries=entries, sidebar_headings=widgets)
    else:
        box = page.locator('.masthead-inner').bounding_box()
        panel = page.locator('.gallery-columns').bounding_box()
        require(box and abs(box['width'] - 960) < 2, f'Masthead geometry: {box}')
        require(panel and abs(panel['width'] - 960) < 2, f'Gallery geometry: {panel}')
        grid = page.locator('.video-grid')
        if grid.count():
            require(grid.evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length") == 3, 'Gallery is not three columns')
        stage = page.locator('.home-player')
        stage_box = None
        # No thumbnail means no stage. Other theme geometry remains mandatory.
        if stage.count():
            image = stage.locator('img')
            require(image.count() == 1 and image.evaluate('img => img.complete && img.naturalWidth > 0'), 'Unusable home hero thumbnail')
            stage_box = stage.bounding_box()
            require(stage_box and abs(stage_box['width'] - 777) < 2, f'Hero geometry: {stage_box}')
            require(panel['y'] > stage_box['y'] + stage_box['height'], 'Gallery overlaps home hero')
        metrics.update(masthead_inner=box, stage=stage_box, panel=panel)
    return metrics


def run_browser(root, base, output, route_plan, manifest):
    from playwright.sync_api import sync_playwright

    site_output = root / '_site'

    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            clean = urlsplit(path).path
            if base:
                if not clean.startswith(base + '/'):
                    return str(site_output / '__outside_base_path__')
                clean = clean[len(base):]
            return super().translate_path(clean)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(site_output)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    served = origin + base
    active_errors = []

    def route_request(route):
        parsed = urlsplit(route.request.url)
        if parsed.scheme == 'http' and parsed.netloc == f'127.0.0.1:{server.server_port}':
            route.continue_()
        else:
            active_errors.append('Blocked external request: ' + route.request.url)
            route.abort()

    def watch(page):
        page.on('pageerror', lambda error: active_errors.append('JavaScript: ' + str(error)))
        page.on('console', lambda message: active_errors.append('Console: ' + message.text) if message.type == 'error' else None)
        page.on('response', lambda response: active_errors.append(f'HTTP {response.status}: {response.url}')
                if response.status >= 400 and urlsplit(response.url).path != base + '/favicon.ico' else None)
        page.on('requestfailed', lambda request: active_errors.append('Failed resource: ' + request.url)
                if urlsplit(request.url).path != base + '/favicon.ico' else None)

    def visit(page, route):
        response = page.goto(served + route, wait_until='load', timeout=15000)
        require(response and response.status == 200, f'Expected browser HTTP 200: {route}')
        require(uri_route(urlsplit(page.url).path) == uri_route(base + route), 'Unexpected navigation redirect')
        local_resources_ready(page)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for mode in MODES:
                viewport = mode.split('-')[0]
                context = browser.new_context(viewport=VIEWPORTS[viewport], java_script_enabled=not mode.endswith('-nojs'), service_workers='block')
                context.set_default_timeout(12000)
                context.route('**/*', route_request)
                def deny_websocket(socket):
                    active_errors.append('Blocked WebSocket: ' + socket.url)
                    socket.close()
                context.route_web_socket('**/*', deny_websocket)
                for row in manifest['routes']:
                    result = row['checks'][mode]
                    active_errors = result['errors']
                    page = context.new_page()
                    watch(page)
                    try:
                        visit(page, row['route'])
                        result['http_status'] = 200
                        check_page(page, origin, base)
                        if row['record_id'] and not mode.endswith('-nojs'):
                            parameter = 'page_id' if row['record_type'] == 'page' else 'p'
                            page.goto(served + '/?' + parameter + '=' + row['record_id'], wait_until='domcontentloaded', timeout=15000)
                            page.wait_for_url(lambda value: uri_route(urlsplit(value).path) == uri_route(base + row['route']) and not urlsplit(value).query, wait_until='load')
                            local_resources_ready(page)
                            result['legacy_parameter'] = parameter
                            result['legacy_id'] = row['record_id']
                        if mode == 'desktop' and row['route'] == '/':
                            manifest['original_theme_geometry'].append(theme_geometry(page, route_plan['site'], route_plan['post_count']))
                    except Exception as error:
                        active_errors.append(f'{type(error).__name__}: {error}')
                    finally:
                        # Capture once per normal route/viewport, even after an assertion fails.
                        if not mode.endswith('-nojs'):
                            filename = row['planned_captures'][mode]
                            try:
                                page.screenshot(path=str(output / filename), full_page=True, timeout=15000)
                                row['captures'][mode] = filename
                            except Exception as error:
                                active_errors.append(f'Capture: {type(error).__name__}: {error}')
                        result['status'] = 'failed' if active_errors else 'passed'
                        page.close()
                        write_review(output, manifest)
                # Only the shard owning home checks query translation; every record has a direct-route check above.
                if any(row['route'] == '/' for row in manifest['routes']) and not mode.endswith('-nojs'):
                    legacy = manifest['legacy_ids'].setdefault(mode, {'status': 'pending', 'errors': []})
                    manifest['legacy_ids']['status'] = 'assigned'
                    active_errors = legacy['errors']
                    page = context.new_page()
                    watch(page)
                    try:
                        ids = route_plan['record_routes']
                        first_id = next(iter(ids))
                        response = page.goto(served + '/?p=' + first_id, wait_until='load', timeout=15000)
                        require(response and response.status == 200, 'Legacy entry not HTTP 200')
                        page.wait_for_url(served + ids[first_id], wait_until='load')
                        local_resources_ready(page)
                        missing = next(str(value) for value in range(1, len(ids) + 2) if str(value) not in ids)
                        for query in ['?p=' + missing, '?p=1&p=2', '?p=https%3A%2F%2Fevil.example', '?p=__proto__', '?p=01', '?page_id=' + missing, '?p=' + first_id + '&page_id=' + first_id, '?page_id=__proto__']:
                            page.goto(served + '/' + query, wait_until='load', timeout=15000)
                            local_resources_ready(page)
                            status = page.locator('#legacy-status')
                            require(status.inner_text() and 'prototype' not in status.inner_text(), 'Missing concise unknown-ID navigation')
                            require(page.url.startswith(served + '/?'), 'Unsafe legacy ID redirected')
                    except Exception as error:
                        active_errors.append(f'{type(error).__name__}: {error}')
                    finally:
                        legacy['status'] = 'failed' if active_errors else 'passed'
                        page.close()
                        write_review(output, manifest)
                context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def finalize(output, manifest, job_status=None):
    if job_status and job_status != 'success':
        manifest['errors'].append('CI job status before artifact upload: ' + job_status)
    complete = all(result['status'] == 'passed' for row in manifest['routes'] for result in row['checks'].values())
    legacy_failed = any(isinstance(value, dict) and value['status'] != 'passed' for value in manifest['legacy_ids'].values())
    if manifest['status'] in ('planning', 'planned') and job_status:
        manifest['errors'].append('Browser execution did not complete; planned/pending checks are not success')
    manifest['status'] = 'passed' if complete and not legacy_failed and not manifest['errors'] else 'failed'
    manifest['screenshots'] = sum(len(row['captures']) for row in manifest['routes'])
    write_review(output, manifest)
    return manifest['status'] == 'passed'


def main(root=ROOT, base='', out='screenshots', shard_index=0, shard_count=1,
         plan_only=False, allow_route_fallback=False, finalize_status=None):
    output = root / out
    if finalize_status:
        try:
            manifest = json.loads((output / 'manifest.json').read_text())
        except (OSError, ValueError):
            manifest = {'status': 'planning', 'base_path': base, 'shard_index': shard_index, 'shard_count': shard_count,
                        'routes': [], 'errors': ['No browser manifest was produced'], 'legacy_ids': {}}
        finalize(output, manifest, finalize_status)
        return 0  # Preserve the original failed step; this always-run diagnostic step must upload evidence.
    route_plan, manifest = prepare(root, base, output, shard_index, shard_count, allow_route_fallback)
    if plan_only:
        return 0
    manifest['status'] = 'running'
    write_review(output, manifest)
    try:
        run_browser(root, base, output, route_plan, manifest)
    except Exception as error:
        manifest['errors'].append(f'Browser execution: {type(error).__name__}: {error}')
    passed = finalize(output, manifest)
    print(json.dumps({'status': manifest['status'], 'shard': shard_index, 'routes': len(manifest['routes']),
                      'screenshots': manifest['screenshots'], 'manifest': str(output / 'manifest.json')}))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--base-path', default='')
    parser.add_argument('--out', default='screenshots')
    parser.add_argument('--shard-index', type=int, default=0)
    parser.add_argument('--shard-count', type=int, default=1)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--allow-route-fallback', action='store_true', help='Explicit compatibility fallback; normal CI requires report routes')
    parser.add_argument('--finalize-status', choices=('success', 'failure', 'cancelled', 'skipped'))
    args = parser.parse_args()
    raise SystemExit(main(args.root, args.base_path, args.out, args.shard_index, args.shard_count,
                          args.plan_only, args.allow_route_fallback, args.finalize_status))
