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
from PIL import Image

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
                self.assertIn("Availability is unknown", page)
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
        self.assertIn("Image not included in this prototype: Remote image", html)
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
        self.assertEqual(html.count('href="/synthetic-one/"'), 2)  # the two markdown links only
        self.assertNotIn('href="http://nighthacking.tv', html)
        self.assertIn("<code>http://nighthacking.com/synthetic-one/</code>", html)

    def test_provenance_and_database_names_are_not_rendered(self):
        self.post["provenance"] = {"database": "synthetic_wordpress", "post_id": 1, "source_content_sha256": "a" * 64}
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("synthetic_wordpress", html)
        self.assertNotIn("a" * 64, html)
        self.assertIn("Source and review notes", html)

    def test_dead_external_link_renders_as_text_without_its_address(self):
        (self.root / "link-status.json").write_text(json.dumps({"https://dead.example/page": "dead", "https://live.example/page": "live"}))
        self.markdown = "[Gone](https://dead.example/page) and [Fine](https://live.example/page)"
        self.save()
        self.compile()
        html = (self.root / "_site/synthetic-one/index.html").read_text()
        self.assertNotIn("dead.example", html)
        self.assertIn('class="dead-link"', html)
        self.assertIn("original link no longer available", html)
        self.assertIn('href="https://live.example/page"', html)

    def test_link_status_rejects_bad_state_and_url(self):
        for bad in [{"https://x.example/": "maybe"}, {"javascript:alert(1)": "dead"}, ["not", "a", "dict"]]:
            (self.root / "link-status.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.compile()

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
