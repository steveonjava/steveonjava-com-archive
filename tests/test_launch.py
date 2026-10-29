"""Launch status: indexable pages, robots.txt and sitemap.xml.

PureLaunchTests touch only helper functions and temporary files. LaunchBuildTests compile synthetic archives, so they run in CI.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build

NS = "{" + build.SITEMAP_NS + "}"
BASE = "https://example.test"
ROBOTS_META_LAUNCHED = '<meta name="robots" content="index,follow">'
ROBOTS_META_PROTOTYPE = '<meta name="robots" content="noindex,nofollow">'


def locations(xml):
    return [node.text for node in ElementTree.fromstring(xml.encode("utf-8")).iter(NS + "loc")]


class PureLaunchTests(unittest.TestCase):
    def folder(self, robots=None, sitemap=None):
        tmp = tempfile.TemporaryDirectory(prefix="synthetic-launch-")
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        (out / "robots.txt").write_text(build.robots_txt(BASE) if robots is None else robots, encoding="utf-8")
        (out / "sitemap.xml").write_text(build.sitemap_xml(BASE, ["/", "/a/", "/404.html"]) if sitemap is None else sitemap, encoding="utf-8")
        return out

    urls = [BASE + "/", BASE + "/a/", BASE + "/404.html"]

    def test_robots_txt_allows_everything_and_names_the_sitemap(self):
        self.assertEqual(build.robots_txt(BASE), "User-agent: *\nAllow: /\n\nSitemap: https://example.test/sitemap.xml\n")

    def test_sitemap_lists_every_page_except_404_sorted_and_escaped(self):
        xml = build.sitemap_xml(BASE, ["/", "/404.html", "/b/", "/a%e2%84%a2/", "/x&y/"])
        self.assertEqual(locations(xml), [BASE + "/", BASE + "/a%e2%84%a2/", BASE + "/b/", BASE + "/x&y/"])
        self.assertIn("/x&amp;y/", xml)
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="' + build.SITEMAP_NS + '">\n'))
        self.assertNotIn("404", xml)

    def test_sitemap_refuses_an_empty_or_oversized_list(self):
        with self.assertRaises(ValueError):
            build.sitemap_xml(BASE, ["/404.html"])
        with mock.patch.object(build, "MAX_SITEMAP_URLS", 2), self.assertRaises(ValueError):
            build.sitemap_xml(BASE, ["/", "/a/", "/b/"])

    def test_matching_files_pass(self):
        build.check_launch_files(self.folder(), self.urls, "launched")

    def test_a_prototype_build_must_publish_neither_file(self):
        with self.assertRaisesRegex(ValueError, "prototype build"):
            build.check_launch_files(self.folder(), self.urls, "prototype")
        empty = tempfile.TemporaryDirectory(prefix="synthetic-launch-")
        self.addCleanup(empty.cleanup)
        build.check_launch_files(Path(empty.name), self.urls, "prototype")

    def test_missing_files_fail(self):
        for name in ("robots.txt", "sitemap.xml"):
            with self.subTest(name=name):
                out = self.folder()
                (out / name).unlink()
                with self.assertRaisesRegex(ValueError, "Missing " + name):
                    build.check_launch_files(out, self.urls, "launched")

    def test_a_symlinked_file_fails(self):
        out = self.folder()
        (out / "robots.txt").unlink()
        (out / "robots.txt").symlink_to(out / "sitemap.xml")
        with self.assertRaisesRegex(ValueError, "Missing robots.txt"):
            build.check_launch_files(out, self.urls, "launched")

    def test_a_wrong_robots_txt_fails(self):
        for text in ("User-agent: *\nDisallow: /\n", build.robots_txt(BASE) + "Disallow: /a/\n", build.robots_txt("https://other.test")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "Unexpected robots.txt"):
                    build.check_launch_files(self.folder(robots=text), self.urls, "launched")

    def test_a_sitemap_that_differs_from_the_pages_fails(self):
        cases = {"missing page": build.sitemap_xml(BASE, ["/"]),
                 "extra page": build.sitemap_xml(BASE, ["/", "/a/", "/b/"]),
                 "404 listed": build.sitemap_xml(BASE, ["/", "/a/"]).replace("</urlset>", "<url><loc>" + BASE + "/404.html</loc></url>\n</urlset>"),
                 "duplicate": build.sitemap_xml(BASE, ["/", "/a/"]).replace("</urlset>", "<url><loc>" + BASE + "/a/</loc></url>\n</urlset>"),
                 "other origin": build.sitemap_xml("https://other.test", ["/", "/a/"])}
        for label, sitemap in cases.items():
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "does not list exactly"):
                build.check_launch_files(self.folder(sitemap=sitemap), self.urls, "launched")

    def test_a_malformed_sitemap_or_root_fails(self):
        with self.assertRaisesRegex(ValueError, "Invalid sitemap.xml"):
            build.check_launch_files(self.folder(sitemap="<urlset><url>"), self.urls, "launched")
        with self.assertRaisesRegex(ValueError, "Invalid sitemap root"):
            build.check_launch_files(self.folder(sitemap='<?xml version="1.0"?><other xmlns="' + build.SITEMAP_NS + '"/>'), self.urls, "launched")

    def test_pages_on_two_origins_fail(self):
        with self.assertRaisesRegex(ValueError, "one origin"):
            build.check_launch_files(self.folder(), self.urls + ["https://other.test/"], "launched")


class LaunchBuildTests(unittest.TestCase):
    """Reuse the synthetic archive fixture of test_build. These compile sites, so they run in GitHub Actions."""

    def setUp(self):
        import test_build
        self.fx = test_build.ArchiveTests("setUp")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.out = self.fx.root / "_site"

    def launch(self, site="steveonjava", host="steveonjava.com"):
        self.fx.config.update(site=site, canonical_base="https://" + host, status="launched")
        self.fx.save()
        return self.fx.compile()

    def test_prototype_status_is_still_noindex_without_robots_or_sitemap(self):
        result = self.fx.compile()
        self.assertEqual(result["status"], "prototype")
        pages = list(self.out.rglob("*.html"))
        self.assertTrue(pages)
        for path in pages:
            self.assertIn(ROBOTS_META_PROTOTYPE, path.read_text(encoding="utf-8"))
        self.assertFalse((self.out / "robots.txt").exists())
        self.assertFalse((self.out / "sitemap.xml").exists())

    def test_launched_pages_are_indexable_with_robots_txt_and_a_matching_sitemap(self):
        for site, host in [("steveonjava", "steveonjava.com"), ("nighthacking", "nighthacking.tv")]:
            with self.subTest(site=site):
                result = self.launch(site, host)
                self.assertEqual(result["status"], "launched")
                pages = list(self.out.rglob("*.html"))
                self.assertTrue(pages)
                for path in pages:
                    html = path.read_text(encoding="utf-8")
                    self.assertIn(ROBOTS_META_LAUNCHED, html)
                    self.assertNotIn("noindex", html)
                base = "https://" + host
                self.assertEqual((self.out / "robots.txt").read_text(encoding="utf-8"), build.robots_txt(base))
                expected = sorted(base + route for route in result["routes"] if route != "/404.html")
                self.assertEqual(sorted(locations((self.out / "sitemap.xml").read_text(encoding="utf-8"))), expected)
                self.assertIn(base + "/synthetic-one/", expected)
                build.check(self.out, status="launched")

    def test_the_audit_enforces_the_status_it_is_given(self):
        self.launch()
        with self.assertRaisesRegex(ValueError, "robots policy or CSP"):
            build.check(self.out)
        (self.out / "sitemap.xml").unlink()
        with self.assertRaisesRegex(ValueError, "Missing sitemap.xml"):
            build.check(self.out, status="launched")

    def test_a_prototype_audit_rejects_published_robots_and_sitemap(self):
        self.fx.compile()
        (self.out / "robots.txt").write_text(build.robots_txt("https://steveonjava.com"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prototype build"):
            build.check(self.out)

    def test_an_unknown_status_is_rejected_by_the_config_and_the_audit(self):
        self.fx.compile()
        with self.assertRaisesRegex(ValueError, "Unexpected status"):
            build.check(self.out, status="published")
        self.fx.config["status"] = "published"
        self.fx.save()
        with self.assertRaisesRegex(ValueError, "Unexpected status"):
            self.fx.compile()


if __name__ == "__main__":
    unittest.main()
