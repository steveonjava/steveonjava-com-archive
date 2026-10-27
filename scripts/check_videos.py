#!/usr/bin/env python3
"""Plan video availability OFFLINE unless --online and an exact ID allowlist are supplied.

No player, cookies, captions or video bytes. Dated prior evidence stays separate
from the current outcome; metadata accessibility is not playback or reuse rights.
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
MAX_APPROVED_IDS = 100


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


def approved_ids(values):
    """Accept only an explicit JSON-style list of exact, unmodified IDs."""
    if not isinstance(values, (list, tuple)) or len(values) > MAX_APPROVED_IDS:
        raise ValueError('Approved IDs must be a list of at most 100 YouTube IDs')
    if any(not isinstance(value, str) or not VIDEO.fullmatch(value) for value in values):
        raise ValueError('Invalid approved YouTube ID')
    if len(set(values)) != len(values):
        raise ValueError('Duplicate approved YouTube ID')
    return set(values)


def prior_checks(evidence):
    """Keep supplied, dated checks only; never promote them to current evidence."""
    if evidence is None:
        return {}
    if not isinstance(evidence, list):
        raise ValueError('Prior evidence must be a JSON list')
    result = {}
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError('Invalid prior evidence record')
        video = item.get('video_id')
        if not isinstance(video, str) or not VIDEO.fullmatch(video):
            raise ValueError('Invalid prior evidence YouTube ID')
        candidates = item.get('prior_evidence', [])
        if not isinstance(candidates, list):
            raise ValueError('Invalid prior evidence list')
        if item.get('outcome') != 'not_checked':
            candidates = [item] + candidates
        for check in candidates:
            if not isinstance(check, dict) or check.get('video_id') != video:
                raise ValueError('Mismatched prior evidence ID')
            try:
                stamp = datetime.fromisoformat(check['checked_at'].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('Undated prior evidence')
            except (KeyError, AttributeError, TypeError, ValueError) as error:
                raise ValueError('Prior evidence needs a dated, timezone-aware checked_at') from error
            historical = {key: value for key, value in check.items() if key != 'prior_evidence'}
            bucket = result.setdefault(video, [])
            if historical not in bucket:
                bucket.append(historical)
    return result


def check(root, *, online=False, allowlist=(), max_requests=100, prior_evidence=None):
    """Return the complete inventory; construct no opener unless requests are approved.

    The request cap applies to the selected intersection, not the archive inventory.
    No supplied URL is ever fetched: the sole endpoint is constructed from a valid ID.
    """
    if type(max_requests) is not int or not 0 <= max_requests <= MAX_APPROVED_IDS:
        raise ValueError('max_requests must be an integer from 0 to 100')
    allowed = approved_ids(allowlist)
    historical = prior_checks(prior_evidence)
    expected = {}
    for path in sorted((root / 'content').glob('*.json')):
        if path.is_symlink() or path.stat().st_size > 1_000_000:
            raise ValueError('Unsafe input record')
        record = json.loads(path.read_text())
        video = record.get('video_id')
        if video is not None:
            if not isinstance(video, str) or not VIDEO.fullmatch(video):
                raise ValueError('Invalid YouTube ID')
            expected.setdefault(video, record['title'])
    selected = set(expected).intersection(allowed) if online else set()
    if len(selected) > max_requests:
        raise ValueError('Approved selection exceeds max_requests; no requests made')
    # Authorization boundary: even an empty online list must not construct an opener.
    opener = urllib.request.build_opener(NoRedirects()) if selected else None
    records = []
    for video, title in sorted(expected.items()):
        item = {'video_id': video, 'expected_title': title, 'outcome': 'not_checked',
                'method': 'offline inventory; no request made',
                'prior_evidence': historical.get(video, [])}
        if video not in selected:
            if online:
                item['method'] = 'not selected by explicit approved-ID allowlist; no request made'
            records.append(item)
            continue
        endpoint = 'https://www.youtube.com/oembed?' + urllib.parse.urlencode({
            'format': 'json', 'url': 'https://www.youtube.com/watch?v=' + video})
        item.update(method='public YouTube oEmbed, metadata only', endpoint=endpoint,
                    checked_at=datetime.now(timezone.utc).isoformat())
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('video-availability.json'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--online', action='store_true', help='Requires --approved-ids; never used by normal CI')
    mode.add_argument('--offline', action='store_true', help='Default: inventory only, without constructing an opener')
    parser.add_argument('--approved-ids', type=Path, help='JSON list of exact owner-approved 11-character YouTube IDs')
    parser.add_argument('--max-requests', type=int, default=100)
    parser.add_argument('--prior-evidence', type=Path, help='Optional local JSON evidence; never fetched or assumed')
    args = parser.parse_args()
    try:
        allowed = json.loads(args.approved_ids.read_text()) if args.approved_ids else []
        prior = json.loads(args.prior_evidence.read_text()) if args.prior_evidence else None
        result = check(args.root, online=args.online, allowlist=allowed,
                       max_requests=args.max_requests, prior_evidence=prior)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + '\n')
    print(json.dumps({'mode': 'online-allowlisted' if args.online else 'offline',
                      'videos': len(result), 'requests': sum(item['outcome'] != 'not_checked' for item in result)}))


if __name__ == '__main__':
    main()
