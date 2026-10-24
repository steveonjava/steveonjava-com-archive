"""Synthetic fixtures live only in temporary directories, never in the archive."""
import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
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
        cases = [("id", True), ("id", -1), ("id", 2), ("slug", "../evil"), ("slug", "archive"), ("slug", "bad/route"), ("date", "2014-02-30 00:00:00"), ("date", "yesterday"), ("review_status", "approved"), ("type", "page"), ("video_id", "evil"), ("thumbnail", "//example.com/pic.jpg"), ("original_urls", ["javascript:evil"]), ("categories", [{"slug": "../bad", "name": "Bad"}]), ("warnings", "wrong"), ("provenance", [])]
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


if __name__ == "__main__":
    unittest.main()
