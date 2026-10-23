#!/usr/bin/env python3
"""Compile a small, offline, unreviewed historical archive. Never fetch content."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PIL import Image

CONFIG_KEYS = {"site", "title", "canonical_base", "main_site", "status", "period_label"}
POST_KEYS = {"id", "type", "title", "slug", "date", "categories", "excerpt", "original_urls", "video_id", "thumbnail", "review_status", "provenance", "warnings"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PHOTO = re.compile(r"/wp-content/uploads/\d{4}/(?:0[1-9]|1[0-2])/[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:jpg|jpeg|png|webp)\Z")
VIDEO = re.compile(r"[A-Za-z0-9_-]{11}\Z")
RESERVED = {"archive", "category", "videos", "assets", "wp-content", "404", "index"}
REL = "nofollow noopener noreferrer"
# Hosts that served each site. Links to them become local routes, because the archive replaces them.
ALIASES = {"steveonjava": {"steveonjava.com", "www.steveonjava.com"},
           "nighthacking": {"nighthacking.tv", "www.nighthacking.tv", "nighthacking.com", "www.nighthacking.com"}}
LINK_STATES = {"live", "dead", "unverified"}
# Optional project-site prefix such as /steveonjava-com-archive. Empty means the site is served from a domain root.
BASE_PATH = re.compile(r"(?:/[a-z0-9]+(?:-[a-z0-9]+)*)?")
CSP = "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, name, maximum=20000):
    require(isinstance(value, str) and len(value) <= maximum, f"Invalid {name}")
    require(not any(ord(c) < 32 and c not in "\n\t\r" for c in value), f"Control character in {name}")
    return value


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path):
    require(path.is_file() and not path.is_symlink(), f"Missing or unsafe file: {path}")
    require(path.stat().st_size <= 1000000, f"Oversized JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: require(False, f"Invalid JSON constant: {value}"))


def safe_url(value, absolute=False):
    text(value, "URL", 4096)
    require(bool(value), "Empty URL")
    decoded = value
    for _ in range(4):
        decoded = unquote(decoded)
    require(not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in decoded), "Whitespace in URL")
    require(not any(c in decoded for c in "\\<>\"'"), "Unsafe URL character")
    require(not decoded.startswith("//"), "Protocol-relative URL")
    parsed = urlsplit(decoded)
    require(parsed.scheme in {"", "http", "https"}, "Unsafe URL scheme")
    require(not parsed.username and not parsed.password, "URL credentials are forbidden")
    require(not parsed.scheme or bool(parsed.netloc), "URL host is required")
    require(not absolute or parsed.scheme in {"http", "https"}, "Absolute HTTP URL required")
    require(not parsed.netloc or parsed.scheme in {"http", "https"}, "Invalid URL authority")
    require(not any(part in {".", ".."} for part in parsed.path.split("/")), "URL traversal")
    return value


def validate(root):
    require(root.is_dir() and not root.is_symlink(), "Root must be a real directory")
    for directory in [root / "content", root / "assets", root / "theme"]:
        if directory.exists():
            require(not directory.is_symlink(), f"Symlink: {directory}")
            for path in directory.rglob("*"):
                require(not path.is_symlink(), f"Symlink: {path}")
    config = load_json(root / "archive.json")
    require(isinstance(config, dict) and set(config) == CONFIG_KEYS, "Invalid archive.json keys")
    require(isinstance(config["site"], str) and config["site"] in {"steveonjava", "nighthacking"}, "Invalid site")
    host = "steveonjava.com" if config["site"] == "steveonjava" else "nighthacking.tv"
    require(config["canonical_base"] == f"https://{host}", "Unexpected canonical_base")
    require(config["main_site"] == "https://stephenchin.com", "Unexpected main_site")
    require(config["status"] == "prototype", "Only prototype builds are permitted")
    for key in ["title", "period_label"]:
        require(bool(text(config[key], key, 300).strip()), f"Empty {key}")
    # Optional owner-reviewed record of external link checks. Dead links render as plain text.
    dead = set()
    status_path = root / "link-status.json"
    if status_path.exists():
        status = load_json(status_path)
        require(isinstance(status, dict) and len(status) <= 1000, "Invalid link-status.json")
        for url, state in status.items():
            safe_url(url, absolute=True)
            require(state in LINK_STATES, "Invalid link state")
            if state == "dead":
                dead.add(url)
    config["dead_links"] = dead
    posts = []
    slugs, ids, category_names = set(), set(), {}
    content = root / "content"
    require(content.is_dir(), "Missing content directory")
    require(all(p.is_file() and p.suffix in {".json", ".md"} for p in content.iterdir()), "Unexpected content file")
    for path in sorted(content.glob("*.json")):
        p = load_json(path)
        require(isinstance(p, dict) and set(p) == POST_KEYS, f"Invalid post keys: {path.name}")
        require(type(p["id"]) is int and 0 < p["id"] <= 2147483647, "Invalid post ID")
        require(path.stem == str(p["id"]), "ID must match filename")
        require(p["id"] not in ids, "Duplicate post ID")
        ids.add(p["id"])
        require(p["type"] == "post" and p["review_status"] == "unreviewed", "Invalid post status or type")
        require(isinstance(p["slug"], str) and SLUG.fullmatch(p["slug"]) and p["slug"] not in RESERVED, "Invalid or reserved slug")
        require(p["slug"] not in slugs, "Duplicate slug")
        slugs.add(p["slug"])
        require(bool(text(p["title"], "title", 1000).strip()), "Empty title")
        text(p["excerpt"], "excerpt")
        require(isinstance(p["date"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", p["date"]), "Invalid date format")
        datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
        require(isinstance(p["categories"], list) and len(p["categories"]) <= 100, "Invalid categories")
        seen = set()
        for category in p["categories"]:
            require(isinstance(category, dict) and set(category) == {"slug", "name"}, "Invalid category")
            slug = category["slug"]
            require(isinstance(slug, str) and SLUG.fullmatch(slug), "Invalid category slug")
            require(slug not in seen, "Duplicate category")
            seen.add(slug)
            require(bool(text(category["name"], "category name", 300).strip()), "Empty category name")
            require(slug not in category_names or category_names[slug] == category["name"], "Conflicting category name")
            category_names[slug] = category["name"]
        require(isinstance(p["original_urls"], list) and bool(p["original_urls"]), "Original URLs are required")
        for url in p["original_urls"]:
            safe_url(url, absolute=True)
        require(p["video_id"] is None or isinstance(p["video_id"], str) and VIDEO.fullmatch(p["video_id"]), "Invalid YouTube ID")
        require(p["thumbnail"] is None or isinstance(p["thumbnail"], str) and PHOTO.fullmatch(p["thumbnail"]), "Invalid thumbnail")
        if p["thumbnail"]:
            require((root / "assets" / p["thumbnail"].lstrip("/")).is_file(), "Missing thumbnail")
        require(isinstance(p["provenance"], dict) and bool(p["provenance"]), "Provenance is required")
        require(isinstance(p["warnings"], list), "Invalid warnings")
        for warning in p["warnings"]:
            text(warning, "warning")
        md = path.with_suffix(".md")
        require(md.is_file() and md.stat().st_size <= 2000000, "Missing or oversized markdown")
        p["markdown"] = text(md.read_text(encoding="utf-8"), "markdown", 2000000)
        posts.append(p)
    require(bool(posts), "No historical records supplied. Add reviewed export inputs before building")
    require({p.stem for p in content.glob("*.md")} == {str(p["id"]) for p in posts}, "Orphan markdown file")
    return config, sorted(posts, key=lambda p: (p["date"], p["id"]), reverse=True)


def localize(url, config):
    safe_url(url)
    parsed = urlsplit(url)
    if parsed.hostname in ALIASES[config["site"]]:
        return (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "") + (f"#{parsed.fragment}" if parsed.fragment else "")
    return url


def local_target(url, current):
    parsed = urlsplit(url)
    if parsed.scheme:
        return None
    path = parsed.path
    if not path:
        return current
    require(path.startswith("/"), "Generated local URL must be root relative")
    return path


def render_markdown(source, config, routes, current, photos):
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    md.validateLink = lambda value: bool(safe_url(value))
    tokens = md.parse(source)
    # commonmark has no raw HTML renderer when html=False. URL checks run on
    # every parsed link, including links the upstream default would suppress.
    in_dead_link = False

    def rewrite(children):
        nonlocal in_dead_link
        for token in children:
            if token.type == "link_open":
                url = localize(token.attrGet("href"), config)
                if not urlsplit(url).scheme and not url.startswith(("/", "#", "?")):
                    url = "/" + url
                if url in config["dead_links"]:
                    # Constant markup only. The dead address is never emitted as an href. Link text stays as plain text.
                    token.type, token.tag, token.attrs, token.content = "html_inline", "", {}, '<span class="dead-link" title="The original link is no longer available">'
                    in_dead_link = True
                    continue
                token.attrSet("href", url)
                if urlsplit(url).scheme:
                    token.attrSet("rel", REL)
                elif local_target(url, current) not in routes and local_target(url, current) not in photos and not url.startswith(("#", "?p=")):
                    token.attrSet("data-unrecovered", "true")
                    token.attrSet("title", "Historical target is not included in this prototype")
            if token.type == "link_close" and in_dead_link:
                token.type, token.tag, token.attrs, token.content = "html_inline", "", {}, '</span><span class="dead-note"> (original link no longer available)</span>'
                in_dead_link = False
                continue
            if token.type == "image":
                url = localize(token.attrGet("src"), config)
                safe_url(url)
                alt = token.content.strip() or "Archived image"
                if url not in photos:
                    token.type = "text"
                    token.tag = ""
                    token.content = f"[Image not included in this prototype: {alt}]"
                    token.children = None
                    token.attrs = {}
                else:
                    token.attrSet("src", url)
                    token.attrSet("alt", alt)
                    token.attrSet("loading", "lazy")
                    if not token.content.strip():
                        child = Token("text", "", 0)
                        child.content = alt
                        token.children = [child]
                        token.content = alt
            if token.children:
                rewrite(token.children)
    rewrite(tokens)
    return md.renderer.render(tokens, md.options, {})


def anchor(url, label):
    external = bool(urlsplit(url).scheme)
    return f'<a href="{escape(url, quote=True)}"' + (f' rel="{REL}"' if external else '') + f'>{escape(label)}</a>'


def post_list(posts, night=False):
    cards = []
    for p in posts:
        image = f'<img src="{escape(p["thumbnail"], quote=True)}" alt="{escape(p["title"], quote=True)}" loading="lazy">' if p["thumbnail"] else '<span class="no-image">No approved thumbnail available</span>'
        cards.append(f'<li class="card">{image if night else ""}<h2>{anchor("/" + p["slug"] + "/", p["title"])}</h2><time datetime="{p["date"][:10]}">{p["date"][:10]}</time><p>{escape(p["excerpt"])}</p></li>')
    return '<ul class="video-grid" role="list">' + ''.join(cards) + '</ul>' if night else '<ul class="post-list" role="list">' + ''.join(cards) + '</ul>'


def rebase(html, base):
    """Prefix every root-relative href and src with the project path.

    The generator emits only double-quoted attributes, and every text node is escaped, so a literal
    href="/..." inside post text appears as href=&quot;/...&quot; and is never matched here.
    """
    if not base:
        return html
    return re.sub(r'(\b(?:href|src)=")/(?!/)', lambda match: match.group(1) + base + "/", html)


def page(config, title, body, route, sidebar):
    night = config["site"] == "nighthacking"
    wordmark = "NightHacking" if night else config["title"]
    nav = anchor("/", "Home") + anchor("/archive/", "Archive") + (anchor("/videos/", "Videos") if night else "")
    canonical = config["canonical_base"] + route
    header_note = "Video archive prototype" if night else "Prototype header treatment. Historical motorcycle photograph is not included."
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}">
<meta name="description" content="{escape(title + ' | Unreviewed archive prototype', quote=True)}"><title>{escape(title)} | {escape(config['title'])}</title>
<link rel="canonical" href="{escape(canonical, quote=True)}"><link rel="stylesheet" href="/assets/archive.css"><script src="/assets/legacy.js" defer></script></head>
<body class="{config['site']}"><a class="skip-link" href="#main">Skip to content</a><div class="site-shell">
<div class="prototype" role="note"><strong>Prototype / unreviewed archive</strong><p>Only the posts listed here are included. Historical links may point to material not yet recovered. Dates and source text have not been fully reviewed. {anchor(config['main_site'], 'Visit Stephen Chin’s current site')}</p></div>
<header class="masthead"><p class="wordmark">{escape(wordmark)}</p><p class="tagline">Technology Hacking and Community Building</p><p class="header-note">{header_note}</p></header>
<nav aria-label="Main navigation">{nav}</nav><p id="legacy-status" role="status"></p><noscript><p class="no-js">All listed posts are available without JavaScript. Old ?p=ID links need JavaScript to translate. Use {anchor('/archive/', 'the archive list')} instead.</p></noscript>
<div class="columns"><main id="main" tabindex="-1"><h1>{escape(title)}</h1>{body}</main><aside aria-label="Archive navigation">{sidebar}</aside></div>
<footer><p>{escape(config['period_label'])}. Archival source material is unreviewed. No comments, search, or contact forms are active.</p><p>{anchor(config['main_site'], 'Current work at stephenchin.com')}</p></footer></div></body></html>'''


def copy_photos(root, output):
    photos = set()
    source = root / "assets"
    if not source.exists():
        return photos
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        url = "/" + path.relative_to(source).as_posix()
        require(PHOTO.fullmatch(url), f"Unexpected asset: {url}")
        require(path.stat().st_size <= 20000000, "Oversized image")
        with Image.open(path) as image:
            require(image.format in {"JPEG", "PNG", "WEBP"}, "Only raster photographs are permitted")
            require(image.width * image.height <= 20000000 and not getattr(image, "is_animated", False), "Oversized or animated image")
            image.load()
            target = output / url.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            # Decode and reencode to drop EXIF, comments, and source metadata. Lossy formats keep
            # high quality, because the exporter already produced one lossy generation.
            clean = Image.new("RGB", image.size)
            clean.paste(image.convert("RGB"))
            fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[path.suffix.lower()]
            options = {"JPEG": {"quality": 95, "optimize": True}, "WEBP": {"quality": 95}, "PNG": {"optimize": True}}[fmt]
            clean.save(target, format=fmt, **options)
        photos.add(url)
    return photos


class Audit(HTMLParser):
    def __init__(self, output, route, base=""):
        super().__init__(convert_charrefs=True)
        self.output, self.route, self.base = output, route, base
        self.unrecovered = []
        self.has_notice = False
        self.has_csp = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        require(tag not in {"iframe", "object", "embed", "form", "base", "style"}, f"Forbidden HTML element: {tag}")
        require(not any(k.startswith("on") or k in {"style", "srcdoc", "srcset"} for k in attrs), "Active HTML attribute")
        if attrs.get("class") == "prototype":
            self.has_notice = True
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "content-security-policy":
            self.has_csp = attrs.get("content") == CSP
        if tag == "script":
            require(attrs.get("src") == self.base + "/assets/legacy.js", "Inline or unexpected script")
        for key in ["href", "src"]:
            if key not in attrs:
                continue
            url = attrs[key]
            safe_url(url)
            external = bool(urlsplit(url).scheme)
            if tag == "a" and external:
                require(set(REL.split()) <= set(attrs.get("rel", "").split()), "Unsafe external link")
            if key == "src" or tag == "link" and attrs.get("rel") == "stylesheet":
                require(not external, "Remote resource")
            if external or url.startswith("#"):
                continue
            if self.base and url.startswith("/"):
                require(url.startswith(self.base + "/"), f"Local URL outside base path on {self.route}: {url}")
                url = url[len(self.base):]
            target = local_target(url, self.route)
            path = self.output / target.lstrip("/")
            if target.endswith("/"):
                path /= "index.html"
            if attrs.get("data-unrecovered") == "true" and tag == "a":
                self.unrecovered.append(url)
            else:
                require(path.is_file(), f"Broken local link on {self.route}: {url}")


def check(output, base=""):
    require(isinstance(base, str) and BASE_PATH.fullmatch(base) is not None, "Invalid base path")
    stylesheet = (output / "assets/archive.css").read_text(encoding="utf-8")
    require(not re.search(r"url\s*\(|@import|expression\s*\(", stylesheet, re.I), "Unexpected CSS resource or active expression")
    unresolved = []
    for file in sorted(output.rglob("*.html")):
        route = "/" + file.relative_to(output).as_posix()
        if route.endswith("index.html"):
            route = route[:-10]
        audit = Audit(output, route, base)
        audit.feed(file.read_text(encoding="utf-8"))
        require(audit.has_notice and audit.has_csp, f"Missing prototype notice or CSP: {route}")
        unresolved.extend({"page": route, "target": url} for url in audit.unrecovered)
    require(bool(list(output.rglob("*.html"))), "No generated pages")
    return unresolved


def build(root, base=""):
    require(isinstance(base, str) and BASE_PATH.fullmatch(base) is not None, "Invalid base path")
    root = Path(root).absolute()
    config, posts = validate(root)
    output = root / "_site"
    require(not output.is_symlink(), "Output cannot be a symlink")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()
    photos = copy_photos(root, output)
    years, categories = defaultdict(list), defaultdict(list)
    for p in posts:
        years[p["date"][:4]].append(p)
        for c in p["categories"]:
            categories[c["slug"]].append(p)
    routes = {"/", "/archive/", "/404.html"} | {f'/{p["slug"]}/' for p in posts}
    routes |= {f"/archive/{year}/" for year in years} | {f"/category/{slug}/" for slug in categories}
    if config["site"] == "nighthacking":
        routes.add("/videos/")
    sidebar = '<h2>Archives</h2><ul>' + ''.join(f'<li>{anchor(f"/archive/{year}/", year)}</li>' for year in sorted(years, reverse=True)) + '</ul><h2>Categories</h2><ul>'
    names = {c["slug"]: c["name"] for p in posts for c in p["categories"]}
    sidebar += ''.join(f'<li>{anchor(f"/category/{slug}/", names[slug])}</li>' for slug in sorted(categories)) + '</ul>'
    night = config["site"] == "nighthacking"
    pages = {"/": (config["title"], '<p class="intro">A limited selection of recovered posts. This is not a complete restoration.</p>' + post_list(posts, night)),
             "/archive/": ("Archive by year", ''.join(f'<section><h2>{anchor(f"/archive/{year}/", year)}</h2>{post_list(years[year])}</section>' for year in sorted(years, reverse=True))),
             "/404.html": ("This page is not included", '<p>This prototype includes only the exported posts listed in the archive. The requested historical URL may not have been recovered. A missing page here does not establish that the original never existed.</p><p>' + anchor('/archive/', 'Browse the recovered archive') + ' or ' + anchor('/', 'return home') + '.</p>')}
    if night:
        pages["/videos/"] = ("Videos", '<p>Links are historical references. YouTube availability is unknown.</p>' + post_list([p for p in posts if p["video_id"]], True))
    for year, records in years.items():
        pages[f"/archive/{year}/"] = (year, post_list(records, night))
    for slug, records in categories.items():
        pages[f"/category/{slug}/"] = (names[slug], post_list(records, night))
    for p in posts:
        route = f'/{p["slug"]}/'
        body = f'<article><p class="post-meta"><time datetime="{p["date"][:10]}">{p["date"]}</time> · Unreviewed source transcription</p>'
        if p["video_id"]:
            thumbnail = f'<img src="{p["thumbnail"]}" alt="{escape(p["title"], quote=True)}">' if p["thumbnail"] else '<p>No approved local thumbnail is available.</p>'
            body += '<section class="player" aria-label="Historical video reference">' + thumbnail + '<p>' + anchor('https://www.youtube.com/watch?v=' + p["video_id"], 'Watch on YouTube') + '</p><p>Availability is unknown. Opening this link visits YouTube. No video is loaded on this page.</p></section>'
        body += render_markdown(p["markdown"], config, routes, route, photos)
        body += '<p>Categories: ' + ', '.join(anchor('/category/' + c['slug'] + '/', c['name']) for c in p['categories']) + '</p>'
        # Original addresses are plain text, never links. Several of those hosts now serve other content.
        # Provenance stays in content/<id>.json in the repository and is not rendered on the page.
        body += '<details><summary>Source and review notes</summary><p>Original address' + ('es' if len(p['original_urls']) > 1 else '') + ' (text only):</p><ul>' + ''.join('<li><code>' + escape(url) + '</code></li>' for url in p['original_urls']) + '</ul>' + ('<p>Recovery notes:</p><ul>' + ''.join('<li>' + escape(w) + '</li>' for w in p['warnings']) + '</ul>' if p['warnings'] else '') + '</details></article>'
        pages[route] = (p["title"], body)
    (output / "assets").mkdir(exist_ok=True)
    shutil.copyfile(root / "theme" / "archive.css", output / "assets" / "archive.css")
    script = (root / "theme" / "legacy.js").read_text(encoding="utf-8")
    require(script.count("__POST_MAP__") == 1 and script.count("__BASE_PATH__") == 1, "Invalid legacy script template")
    mapping = {str(p["id"]): '/' + p['slug'] + '/' for p in posts}
    script = script.replace("__POST_MAP__", json.dumps(mapping, sort_keys=True)).replace("__BASE_PATH__", json.dumps(base))
    (output / "assets" / "legacy.js").write_text(script, encoding="utf-8")
    for route, (title, body) in pages.items():
        target = output / route.lstrip("/")
        if route.endswith("/"):
            target /= "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rebase(page(config, title, body, route, sidebar), base), encoding="utf-8")
    unresolved = check(output, base)
    report = {"status": "prototype", "review_status": "unreviewed", "base_path": base, "posts": len(posts), "pages": len(pages), "photos": len(photos), "unrecovered_links": unresolved}
    (output / "build-report.json").write_text(json.dumps(report, indent=2) + '\n', encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--base-path", default="", help="project-site prefix such as /my-repo, empty for a domain root")
    args = parser.parse_args()
    try:
        if args.check_only:
            print(json.dumps({"unrecovered_links": check(args.root / "_site", args.base_path)}))
        else:
            build(args.root, args.base_path)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"Archive build rejected: {error}\n")
