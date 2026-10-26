"""Synthetic fixtures live only in temporary directories, never in the archive."""
import contextlib
from copy import deepcopy
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build
import check_videos
from PIL import Image, PngImagePlugin

TEMPLATE = Path(__file__).resolve().parents[1]


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="synthetic-archive-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(TEMPLATE / "theme", self.root / "theme")
        (self.root / "content").mkdir()
        self.config = {"site": "steveonjava", "title": "Synthetic archive test", "canonical_base": "https://steveonjava.com", "main_site": "https://stephenchin.com", "status": "prototype", "period_label": "Synthetic test period"}
        self.post = {"id": 1, "type": "post", "title": "Synthetic post one", "slug": "synthetic-one", "date": "2014-01-02 12:30:00", "categories": [{"slug": "testing", "name": "Synthetic category"}], "excerpt": "Synthetic fixture, not historical content.", "original_urls": ["http://steveonjava.com/?p=1"], "video_id": "Abcdef123_-", "thumbnail": "/wp-content/uploads/2014/01/synthetic.jpg", "review_status": "unreviewed", "provenance": {"kind": "synthetic test only"}, "warnings": ["Not historical content"]}
        photo = self.root / "assets/wp-content/uploads/2014/01/synthetic.jpg"
        photo.parent.mkdir(parents=True)
        Image.new("RGB", (32, 18), "navy").save(photo)
        self.markdown = "Synthetic **emphasis**. [External](https://example.com/path). [Missing](/not-exported/).\n\n![Synthetic photo](/wp-content/uploads/2014/01/synthetic.jpg)\n\n- List item\n\n```python\nprint('synthetic')\n```\n"
        self.save()

    def save(self):
        (self.root / "archive.json").write_text(json.dumps(self.config))
        (self.root / "content/1.json").write_text(json.dumps(self.post))
        (self.root / "content/1.md").write_text(self.markdown)

    def compile(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return build.build(self.root)

    def test_both_themes_routes_and_reports(self):
        for site, host in [("steveonjava", "steveonjava.com"), ("nighthacking", "nighthacking.tv")]:
            with self.subTest(site=site):
                self.config.update(site=site, canonical_base="https://" + host)
                self.save()
                result = self.compile()
                self.assertEqual(result["posts"], 1)
                self.assertEqual(result["photos"], 1)
                self.assertEqual(result["unrecovered_links"], [{"page": "/synthetic-one/", "target": "/not-exported/"}])
                for route in ["index.html", "archive/index.html", "archive/2014/index.html", "category/testing/index.html", "synthetic-one/index.html", "404.html"]:
                    self.assertTrue((self.root / "_site" / route).is_file())
                page = (self.root / "_site/synthetic-one/index.html").read_text()
                self.assertIn("Watch on YouTube", page)
                self.assertNotIn("Availability is unknown", page)
                self.assertNotIn("<iframe", page)
                self.assertIn('rel="nofollow noopener noreferrer"', page)
                self.assertIn("<strong>emphasis</strong>", page)
                if site == "nighthacking":
                    self.assertTrue((self.root / "_site/videos/index.html").is_file())
                build.check(self.root / "_site")

    def test_escaping_raw_html_and_metadata(self):
        self.post["title"] = '\"><img src=x onerror=alert(1)>'
        self.config["title"] = '<script>alert(1)</script>'
        self.markdown = '<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n'
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)

    def test_reject_dangerous_markdown_urls(self):
        for url in ["javascript:alert(1)", "data:text/html,evil", "//evil.example/a", "https://good.example/../secret", "https://user:pass@example.com/a", "%6aavascript:evil", "https://example.com/%2e%2e/secret"]:
            with self.subTest(url=url):
                self.markdown = "[attack](" + url + ")"
                self.save()
                with self.assertRaises(ValueError):
                    self.compile()

    def test_reject_unsafe_direct_urls(self):
        for url in ["javascript:evil", "data:text/html,evil", "//evil.example", "https://good.example\\evil", "https://a.example/%252e%252e/private", " https://example.com", "https://user:password@example.com"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                build.safe_url(url)

    def test_remote_images_are_never_loaded(self):
        self.markdown = "![Remote image](https://example.com/image.jpg)\n\n![Missing](/wp-content/uploads/2014/01/missing.jpg)"
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("Image not included", html)
        self.assertNotIn("image.jpg", html)
        self.assertEqual(len(json.loads((self.root / "build-report.json").read_text())["missing_images"]), 2)
        self.assertNotIn('src="https://', html)

    def test_image_alt_fallback(self):
        self.markdown = "![](/wp-content/uploads/2014/01/synthetic.jpg)"
        self.save()
        self.compile()
        self.assertIn('alt="Archived image"', (self.root / "_site/synthetic-one/index.html").read_text())

    def test_invalid_post_fields(self):
        cases = [("id", True), ("id", -1), ("id", 2), ("slug", "../evil"), ("slug", "archive"), ("slug", "bad/route"), ("date", "2014-02-30 00:00:00"), ("date", "yesterday"), ("review_status", "approved"), ("type", "attachment"), ("video_id", "evil"), ("thumbnail", "//example.com/pic.jpg"), ("original_urls", ["javascript:evil"]), ("categories", [{"slug": "../bad", "name": "Bad"}]), ("warnings", "wrong"), ("provenance", [])]
        original = deepcopy(self.post)
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.post = deepcopy(original)
                self.post[field] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.compile()

    def test_build_is_offline(self):
        from unittest.mock import patch
        with patch("socket.socket", side_effect=AssertionError("Network access is forbidden")):
            self.compile()

    def test_css_remote_import_rejected(self):
        path = self.root / "theme/archive.css"
        path.write_text(path.read_text() + '\n@import "https://example.com/evil.css";')
        with self.assertRaisesRegex(ValueError, "CSS resource"):
            self.compile()

    def test_duplicate_slug_rejected(self):
        second = deepcopy(self.post)
        second["id"] = 2
        (self.root / "content/2.json").write_text(json.dumps(second))
        (self.root / "content/2.md").write_text("Synthetic second fixture")
        with self.assertRaisesRegex(ValueError, "Duplicate slug"):
            self.compile()

    def test_missing_content_or_orphan_rejected(self):
        (self.root / "content/99.md").write_text("Synthetic orphan")
        with self.assertRaisesRegex(ValueError, "Orphan"):
            self.compile()
        (self.root / "content/99.md").unlink()
        (self.root / "content/1.md").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            self.compile()

    def test_duplicate_json_key_rejected(self):
        path = self.root / "archive.json"
        path.write_text(path.read_text()[:-1] + ', "site": "nighthacking"}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            self.compile()

    def test_config_contract(self):
        for key, value in [("main_site", "https://evil.example"), ("canonical_base", "https://wrong.example"), ("status", "published"), ("site", "other"), ("extra", True)]:
            original = deepcopy(self.config)
            self.config[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.compile()
            self.config = original

    def test_symlink_rejected(self):
        (self.root / "content/linked.md").symlink_to(self.root / "content/1.md")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.compile()

    def test_active_asset_rejected(self):
        (self.root / "assets/attack.svg").write_text('<svg onload="alert(1)"/>')
        with self.assertRaisesRegex(ValueError, "Unexpected asset"):
            self.compile()

    def test_audit_catches_tampered_local_links(self):
        self.compile()
        path = self.root / "_site/index.html"
        path.write_text(path.read_text().replace('href="/archive/"', 'href="/broken/"'))
        with self.assertRaisesRegex(ValueError, "Broken local link"):
            build.check(self.root / "_site")

    def test_same_domain_links_become_local(self):
        self.markdown = "[Known](http://www.steveonjava.com/synthetic-one/) [Unknown](https://steveonjava.com/not-exported/)"
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertIn('href="/synthetic-one/"', html)
        self.assertIn('href="/not-exported/" data-unrecovered="true"', html)

    def test_linked_full_size_photo_is_not_reported_unrecovered(self):
        full = self.root / "assets/wp-content/uploads/2014/01/full.jpg"
        Image.new("RGB", (64, 36), "teal").save(full)
        self.markdown = "[![Thumb](/wp-content/uploads/2014/01/synthetic.jpg)](/wp-content/uploads/2014/01/full.jpg) [Gone](/wp-content/uploads/2014/01/absent.jpg)"
        self.save()
        result = self.compile()
        self.assertEqual(result["unrecovered_links"], [{"page": "/synthetic-one/", "target": "/wp-content/uploads/2014/01/absent.jpg"}])

    def test_old_nighthacking_domain_links_become_local_and_never_live(self):
        self.config.update(site="nighthacking", canonical_base="https://nighthacking.tv")
        self.post["original_urls"] = ["http://nighthacking.tv/synthetic-one/", "http://nighthacking.com/synthetic-one/"]
        self.markdown = "[Old](http://nighthacking.com/synthetic-one/) and [Www](http://www.nighthacking.com/synthetic-one/)"
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("http://nighthacking.com", html.replace("<code>http://nighthacking.com/synthetic-one/</code>", ""))
        self.assertGreaterEqual(html.count('href="/synthetic-one/"'), 2)
        self.assertNotIn('href="http://nighthacking.tv', html)
        self.assertNotIn("<code>http://nighthacking.com/synthetic-one/</code>", html)

    def test_provenance_and_database_names_are_not_rendered(self):
        self.post["provenance"] = {"database": "synthetic_wordpress", "post_id": 1, "source_content_sha256": "a" * 64}
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("synthetic_wordpress", html)
        self.assertNotIn("a" * 64, html)
        self.assertNotIn("Source and review notes", html)

    def test_dead_external_link_renders_as_text_without_its_address(self):
        (self.root / "link-status.json").write_text(json.dumps({"https://dead.example/page": "dead", "https://live.example/page": "live"}))
        self.markdown = "[Gone](https://dead.example/page) and [Fine](https://live.example/page)"
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("dead.example", html)
        self.assertIn('class="dead-link"', html)
        self.assertNotIn("original link no longer available", html)
        self.assertNotIn('title="The original link', html)
        self.assertIn('href="https://live.example/page"', html)

    def test_link_status_rejects_bad_state_and_url(self):
        for bad in [{"https://x.example/": "maybe"}, {"javascript:alert(1)": "dead"}, ["not", "a", "dict"]]:
            (self.root / "link-status.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.compile()

    def test_project_base_path_prefixes_every_local_url(self):
        self.markdown = "[Missing](/not-exported/) [Gone](/wp-content/uploads/2014/01/absent.jpg) Text: href=\"/literal\"\n\n```\nsrc=\"/code\"\n```\n"
        self.save()
        with contextlib.redirect_stdout(io.StringIO()):
            report = build.build(self.root, "/my-repo")
        self.assertEqual(report["base_path"], "/my-repo")
        self.assertEqual(report["unrecovered_links"], [{"page": "/synthetic-one/", "target": "/not-exported/"}, {"page": "/synthetic-one/", "target": "/wp-content/uploads/2014/01/absent.jpg"}])
        pages = list((self.root / "_site").rglob("*.html"))
        self.assertGreater(len(pages), 5)
        for file in pages:
            html = file.read_text()
            for match in __import__("re").findall(r'\b(?:href|src)="(/[^"]*)"', html):
                self.assertTrue(match.startswith("/my-repo/"), f"{file.name}: {match}")
        post = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertIn('href="/my-repo/not-exported/"', post)
        self.assertIn("href=&quot;/literal&quot;", post)
        self.assertIn("src=&quot;/code&quot;", post)
        self.assertNotIn("/my-repo/literal", post)
        self.assertNotIn("/my-repo/code", post)
        script = (self.root / "_site/assets/legacy.js").read_text()
        self.assertIn('const base = "/my-repo";', script)
        self.assertNotIn("__BASE_PATH__", script)
        self.assertIn('src="/my-repo/assets/legacy.js"', post)
        build.check(self.root / "_site", "/my-repo")

    def test_audit_rejects_a_build_checked_against_the_wrong_base_path(self):
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(self.root, "/my-repo")
        for wrong in ["", "/other-repo"]:
            with self.assertRaises(ValueError):
                build.check(self.root / "_site", wrong)

    def test_domain_root_build_is_unchanged_by_the_base_path_option(self):
        self.compile()
        post = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertIn('href="/assets/archive.css"', post)
        self.assertIn('const base = "";', (self.root / "_site/assets/legacy.js").read_text())

    def test_cname_marker_selects_the_domain_root_build(self):
        self.assertIsNone(self.compile()["custom_domain"])
        (self.root / "CNAME").write_text("steveonjava.com\n")
        report = self.compile()
        self.assertEqual(report["custom_domain"], "steveonjava.com")
        self.assertIn('href="/assets/archive.css"', (self.root / "_site/index.html").read_text())
        self.assertIn('href="https://steveonjava.com/"', (self.root / "_site/index.html").read_text())
        self.assertFalse((self.root / "_site/CNAME").exists())
        with self.assertRaisesRegex(ValueError, "domain root"):
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(self.root, "/my-repo")

    def test_cname_marker_must_name_this_archives_own_domain(self):
        for content in ["nighthacking.tv\n", "steveonjava.com.evil.example\n", "www.steveonjava.com\n", "steveonjava.com\nextra.example\n", "", " steveonjava.com"]:
            with self.subTest(content=content):
                (self.root / "CNAME").write_text(content)
                with self.assertRaisesRegex(ValueError, "CNAME must name exactly"):
                    self.compile()
        (self.root / "CNAME").unlink()
        (self.root / "CNAME").symlink_to(self.root / "archive.json")
        with self.assertRaisesRegex(ValueError, "CNAME must be a regular file"):
            self.compile()

    def test_nighthacking_cname_names_nighthacking_tv(self):
        self.config.update(site="nighthacking", canonical_base="https://nighthacking.tv")
        self.save()
        (self.root / "CNAME").write_text("nighthacking.tv\n")
        self.assertEqual(self.compile()["custom_domain"], "nighthacking.tv")
        (self.root / "CNAME").write_text("steveonjava.com\n")
        with self.assertRaisesRegex(ValueError, "CNAME must name exactly"):
            self.compile()

    def test_workflows_switch_to_the_root_path_only_when_cname_exists(self):
        for name in ["build.yml", "pages.yml"]:
            with self.subTest(workflow=name):
                text = (TEMPLATE / ".github/workflows" / name).read_text()
                self.assertIn("if [ -f CNAME ]; then", text)
                self.assertIn('--base-path "$SERVED_PATH"', text)
                self.assertNotIn('--base-path "/${GITHUB_REPOSITORY#*/}"', text)
                self.assertIn("SERVED_PATH: ${{ steps.served.outputs.path }}", text)

    def test_invalid_base_paths_are_rejected(self):
        for bad in ["my-repo", "/My-Repo", "/a/b", "/x/", "//evil.example", '/a"b', "/a b", "/-x", "/x_y", "/"]:
            with self.subTest(base=bad), self.assertRaises(ValueError):
                with contextlib.redirect_stdout(io.StringIO()):
                    build.build(self.root, bad)

    def test_review_metadata_never_becomes_reader_text(self):
        banned = ["Only the posts listed here are included", "A limited selection of recovered posts",
                  "Archival source material is unreviewed", "Unreviewed source transcription",
                  "Video archive prototype", "Historical motorcycle photograph is not included",
                  "Availability is unknown", "Opening this link visits YouTube", "No video is loaded",
                  "Source and review notes", "No approved thumbnail", "Unreviewed archive prototype",
                  "Historical target is not included", "REVIEW-ONLY-MARKER"]
        self.post['warnings'] = ['REVIEW-ONLY-MARKER']
        self.post['provenance'] = {'note': 'REVIEW-ONLY-MARKER'}
        self.config['period_label'] = 'REVIEW-ONLY-MARKER'
        for site, host in [('steveonjava', 'steveonjava.com'), ('nighthacking', 'nighthacking.tv')]:
            self.config.update(site=site, canonical_base='https://' + host)
            self.save()
            self.compile()
            for path in (self.root / '_site').rglob('*.html'):
                html = path.read_text()
                for phrase in banned:
                    self.assertNotIn(phrase, html, (site, path, phrase))
                self.assertIn('name="robots" content="noindex,nofollow"', html)
                self.assertIn('Content-Security-Policy', html)
                self.assertIn('Current work at stephenchin.com', html)
        self.assertIn('REVIEW-ONLY-MARKER', (self.root / 'content/1.json').read_text())

    def test_exporter_notes_omitted_without_changing_author_prose_or_input(self):
        self.markdown = 'The author says this is a prototype.\n\n\\[Archive note: the original embedded player is not included in this static recovery.\\]\n\nThe author continues.\n'
        self.save()
        before = (self.root / 'content/1.md').read_bytes()
        self.compile()
        html = (self.root / '_site/synthetic-one/index.html').read_text()
        self.assertNotIn('Archive note:', html)
        self.assertIn('The author says this is a prototype.', html)
        self.assertIn('The author continues.', html)
        self.assertEqual(before, (self.root / 'content/1.md').read_bytes())

    def test_absent_thumbnails_leave_no_apology(self):
        self.config.update(site='nighthacking', canonical_base='https://nighthacking.tv')
        self.post['thumbnail'] = None
        self.save()
        self.compile()
        post = (self.root / '_site/synthetic-one/index.html').read_text()
        home = (self.root / '_site/index.html').read_text()
        self.assertIn('Watch on YouTube', post)
        self.assertIn('class="video-card"', home)
        self.assertNotIn('No approved', post + home)
        self.assertNotIn('no-image', post + home)
        self.assertNotIn('class="video-poster"', post)

    def test_theme_art_is_local_metadata_free_and_project_prefixed(self):
        for site, host in [('steveonjava', 'steveonjava.com'), ('nighthacking', 'nighthacking.tv')]:
            self.config.update(site=site, canonical_base='https://' + host)
            asset = build.THEME_IMAGES[site]
            path = self.root / 'assets' / asset.lstrip('/')
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (880, 200) if site == 'steveonjava' else (230, 28), 'navy').save(path)
            self.save()
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(self.root, '/my-repo')
            html = (self.root / '_site/index.html').read_text()
            self.assertIn('src="/my-repo' + asset + '"', html)
            with Image.open(self.root / '_site' / asset.lstrip('/')) as image:
                self.assertFalse(image.getexif())
            build.check(self.root / '_site', '/my-repo')

    def test_audit_requires_security_policy_and_robots_not_a_banner(self):
        self.compile()
        page = self.root / '_site/index.html'
        original = page.read_text()
        self.assertNotIn('class="prototype"', original)
        for text in ['<meta name="robots" content="noindex,nofollow">', 'Content-Security-Policy']:
            page.write_text(original.replace(text, ''))
            with self.assertRaisesRegex(ValueError, 'robots policy or CSP'):
                build.check(self.root / '_site')
        page.write_text(original.replace('<main', '<div class="prototype"></div><main', 1))
        with self.assertRaisesRegex(ValueError, 'prototype notice'):
            build.check(self.root / '_site')

    def test_internal_build_report_is_not_published(self):
        self.compile()
        self.assertTrue((self.root / 'build-report.json').is_file())
        self.assertFalse((self.root / '_site/build-report.json').exists())

    def test_video_metadata_check_is_not_a_playback_claim(self):
        response = json.dumps({'type': 'video', 'title': 'Synthetic title', 'author_name': 'Synthetic channel'})
        self.assertEqual(check_videos.classify(200, response), ('metadata_available', 'Synthetic title', 'Synthetic channel'))
        for status in [401, 403, 404, 410, 429, 500]:
            self.assertEqual(check_videos.classify(status, response)[0], 'check_inconclusive')

    def test_video_metadata_rejects_bad_provider_responses(self):
        for response in ['<html>challenge</html>', '[]', '{}', '{"type":"video", "title":{}, "author_name":"x"}']:
            self.assertEqual(check_videos.classify(200, response)[0], 'check_inconclusive')

    def test_video_id_validation_precedes_network(self):
        self.post['video_id'] = '../attack'
        self.save()
        from unittest.mock import patch
        with patch('urllib.request.build_opener', side_effect=AssertionError('No network setup before validation')):
            with self.assertRaisesRegex(ValueError, 'YouTube ID'):
                check_videos.check(self.root)

    def test_transparent_png_keeps_alpha_and_loses_metadata(self):
        source = self.root / "assets/wp-content/uploads/2014/01/clear-logo.png"
        logo = Image.new("RGBA", (40, 10), (255, 255, 255, 0))
        for x in range(10, 30):
            logo.putpixel((x, 5), (255, 255, 255, 255))
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Comment", "SOURCE-METADATA-MARKER")
        logo.save(source, pnginfo=meta)
        self.compile()
        built = self.root / "_site/wp-content/uploads/2014/01/clear-logo.png"
        self.assertNotIn(b"SOURCE-METADATA-MARKER", built.read_bytes())
        with Image.open(built) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getpixel((15, 5)), (255, 255, 255, 255))
            self.assertFalse(image.info.get("Comment"))

    def test_opaque_photo_stays_rgb(self):
        self.compile()
        with Image.open(self.root / "_site/wp-content/uploads/2014/01/synthetic.jpg") as image:
            self.assertEqual(image.mode, "RGB")

    def test_original_theme_structure(self):
        self.compile()
        html = (self.root / '_site/synthetic-one/index.html').read_text()
        self.assertIn('Steve On Java', html)
        self.assertIn('Hacking Java, JavaFX, and Flash with Agility', html)
        self.assertIn('class="header-scene"', html)
        self.assertIn('January 2, 2014', html)
        self.assertIn('class="post-taxonomy"', html)
        self.config.update(site='nighthacking', canonical_base='https://nighthacking.tv')
        self.save()
        self.compile()
        html = (self.root / '_site/synthetic-one/index.html').read_text()
        self.assertIn('class="video-stage"', html)
        self.assertIn('class="stage-inner"', html)
        self.assertIn('class="video-meta"', html)
        self.assertIn('Recent Videos', html)

    def add_posts(self, count):
        for number in range(2, count + 2):
            record = dict(self.post, id=number, slug=f"synthetic-{number}", title=f"Synthetic post {number}",
                          date=f"2014-01-{number:02d} 12:30:00", original_urls=[f"http://steveonjava.com/?p={number}"])
            (self.root / f"content/{number}.json").write_text(json.dumps(record))
            (self.root / f"content/{number}.md").write_text(f"Body number {number} with **emphasis**.\n")

    def add_art(self, *paths):
        for path in paths:
            target = self.root / "assets" / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA" if path.endswith(".png") else "RGB", (20, 20), "navy").save(target)

    def test_steveonjava_home_is_a_river_of_full_posts(self):
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        self.assertIn("<strong>emphasis</strong>", html)
        self.assertIn('class="post-taxonomy"', html)
        self.assertNotIn("Previous Entries", html)
        self.assertIn('class="page-title visually-hidden"', html)
        self.add_posts(11)
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        self.assertEqual(html.count('class="entry"'), build.HOME_POSTS)
        self.assertIn("Body number 12", html)
        self.assertNotIn("Synthetic post one", html)
        self.assertIn("\u00ab Previous Entries", html)
        self.assertTrue((self.root / "_site/archive/index.html").is_file())

    def test_unrecovered_links_are_reported_on_the_post_only(self):
        result = self.compile()
        self.assertEqual([item["page"] for item in result["unrecovered_links"]], ["/synthetic-one/"])

    def test_steveonjava_widgets_appear_only_with_supplied_art(self):
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        for heading in ["Steve On\u2026", "Archives", "Disclaimer"]:
            self.assertIn(f"<h2>{heading}</h2>", html)
        for heading in ["Publications", "Affiliations", "Awards", "Upcoming Talks"]:
            self.assertNotIn(f"<h2>{heading}</h2>", html)
        self.add_art(build.PUBLICATIONS[0][0], build.CHAMPIONS, build.AWARDS[1][0])
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        for heading in ["Publications", "Affiliations", "Awards"]:
            self.assertIn(f"<h2>{heading}</h2>", html)
        self.assertEqual(html.count("alt=\"Pro JavaFX Platform\""), 1)
        self.assertNotIn("Pro Android Flash", html)
        self.assertIn("2009 JavaOne Rock Star!", html)
        self.assertNotIn("DZone", html)
        self.assertIn('rel="nofollow noopener noreferrer"', html)

    def test_nighthacking_home_has_featured_stage_without_a_player(self):
        self.config.update(site="nighthacking", canonical_base="https://nighthacking.tv")
        self.save()
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        self.assertIn('class="home-stage"', html)
        self.assertIn('href="/synthetic-one/"', html.split('class="home-stage"')[1].split("</section>")[0])
        self.assertNotIn("<iframe", html)
        self.assertNotIn("youtube.com", html)
        self.assertNotIn("Older posts", html)
        self.post["thumbnail"] = None
        self.save()
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        self.assertNotIn('class="home-stage"', html)
        self.assertIn('class="video-grid"', html)

    def test_nighthacking_home_pager_points_at_the_videos_page(self):
        self.config.update(site="nighthacking", canonical_base="https://nighthacking.tv")
        self.save()
        self.add_posts(build.HOME_VIDEOS)
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        self.assertEqual(html.count('class="video-card"'), build.HOME_VIDEOS)
        self.assertIn('href="/videos/">\u2190 Older posts', html)

    def test_reencode_strips_exif(self):
        photo = self.root / "assets/wp-content/uploads/2014/01/synthetic.jpg"
        exif = Image.Exif()
        exif[315] = "Synthetic metadata"
        Image.new("RGB", (20, 10)).save(photo, exif=exif)
        self.compile()
        with Image.open(self.root / "_site/wp-content/uploads/2014/01/synthetic.jpg") as image:
            self.assertFalse(image.getexif())


    def write_record(self, record, markdown="Synthetic additional record.\n"):
        (self.root / f"content/{record['id']}.json").write_text(json.dumps(record), encoding="utf-8")
        (self.root / f"content/{record['id']}.md").write_text(markdown, encoding="utf-8")

    def static_record(self, number=2, slug="about", route=None):
        record = dict(deepcopy(self.post), id=number, type="page", slug=slug,
                      title=f"Synthetic static page {number}", video_id=None, thumbnail=None,
                      categories=[{"slug": "page-only-topic", "name": "Page-only topic"}],
                      original_urls=[f"http://steveonjava.com/?page_id={number}"])
        if route is not None:
            record["route"] = route
        return record

    def test_percent20_outbound_components_are_valid_without_fetching(self):
        for value in ["https://example.com/Sample%20File.pdf", "https://example.com/search?q=two%20words#some%20label"]:
            with self.subTest(value=value):
                self.assertEqual(build.safe_url(value, absolute=True), value)

    def test_percent20_does_not_relax_authority_local_route_or_controls(self):
        for value in ["/local%20asset.jpg", "http://exa%20mple.com/a", "http://user%20name@example.com/a", "https://example.com/path%2520file", "http://example.com/plain space", "https://example.com/search?q=x%09y", "https://example.com/a%20b%0d%0aHeader"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                build.safe_url(value)

    def test_percent20_links_keep_original_hrefs_and_unverified_state(self):
        self.markdown = "[Synthetic PDF](https://example.com/Sample%20File.pdf) and [Synthetic search](https://example.com/search?q=two%20words).\n"
        self.save()
        result = self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertIn('href="https://example.com/Sample%20File.pdf"', html)
        self.assertIn('href="https://example.com/search?q=two%20words"', html)
        self.assertIn("https://example.com/Sample%20File.pdf", result["unverified_external_urls"])

    def test_static_pages_are_discoverable_but_not_posts(self):
        for site, host in [("steveonjava", "steveonjava.com"), ("nighthacking", "nighthacking.tv")]:
            with self.subTest(site=site):
                self.config.update(site=site, canonical_base="https://" + host)
                self.save()
                record = self.static_record(route="/training/about/")
                self.write_record(record, "The original page wording stays **unchanged**.\n")
                result = self.compile()
                self.assertEqual(result["posts"], 1)
                self.assertEqual(result["static_pages"], 1)
                self.assertEqual(result["record_routes"]["2"], "/training/about/")
                page = (self.root / "_site/training/about/index.html").read_text()
                self.assertIn("wording stays <strong>unchanged</strong>", page)
                self.assertNotIn('class="video-stage"', page)
                self.assertNotIn('class="post-meta"', page)
                self.assertNotIn('class="post-taxonomy"', page)
                discovery = (self.root / "_site/pages/index.html").read_text()
                self.assertIn('href="/training/about/"', discovery)
                self.assertIn('href="/pages/" aria-current="page">Pages</a>', discovery)
                self.assertNotIn("/category/page-only-topic/", result["routes"])
                for path in ["index.html", "archive/index.html", "archive/2014/index.html", "category/testing/index.html"]:
                    html = (self.root / "_site" / path).read_text()
                    self.assertNotIn(record["title"], html)
                if site == "nighthacking":
                    self.assertNotIn(record["title"], (self.root / "_site/videos/index.html").read_text())

    def test_absent_pages_preserves_routes_and_plain_slug_behavior(self):
        result = self.compile()
        self.assertEqual(result["static_pages"], 0)
        self.assertNotIn("/pages/", result["routes"])
        self.assertEqual(result["record_routes"], {"1": "/synthetic-one/"})
        self.assertNotIn('href="/pages/"', (self.root / "_site/index.html").read_text())

    def test_static_pages_default_route_and_duplicate_leaf_names(self):
        self.write_record(self.static_record())
        self.write_record(self.static_record(3, route="/training/about/"))
        result = self.compile()
        self.assertEqual(result["record_routes"]["2"], "/about/")
        self.assertEqual(result["record_routes"]["3"], "/training/about/")

    def test_page_only_input_has_no_synthetic_post_lists(self):
        self.post = self.static_record(1)
        self.save()
        result = self.compile()
        self.assertEqual(result["posts"], 0)
        self.assertEqual(result["static_pages"], 1)
        self.assertNotIn("/archive/2014/", result["routes"])
        self.assertIn("/pages/", result["routes"])

    def test_page_routes_reject_reserved_and_unsafe_paths(self):
        bad_routes = ["/", "relative/", "//evil.example/a/", "/archive/2014/", "/category/topic/",
                      "/videos/page/2/", "/pages/page/2/", "/assets/thing/", "/wp-content/image/",
                      "/page/2/", "/404/", "/index/", "/a%c5%bf%c5%bfets/", "/a%c3%9fets/", "/valid", "/a//b/", "/a/../b/",
                      "/a/%2e%2e/b/", "/a/%2fb/", "/a/%252f/", "/a/%20b/", "/a/?x=1/",
                      "/a/#part/", "/a/\\b/", "/a/UPPER/", "/a/%ff/", "/a/%e3%80/", "/a/%/", "/a/" + "b" * 256 + "/"]
        for route in bad_routes:
            with self.subTest(route=route):
                self.write_record(self.static_record(route=route))
                with self.assertRaises(ValueError):
                    self.compile()
        self.write_record(dict(self.post, id=2, slug="post-two", route="/nested/post-two/"))
        with self.assertRaisesRegex(ValueError, "Only static pages"):
            self.compile()

    def test_static_route_collisions_are_rejected(self):
        for route in ["/synthetic-one/", "/training/about/"]:
            with self.subTest(route=route):
                self.write_record(self.static_record(route=route))
                self.write_record(self.static_record(3, route="/training/about/"))
                with self.assertRaisesRegex(ValueError, "collision"):
                    self.compile()

    def test_encoded_original_slugs_keep_uri_and_decode_filesystem(self):
        slugs = ["behind-the-scenes-the-making-of-pro-javafx%e2%84%a2-platform",
                 "live-video-streaming-guide-%e2%80%93-part-2-hardware",
                 "%e6%97%a5%e6%9c%ac%e8%aa%9e%e3%80%80%e8%a9%b1"]
        for slug in slugs:
            with self.subTest(slug=slug):
                self.post["slug"] = slug
                self.post["original_urls"] = ["http://steveonjava.com/" + slug + "/"]
                self.markdown = "[Self](http://steveonjava.com/" + slug + "/) [ID](?p=1)"
                self.save()
                with contextlib.redirect_stdout(io.StringIO()):
                    result = build.build(self.root, "/my-repo")
                route = "/" + slug + "/"
                self.assertEqual(result["record_routes"]["1"], route)
                self.assertIn(route, result["routes"])
                path = self.root / "_site" / build.decode_uri_path(route).lstrip("/") / "index.html"
                self.assertTrue(path.is_file())
                self.assertFalse((self.root / "_site" / slug).exists())
                html = path.read_text()
                self.assertIn('href="https://steveonjava.com' + route + '"', html)
                self.assertIn('href="/my-repo' + route + '"', html)
                self.assertIn(route, (self.root / "_site/assets/legacy.js").read_text())
                self.assertEqual(result["unrecovered_links"], [])
                build.check(self.root / "_site", "/my-repo")

    def test_encoded_unicode_nested_page_and_equivalent_link_case(self):
        record = self.static_record(slug="%e6%97%a5%e6%9c%ac", route="/training/%e6%97%a5%e6%9c%ac/")
        self.write_record(record)
        self.markdown = "[Page](http://steveonjava.com/training/%E6%97%A5%E6%9C%AC/)"
        self.save()
        result = self.compile()
        self.assertEqual(result["unrecovered_links"], [])
        self.assertIn('href="/training/%e6%97%a5%e6%9c%ac/"', (self.root / "_site/synthetic-one/index.html").read_text())

    def test_percent_variants_and_unicode_normalization_collide(self):
        pairs = [("%e6%97%a5", "%E6%97%A5"), ("caf%c3%a9", "cafe%cc%81")]
        for first, second in pairs:
            with self.subTest(first=first):
                self.post["slug"] = first
                self.post["original_urls"] = ["http://steveonjava.com/" + first + "/"]
                self.save()
                self.write_record(dict(self.post, id=2, slug=second))
                with self.assertRaisesRegex(ValueError, "collision"):
                    self.compile()

    def test_encoded_slugs_reject_ascii_escapes_and_malformed_utf8(self):
        for slug in ["hello%2fworld", "%61rchive", "%2e%2e", "%25e6%2597%25a5", "%00", "%7f",
                     "%09", "%20", "%5c", "%c0%af", "%ed%a0%80", "%f4%90%80%80", "%e6%97", "%zz",
                     "a%e2%80%8bb", "a%c2%a0b", "hello--world", "-hello", "hello-", "日本語"]:
            with self.subTest(slug=slug):
                self.post["slug"] = slug
                self.save()
                with self.assertRaises(ValueError):
                    self.compile()

    def test_ideographic_space_exception_is_route_scoped(self):
        route = "/%e6%97%a5%e3%80%80%e6%9c%ac/"
        for url in [route, "https://example.com" + route, "/other%e3%80%80/", route + "?q=%e3%80%80", route + "#%e3%80%80"]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    build.safe_url(url)
        self.assertEqual(build.safe_url(route, allowed_routes=[route]), route)
        for url in ["https://example.com" + route, "/other%e3%80%80/", route + "?q=%e3%80%80", route + "#%e3%80%80"]:
            with self.subTest(allowed_route=url), self.assertRaises(ValueError):
                build.safe_url(url, allowed_routes=[route], allowed_hosts={"steveonjava.com"})

    def test_audit_rejects_encoded_traversal_and_wrong_unicode_identity(self):
        self.compile()
        path = self.root / "_site/index.html"
        original = path.read_text()
        for target in ["/%2e%2e/", "/%252e%252e/", "/%2f/", "/%ff/", "/a%00b/", "/a%25b/"]:
            path.write_text(original.replace('href="/archive/"', 'href="' + target + '"'))
            with self.subTest(target=target), self.assertRaises(ValueError):
                build.check(self.root / "_site")
        path.write_text(original.replace('href="https://steveonjava.com/"', 'href="https://steveonjava.com/elsewhere/"'))
        with self.assertRaisesRegex(ValueError, "does not match"):
            build.check(self.root / "_site")

    def test_legacy_ids_resolve_posts_and_pages_and_report_unknowns_offline(self):
        self.write_record(self.static_record(route="/training/about/"))
        self.markdown = ("[Post](http://steveonjava.com/?p=1#part) [Page](?page_id=2) "
                         "[Absent](?page_id=999) [Duplicate](?p=1&p=1) [Mixed](?p=1&page_id=2) "
                         "[Invalid](?p=01) [Too big](?p=2147483648)")
        self.save()
        result = self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertIn('href="/synthetic-one/#part"', html)
        self.assertIn('href="/training/about/"', html)
        unknown = result["unknown_legacy_ids"]
        self.assertEqual(len(unknown), 5)
        self.assertEqual([item["reason"] for item in unknown].count("unknown"), 1)
        self.assertTrue(all(item["page"] == "/synthetic-one/" for item in unknown))
        self.assertEqual(len(result["unrecovered_links"]), 5)
        self.assertNotIn("unknown legacy", html.lower())

    def test_js_translator_uses_validated_nested_and_encoded_routes(self):
        if not shutil.which("node"):
            self.skipTest("Node is optional here; the Actions browser suite also exercises legacy IDs")
        self.write_record(self.static_record(route="/training/%e6%97%a5%e3%80%80%e6%9c%ac/"))
        self.compile()
        script = (self.root / "_site/assets/legacy.js").read_text()
        cases = [("?p=1", "/synthetic-one/"), ("?page_id=2", "/training/%e6%97%a5%e3%80%80%e6%9c%ac/")]
        cases += [(query, None) for query in ["?p=999", "?page_id=999", "?p=01", "?p=1&p=1", "?p=1&page_id=2", "?p=2147483648", "?p=__proto__", "?page_id=", "?p=https%3A%2F%2Fevil.example"]]
        for query, expected in cases:
            with self.subTest(query=query):
                setup = ('let result = null; const status = {textContent: ""}; '
                         'global.window = {location: {search: ' + json.dumps(query) + ', replace: value => {result = value;}}}; '
                         'global.document = {getElementById: () => status};\n')
                output = subprocess.run(["node", "-e", setup + script + '\nconsole.log(JSON.stringify({result, message: status.textContent}));'], check=True, text=True, capture_output=True)
                result = json.loads(output.stdout)
                self.assertEqual(result["result"], expected)
                if expected is None:
                    self.assertTrue(result["message"])

    def test_bulk_collections_are_bounded_complete_and_connected(self):
        self.config.update(site="nighthacking", canonical_base="https://nighthacking.tv")
        self.save()
        count = 2 * build.LIST_PAGE_SIZE + 3
        for number in range(2, count + 1):
            self.write_record(dict(self.post, id=number, slug=f"bulk-{number}", title=f"Bulk synthetic {number}"))
        page = self.static_record(count + 1)
        page["video_id"] = self.post["video_id"]
        self.write_record(page)
        result = self.compile()
        expected = {result["record_routes"][str(number)] for number in range(1, count + 1)}
        for start in ["/archive/", "/videos/", "/archive/2014/", "/category/testing/"]:
            pattern = re.escape(start) + r"(?:page/[1-9][0-9]*/)?"
            routes = [route for route in result["routes"] if re.fullmatch(pattern, route)]
            self.assertEqual(len(routes), 3)
            found = []
            for route in routes:
                html = build.output_path(self.root / "_site", route).read_text()
                cards = re.findall(r'<li class="card">.*?href="([^"]*)"', html, re.S)
                self.assertLessEqual(len(cards), build.LIST_PAGE_SIZE)
                found.extend(cards)
                self.assertNotIn(page["title"], html)
                self.assertIn('aria-label="Archive pages"', html)
            self.assertEqual(set(found), expected)
            self.assertEqual(len(found), count)
        home = (self.root / "_site/index.html").read_text()
        self.assertEqual(home.count('class="video-card"'), build.HOME_VIDEOS)
        self.assertEqual(result["pages"], len(result["routes"]))

    def test_static_page_discovery_is_paginated_without_loss(self):
        count = build.LIST_PAGE_SIZE + 2
        for number in range(2, count + 2):
            self.write_record(self.static_record(number, slug=f"page-{number}", route=f"/training/page-{number}/"))
        result = self.compile()
        self.assertIn("/pages/page/2/", result["routes"])
        found = []
        for route in ["/pages/", "/pages/page/2/"]:
            html = build.output_path(self.root / "_site", route).read_text()
            found.extend(re.findall(r'<li class="card">.*?href="([^"]*)"', html, re.S))
        self.assertEqual(len(found), count)
        self.assertEqual(len(set(found)), count)
        self.assertEqual(result["posts"], 1)

    def test_route_report_exactly_matches_generated_html(self):
        self.write_record(self.static_record(route="/training/about/"))
        result = self.compile()
        output = self.root / "_site"
        generated = {path.resolve() for path in output.rglob("*.html")}
        reported = {build.output_path(output, route).resolve() for route in result["routes"]}
        self.assertEqual(generated, reported)
        self.assertEqual(result["pages"], len(generated))
        self.assertEqual(set(result["record_routes"]), {"1", "2"})
        self.assertIn("/404.html", result["routes"])
        with self.assertRaisesRegex(ValueError, "coverage"):
            build.check(output, routes=set(result["routes"]) - {"/404.html"})
        self.assertEqual(json.loads((self.root / "build-report.json").read_text()), result)
        self.assertFalse((output / "build-report.json").exists())

    def test_dead_video_alias_suppresses_poster_watch_and_markdown_hrefs(self):
        video = self.post["video_id"]
        canonical = "https://www.youtube.com/watch?v=" + video
        for dead in [canonical, "https://youtu.be/" + video, "http://youtube.com/embed/" + video]:
            with self.subTest(dead=dead):
                (self.root / "link-status.json").write_text(json.dumps({dead: "dead", canonical: "dead" if dead == canonical else "live"}))
                self.markdown = "[Original video](" + canonical + ")"
                self.save()
                result = self.compile()
                for path in (self.root / "_site").rglob("*.html"):
                    self.assertNotIn('href="' + canonical + '"', path.read_text())
                html = (self.root / "_site/synthetic-one/index.html").read_text()
                self.assertIn("Watch on YouTube", html)
                self.assertIn("Original video", html)
                self.assertNotIn("unavailable", html.lower())
                self.assertNotIn(canonical, result["unverified_external_urls"])
                self.assertTrue(any(item["url"] == canonical and item["status"] == "dead" for item in result["external_links"]))

    def test_template_external_links_follow_dead_link_policy(self):
        self.add_art(build.PUBLICATIONS[0][0])
        dead = build.PUBLICATIONS[0][2]
        (self.root / "link-status.json").write_text(json.dumps({dead: "dead"}))
        self.compile()
        html = (self.root / "_site/index.html").read_text()
        self.assertNotIn('href="' + dead + '"', html)
        self.assertIn('alt="Pro JavaFX Platform"', html)

    def test_unverified_external_urls_reported_without_network_or_reader_notes(self):
        status = {"https://live.example/": "live", "https://pending.example/": "unverified", "https://dead.example/": "dead"}
        (self.root / "link-status.json").write_text(json.dumps(status))
        self.markdown = "[Live](https://live.example/) [Pending](https://pending.example/) [Unchecked](https://unchecked.example/) [Dead](https://dead.example/)"
        self.save()
        from unittest.mock import patch
        with patch("socket.socket", side_effect=AssertionError("Offline only")):
            result = self.compile()
        self.assertIn("https://pending.example/", result["unverified_external_urls"])
        self.assertIn("https://unchecked.example/", result["unverified_external_urls"])
        self.assertNotIn("https://live.example/", result["unverified_external_urls"])
        self.assertNotIn("https://dead.example/", result["unverified_external_urls"])
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("unverified", html.lower())
        self.assertNotIn("dead.example", html)

    def write_asset_manifests(self, theme_paths=()):
        rights, media, theme = [], [], []
        for path in sorted((self.root / "assets").rglob("*")):
            if not path.is_file():
                continue
            url = "/" + path.relative_to(self.root / "assets").as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rights.append({"path": url, "rights_holder": "Synthetic fixture", "status": "synthetic", "basis": "Synthetic pixels for unit tests only", "export_sha256": digest})
            item = {"path": url, "source_sha256": "a" * 64, "export_sha256": digest, "bytes": path.stat().st_size, "transformation": "Synthetic fixture only"}
            if url in theme_paths:
                item["site"] = self.config["site"]
                theme.append(item)
            else:
                media.append(item)
        (self.root / "rights.json").write_text(json.dumps(rights))
        (self.root / "recovery-manifest.json").write_text(json.dumps({"media": media}))
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs/theme-art.json").write_text(json.dumps(theme))
        return rights, media, theme

    def test_asset_rights_and_separate_theme_provenance_cover_all_actual_assets(self):
        art = build.THEME_IMAGES["steveonjava"]
        self.add_art(art, build.PUBLICATIONS[0][0])
        self.write_asset_manifests(theme_paths=[art, build.PUBLICATIONS[0][0]])
        result = self.compile()["asset_review"]
        self.assertEqual(result["assets"], 3)
        self.assertTrue(result["rights_checked"])
        self.assertTrue(result["image_provenance_checked"])
        self.assertEqual(result["lab_images"], 1)
        self.assertEqual(result["theme_images"], 2)

    def test_asset_registry_hash_duplicate_stale_and_missing_entries_fail(self):
        for case in ["hash", "duplicate", "stale", "missing"]:
            with self.subTest(case=case):
                rights, _, _ = self.write_asset_manifests()
                if case == "hash":
                    rights[0]["export_sha256"] = "0" * 64
                elif case == "duplicate":
                    rights.append(dict(rights[0]))
                elif case == "stale":
                    rights[0]["path"] = "/wp-content/uploads/2014/01/absent.jpg"
                else:
                    rights.clear()
                (self.root / "rights.json").write_text(json.dumps(rights))
                with self.assertRaises(ValueError):
                    self.compile()

    def test_provenance_coverage_includes_unused_images_and_reports_shared_evidence(self):
        unused = "/wp-content/uploads/2014/01/unused.png"
        self.add_art(unused)
        _, media, _ = self.write_asset_manifests()
        (self.root / "recovery-manifest.json").write_text(json.dumps({"media": media[:1]}))
        with self.assertRaisesRegex(ValueError, "provenance coverage"):
            self.compile()
        self.write_asset_manifests()
        (self.root / "docs/theme-art.json").write_text(json.dumps([media[0]]))
        # One verified raster may have two independent source-evidence records.
        result = build.validate_asset_records(self.root, self.config)
        self.assertEqual(result["shared_theme_lab_images"], [media[0]["path"]])

    def test_missing_asset_registries_are_not_misreported_as_clearance(self):
        result = self.compile()["asset_review"]
        self.assertFalse(result["rights_checked"])
        self.assertFalse(result["image_provenance_checked"])
        self.assertEqual(result["assets"], 1)

    def test_known_record_provenance_fields_are_checked_not_invented(self):
        for provenance in [{"post_id": 2}, {"post_id": True}, {"source_content_sha256": "bad"}]:
            with self.subTest(provenance=provenance):
                self.post["provenance"] = provenance
                self.save()
                with self.assertRaisesRegex(ValueError, "[Pp]rovenance"):
                    self.compile()


if __name__ == "__main__":
    unittest.main()
