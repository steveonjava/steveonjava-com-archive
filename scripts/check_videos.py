#!/usr/bin/env python3
"""Check public YouTube metadata separately from the offline site build.

No cookies, player, captions or video bytes. Results are review artifacts, never
page boilerplate. Metadata availability is not proof of playback or reuse rights.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

VIDEO = re.compile(r'[A-Za-z0-9_-]{11}\Z', re.ASCII)


def classify(status, body):
    if status != 200:
        return 'check_inconclusive', None, None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        return 'check_inconclusive', None, None
    if not isinstance(data, dict):
        return 'check_inconclusive', None, None
    title, channel = data.get('title'), data.get('author_name')
    if data.get('type') != 'video' or not all(isinstance(v, str) and v.strip() and len(v) <= 1000 for v in (title, channel)):
        return 'check_inconclusive', None, None
    clean = lambda v: ''.join(c for c in v if ord(c) >= 32)[:1000]
    return 'metadata_available', clean(title), clean(channel)


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(root):
    expected = {}
    for path in sorted((root / 'content').glob('*.json')):
        if path.is_symlink() or path.stat().st_size > 1_000_000:
            raise ValueError('Unsafe input record')
        record = json.loads(path.read_text())
        video = record.get('video_id')
        if video is not None:
            if not isinstance(video, str) or not VIDEO.fullmatch(video):
                raise ValueError('Invalid YouTube ID')
            expected[video] = record['title']
    if len(expected) > 100:
        raise ValueError('Unexpectedly many videos')
    opener = urllib.request.build_opener(NoRedirects())
    records = []
    for video, title in sorted(expected.items()):
        endpoint = 'https://www.youtube.com/oembed?' + urllib.parse.urlencode({'format': 'json', 'url': 'https://www.youtube.com/watch?v=' + video})
        item = {'video_id': video, 'expected_title': title, 'method': 'public YouTube oEmbed, metadata only',
                'endpoint': endpoint, 'checked_at': datetime.now(timezone.utc).isoformat()}
        try:
            request = urllib.request.Request(endpoint, headers={'User-Agent': 'Mozilla/5.0 archive reference verification'})
            with opener.open(request, timeout=20) as response:
                body = response.read(400001)
                if len(body) > 400000:
                    raise ValueError('Oversized metadata response')
                status = response.status
            outcome, actual_title, channel = classify(status, body)
            item.update(http_status=status, outcome=outcome, title=actual_title, channel=channel)
        except urllib.error.HTTPError as error:
            item.update(http_status=error.code, outcome='check_inconclusive', error='Provider metadata request rejected')
        except (OSError, ValueError) as error:
            item.update(outcome='check_inconclusive', error=type(error).__name__)
        records.append(item)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('video-checks.json'))
    args = parser.parse_args()
    result = check(args.root)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + '\n')
    print(json.dumps(result, ensure_ascii=True))
