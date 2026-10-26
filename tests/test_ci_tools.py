"""Synthetic video-planning tests only: never build a site, launch a browser or fetch a URL."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_videos


class VideoPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-video-planner-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'content').mkdir()
        self.videos = ['SYNTH000001', 'SYNTH000002', 'SYNTH000003']
        for index, video in enumerate(self.videos, 1):
            self.record(index, video)
        self.opener = patch('urllib.request.build_opener', side_effect=AssertionError('Forbidden opener construction'))
        self.build_opener = self.opener.start()
        self.addCleanup(self.opener.stop)
        for target in ('urllib.request.urlopen', 'socket.create_connection'):
            guard = patch(target, side_effect=AssertionError('Forbidden real network request'))
            guard.start()
            self.addCleanup(guard.stop)

    def record(self, index, video):
        (self.root / 'content' / f'{index}.json').write_text(json.dumps({
            'id': index, 'title': f'Synthetic title {index}', 'video_id': video,
            'original_urls': ['https://unapproved.example.invalid/never-fetch-this']}))

    def mocked_opener(self, body=None, status=200):
        self.build_opener.side_effect = None
        opener = self.build_opener.return_value = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = status
        response.read.return_value = body if body is not None else json.dumps({
            'type': 'video', 'title': 'Synthetic response title', 'author_name': 'Synthetic channel'}).encode()
        return opener

    def invoke_cli(self, *arguments):
        output = self.root / 'availability.json'
        argv = ['check_videos.py', '--root', str(self.root), '--output', str(output), *arguments]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
            check_videos.main()
        return json.loads(output.read_text())

    def assert_not_checked(self, records):
        self.assertEqual(len(records), len(self.videos))
        self.assertTrue(all(record['outcome'] == 'not_checked' for record in records))
        self.assertTrue(all('checked_at' not in record and 'endpoint' not in record for record in records))
        self.build_opener.assert_not_called()

    def test_default_is_offline_without_even_constructing_an_opener(self):
        self.assert_not_checked(check_videos.check(self.root))

    def test_explicit_offline_cli(self):
        self.assert_not_checked(self.invoke_cli('--offline'))

    def test_default_cli_is_offline(self):
        self.assert_not_checked(self.invoke_cli())

    def test_online_without_allowlist_is_zero_requests(self):
        self.assert_not_checked(check_videos.check(self.root, online=True))
        self.assert_not_checked(self.invoke_cli('--online'))

    def test_online_empty_allowlist_is_zero_requests(self):
        allowlist = self.root / 'approved.json'
        allowlist.write_text('[]')
        self.assert_not_checked(self.invoke_cli('--online', '--approved-ids', str(allowlist)))

    def test_allowlist_does_not_enable_online_mode(self):
        self.assert_not_checked(check_videos.check(self.root, allowlist=[self.videos[0]]))
        allowlist = self.root / 'approved.json'
        allowlist.write_text(json.dumps([self.videos[0]]))
        self.assert_not_checked(self.invoke_cli('--approved-ids', str(allowlist)))

    def test_unrelated_allowlisted_id_is_never_fetched(self):
        self.assert_not_checked(check_videos.check(self.root, online=True, allowlist=['OTHER000001']))

    def test_exact_approved_intersection_only_and_no_supplied_url_fetching(self):
        opener = self.mocked_opener()
        records = check_videos.check(self.root, online=True, allowlist=[self.videos[1], 'OTHER000001'], max_requests=1)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        endpoint = urllib.parse.urlsplit(request.full_url)
        self.assertEqual((endpoint.scheme, endpoint.netloc, endpoint.path), ('https', 'www.youtube.com', '/oembed'))
        self.assertEqual(urllib.parse.parse_qs(endpoint.query), {'format': ['json'], 'url': ['https://www.youtube.com/watch?v=' + self.videos[1]]})
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 20})
        self.assertEqual([item['video_id'] for item in records if item['outcome'] != 'not_checked'], [self.videos[1]])
        self.assertEqual(records[1]['outcome'], 'metadata_available')
        self.assertNotIn('playback', records[1])
        self.assertEqual(opener.open.return_value.__enter__.return_value.read.call_args.args, (400001,))

    def test_inventory_larger_than_100_is_allowed_offline_and_with_small_selection(self):
        for index in range(4, 154):
            self.record(index, f'{index:011d}')
        self.assertEqual(len(check_videos.check(self.root)), 153)
        self.build_opener.assert_not_called()
        opener = self.mocked_opener()
        records = check_videos.check(self.root, online=True, allowlist=[self.videos[0]], max_requests=1)
        self.assertEqual(len(records), 153)
        opener.open.assert_called_once()

    def test_cap_is_checked_before_opener_construction(self):
        with self.assertRaisesRegex(ValueError, 'exceeds max_requests'):
            check_videos.check(self.root, online=True, allowlist=self.videos[:2], max_requests=1)
        self.build_opener.assert_not_called()

    def test_zero_cap_allows_offline_but_rejects_online_selection(self):
        self.assert_not_checked(check_videos.check(self.root, max_requests=0))
        with self.assertRaises(ValueError):
            check_videos.check(self.root, online=True, allowlist=[self.videos[0]], max_requests=0)
        self.build_opener.assert_not_called()

    def test_request_cap_must_be_bounded_integer(self):
        for cap in [-1, 101, True, 1.5, '1']:
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                check_videos.check(self.root, max_requests=cap)
        self.build_opener.assert_not_called()

    def test_allowlist_requires_exact_11_ascii_characters_without_normalization(self):
        for value in ['short', 'SYNTH000001x', ' SYNTH000001', 'SYNTH000001\n', '../SYNTH001', 'https://youtu.be/SYNTH000001', 'ＳYNTH000001', 'SYNTH00/001', None, 123]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_videos.check(self.root, online=True, allowlist=[value])
        self.build_opener.assert_not_called()

    def test_allowlist_shape_duplicates_and_size_fail_closed(self):
        for values in [None, self.videos[0], set(self.videos), {'id': self.videos[0]}, [self.videos[0]] * 2,
                       [f'{index:011d}' for index in range(101)]]:
            with self.subTest(values=repr(values)), self.assertRaises(ValueError):
                check_videos.check(self.root, online=True, allowlist=values)
        self.build_opener.assert_not_called()

    def test_entire_inventory_validated_before_any_online_request(self):
        self.record(9, '../attack')
        with self.assertRaisesRegex(ValueError, 'YouTube ID'):
            check_videos.check(self.root, online=True, allowlist=[self.videos[0]])
        self.build_opener.assert_not_called()

    def test_duplicate_video_ids_are_one_inventory_entry_and_one_request(self):
        self.record(4, self.videos[0])
        opener = self.mocked_opener()
        records = check_videos.check(self.root, online=True, allowlist=[self.videos[0]])
        self.assertEqual(len(records), 3)
        opener.open.assert_called_once()

    def test_dated_prior_evidence_is_distinct_and_never_current_availability(self):
        prior = {'video_id': self.videos[0], 'checked_at': '2020-01-02T03:04:05+00:00',
                 'outcome': 'metadata_available', 'method': 'synthetic prior evidence', 'http_status': 200}
        records = check_videos.check(self.root, prior_evidence=[prior])
        self.assert_not_checked(records)
        self.assertEqual(records[0]['prior_evidence'], [prior])
        self.assertEqual(records[1]['prior_evidence'], [])
        # Replanning an offline report does not turn its timestamps into new evidence.
        self.assertEqual(check_videos.check(self.root, prior_evidence=records), records)
        self.assertEqual(prior['checked_at'], '2020-01-02T03:04:05+00:00')

    def test_prior_evidence_must_be_dated_and_timezone_aware(self):
        for date in [None, '', 'not-a-date', '2020-01-02T03:04:05']:
            with self.subTest(date=date), self.assertRaises(ValueError):
                check_videos.check(self.root, prior_evidence=[{'video_id': self.videos[0], 'outcome': 'metadata_available', 'checked_at': date}])
        self.build_opener.assert_not_called()

    def test_inconclusive_response_does_not_delete_or_hide_video(self):
        opener = self.mocked_opener(status=404)
        records = check_videos.check(self.root, online=True, allowlist=[self.videos[0]])
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]['outcome'], 'check_inconclusive')
        self.assertNotIn('deleted', json.dumps(records))
        opener.open.assert_called_once()

    def test_transport_failure_is_inconclusive_and_retains_prior_evidence(self):
        opener = self.mocked_opener()
        opener.open.side_effect = urllib.error.URLError('Synthetic transport failure')
        prior = {'video_id': self.videos[0], 'checked_at': '2020-01-02T03:04:05Z', 'outcome': 'metadata_available'}
        records = check_videos.check(self.root, online=True, allowlist=[self.videos[0]], prior_evidence=[prior])
        self.assertEqual(records[0]['outcome'], 'check_inconclusive')
        self.assertEqual(records[0]['prior_evidence'], [prior])
        self.assertEqual(len(records), 3)

    def test_oversized_and_challenge_responses_are_inconclusive(self):
        for body in [b'x' * 400001, b'<html>synthetic challenge</html>', b'[]']:
            with self.subTest(size=len(body)):
                self.mocked_opener(body=body)
                records = check_videos.check(self.root, online=True, allowlist=[self.videos[0]])
                self.assertEqual(records[0]['outcome'], 'check_inconclusive')

    def test_redirect_handler_never_follows_redirects(self):
        self.assertIsNone(check_videos.NoRedirects().redirect_request(None, None, 302, '', {}, 'https://unapproved.example.invalid/'))
        self.build_opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
