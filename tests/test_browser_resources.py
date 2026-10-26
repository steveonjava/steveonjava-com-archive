"""Pure browser-helper tests. No browser, server, network or site build."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('browser_resources', Path(__file__).resolve().parents[1] / 'scripts/screenshots.py')
assert SPEC is not None and SPEC.loader is not None
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)


class FakePage:
    def __init__(self, snapshots=()):
        self.snapshots = iter(snapshots)
        self.expressions = []
        self.waits = []
        self.handlers = {}

    def evaluate(self, expression):
        self.expressions.append(expression)
        return next(self.snapshots) if 'pending:' in expression else None

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    def on(self, event, callback):
        self.handlers[event] = callback


READY = dict(styles=True, pending=[], broken=[], fonts=True)


class ResourceHelpers(unittest.TestCase):
    def test_nojs_uses_synchronous_state_not_promises_or_page_timers(self):
        page = FakePage([READY])
        browser.local_resources_ready(page, nojs=True)
        self.assertEqual(page.waits, [50])
        for expression in page.expressions:
            self.assertNotIn('async', expression)
            self.assertNotIn('Promise', expression)
            self.assertNotIn('setTimeout', expression)
            self.assertNotIn('requestAnimationFrame', expression)

    def test_nojs_waits_for_pending_images_and_fonts(self):
        page = FakePage([dict(READY, pending=['http://127.0.0.1/image.jpg'], fonts=False), READY])
        browser.local_resources_ready(page, nojs=True)
        self.assertEqual(page.waits, [50, 50])

    def test_nojs_rejects_a_complete_but_broken_image(self):
        page = FakePage([dict(READY, broken=['http://127.0.0.1/broken.jpg'])])
        with self.assertRaisesRegex(AssertionError, 'Broken local images'):
            browser.local_resources_ready(page, nojs=True)

    def test_nojs_deadline_is_host_side_and_bounded(self):
        page = FakePage([dict(READY, pending=['http://127.0.0.1/pending.jpg'])])
        with patch.object(browser.time, 'monotonic', side_effect=[0, 11]):
            with self.assertRaisesRegex(AssertionError, 'readiness timeout'):
                browser.local_resources_ready(page, nojs=True)

    def test_enabled_javascript_retains_full_decode_and_paint_checks(self):
        page = FakePage()
        browser.local_resources_ready(page)
        expression = page.expressions[0]
        self.assertIn('await img.decode()', expression)
        self.assertIn('requestAnimationFrame', expression)
        self.assertIn('10000', expression)

    def test_late_events_stay_with_their_own_page_errors(self):
        first, second = FakePage(), FakePage()
        first_errors, second_errors = [], []
        browser.watch_page(first, first_errors, '', set())
        browser.watch_page(second, second_errors, '', set())
        first.handlers['requestfailed'](SimpleNamespace(url='http://127.0.0.1/a.jpg', failure='net::ERR_CONNECTION_RESET'))
        self.assertEqual(len(first_errors), 1)
        self.assertEqual(second_errors, [])

    def test_late_route_or_legacy_errors_cannot_finalize_as_success(self):
        for kind in ('route', 'legacy'):
            manifest = {'status': 'running', 'errors': [],
                        'routes': [{'checks': {'desktop': {'status': 'passed', 'errors': []}}, 'captures': {}}],
                        'legacy_ids': {'desktop': {'status': 'passed', 'errors': []}}}
            if kind == 'route':
                manifest['routes'][0]['checks']['desktop']['errors'].append('Synthetic late error')
            else:
                manifest['legacy_ids']['desktop']['errors'].append('Synthetic late error')
            with self.subTest(kind=kind), patch.object(browser, 'write_review'):
                self.assertFalse(browser.finalize(Path('unused-synthetic-output'), manifest))
                self.assertEqual(manifest['status'], 'failed')

    def test_only_expected_navigation_aborts_are_ignored(self):
        page, errors, expected = FakePage(), [], set()
        browser.watch_page(page, errors, '', expected)
        request = SimpleNamespace(url='http://127.0.0.1/a.jpg', failure='net::ERR_ABORTED')
        page.handlers['requestfailed'](request)
        self.assertEqual(len(errors), 1)
        expected.add(page)
        page.handlers['requestfailed'](request)
        self.assertEqual(len(errors), 1)
        request.failure = 'net::ERR_CONNECTION_RESET'
        page.handlers['requestfailed'](request)
        self.assertEqual(len(errors), 2)


if __name__ == '__main__':
    unittest.main()
