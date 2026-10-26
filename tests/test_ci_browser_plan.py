"""Pure synthetic route-planning tests. No compiler, browser, server or network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import screenshots


class BrowserPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-route-plan-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'content').mkdir()
        (self.root / '_site').mkdir()
        self.encoded = '/%e6%97%a5%e6%9c%ac%e3%80%80test/'
        self.mapping = {'1': '/synthetic-post/', '2': '/forms/synthetic-child/', '3': self.encoded}
        self.routes = ['/', '/404.html', '/archive/', *self.mapping.values()]
        for pid, route in self.mapping.items():
            (self.root / 'content' / (pid + '.json')).write_text(json.dumps({
                'id': int(pid), 'type': 'page' if pid == '2' else 'post',
                'slug': route.strip('/').split('/')[-1], 'title': 'Synthetic planning fixture'}))
        for route in self.routes:
            target = self.root / '_site' / unquote(route).lstrip('/')
            if route.endswith('/'):
                target /= 'index.html'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('Synthetic planner input only. Not compiled historical content.')
        (self.root / 'archive.json').write_text(json.dumps({'site': 'steveonjava'}))
        self.report = {'routes': self.routes, 'record_routes': self.mapping, 'base_path': ''}
        self.save()

    def save(self):
        (self.root / 'build-report.json').write_text(json.dumps(self.report))

    def test_eight_shards_partition_every_route_without_loss(self):
        plans = [screenshots.plan(self.root, '', index, 8) for index in range(8)]
        assigned = [task['route'] for plan in plans for task in plan['selected']]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), screenshots.disk_routes(self.root / '_site'))
        self.assertEqual(plans[0]['record_count'], 3)

    def test_nested_and_encoded_records_have_explicit_types_and_routes(self):
        plan = screenshots.plan(self.root, '', 0, 1)
        tasks = {task['record_id']: task for task in plan['tasks'] if task['record_id']}
        self.assertEqual(tasks['2']['route'], '/forms/synthetic-child/')
        self.assertEqual(tasks['2']['record_type'], 'page')
        self.assertEqual(tasks['3']['route'], screenshots.uri_route(self.encoded))
        self.assertEqual(tasks['3']['record_type'], 'post')

    def test_omitted_generated_route_fails_closed(self):
        self.report['routes'] = self.report['routes'][1:]
        self.save()
        with self.assertRaisesRegex(ValueError, 'ALL generated'):
            screenshots.plan(self.root, '', 0, 1)

    def test_missing_record_route_fails_closed(self):
        del self.report['record_routes']['2']
        self.save()
        with self.assertRaisesRegex(ValueError, 'every content ID'):
            screenshots.plan(self.root, '', 0, 1)

    def test_invalid_uri_cannot_be_a_planned_route(self):
        for route in ('//evil.example/', '/%2f/', '/%00/', '/a//b/', '/%ff/'):
            with self.subTest(route=route), self.assertRaises(ValueError):
                screenshots.uri_route(route)

    def test_pending_checks_are_not_success_after_finalization(self):
        output = self.root / 'synthetic-review'
        _, manifest = screenshots.prepare(self.root, '', output, 0, 1, False)
        self.assertFalse(screenshots.finalize(output, manifest, 'success'))
        self.assertEqual(manifest['status'], 'failed')
        self.assertTrue((output / 'index.html').is_file())
        self.assertTrue(all(result['status'] == 'pending' for row in manifest['routes'] for result in row['checks'].values()))


if __name__ == '__main__':
    unittest.main()
