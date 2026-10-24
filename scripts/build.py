#!/usr/bin/env python3
"""Compile a historical archive from local inert records. Never fetch content."""
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
THEME_IMAGES = {"steveonjava": "/wp-content/uploads/2010/03/racer3.1.jpg",
                "nighthacking": "/wp-content/uploads/2013/10/NightHacking-Header.png"}
# Home pages show the newest entries, as the originals did. Older material stays one click away in the archive.
HOME_POSTS = 10
HOME_VIDEOS = 15
# Sidebar art of the original SteveOnJava theme. Each widget appears only when its image was supplied.
PUBLICATIONS = [("/wp-content/uploads/2009/06/cover-100.jpg", "Pro JavaFX Platform", "https://www.apress.com/9781430218753"),
                ("/wp-content/uploads/2011/03/proandroidflash-100.jpg", "Pro Android Flash", "https://www.oreilly.com/library/view/pro-android-flash/9781430232315/")]
CHAMPIONS = "/wp-content/uploads/2010/07/Java_Champions_Transparent.png"
AWARDS = [("/wp-content/uploads/2011/08/big-mvbbutton1.png", "DZone Most Valuable Blogger", 150, 68),
          ("/wp-content/uploads/2009/07/rockstar_dukewithguitar_small.png", "Duke playing an electric guitar", 150, 128)]
DISCLAIMER = "Views and opinions expressed here are all my fault... complain to me, not my employer. :)"
# These exact standalone lines were written by the exporter, not the author.
EXPORT_NOTICES = {"[Archive note: the original embedded player is not included in this static recovery.]",
                  "[Archive note: this image was not recovered.]"}
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
    config["missing_images"] = []
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
    source = "".join(line for line in source.splitlines(keepends=True)
                     if line.strip().replace("\\[", "[").replace("\\]", "]") not in EXPORT_NOTICES)
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
                    token.type, token.tag, token.attrs, token.content = "html_inline", "", {}, '<span class="dead-link">'
                    in_dead_link = True
                    continue
                token.attrSet("href", url)
                if urlsplit(url).scheme:
                    token.attrSet("rel", REL)
                elif local_target(url, current) not in routes and local_target(url, current) not in photos and not url.startswith(("#", "?p=")):
                    token.attrSet("data-unrecovered", "true")
            if token.type == "link_close" and in_dead_link:
                token.type, token.tag, token.attrs, token.content = "html_inline", "", {}, '</span>'
                in_dead_link = False
                continue
            if token.type == "image":
                url = localize(token.attrGet("src"), config)
                safe_url(url)
                alt = token.content.strip() or "Archived image"
                if url not in photos:
                    token.type = "text"
                    token.tag = ""
                    config["missing_images"].append({"page": current, "target": url, "alt": alt})
                    token.content = ""
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


def readable_date(value):
    date = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return f"{date:%B} {date.day}, {date.year}"


def post_meta(post):
    return f'<p class="post-meta">steveonjava | <time datetime="{post["date"][:10]}">{readable_date(post["date"])}</time></p>'


def taxonomy(post):
    links = ', '.join(anchor('/category/' + c['slug'] + '/', c['name']) for c in post['categories'])
    return '<dl class="post-taxonomy"><dt>Categories</dt><dd>' + links + '</dd></dl>' if links else ''


def post_list(posts, night=False):
    cards = []
    for post in posts:
        route = '/' + post['slug'] + '/'
        if night:
            image = f'<img src="{escape(post["thumbnail"], quote=True)}" alt="" loading="lazy">' if post['thumbnail'] else ''
            cards.append(f'<li class="card"><a class="video-card" href="{route}">{image}<h2>{escape(post["title"])}</h2></a></li>')
        else:
            cards.append(f'<li class="card"><h2>{anchor(route, post["title"])}</h2>{post_meta(post)}<p class="excerpt">{escape(post["excerpt"])}</p></li>')
    cls = 'video-grid' if night else 'post-list'
    return f'<ul class="{cls}" role="list">' + ''.join(cards) + '</ul>'


def video_reference(post):
    image = f'<img src="{escape(post["thumbnail"], quote=True)}" alt="{escape(post["title"], quote=True)}">' if post['thumbnail'] else ''
    url = 'https://www.youtube.com/watch?v=' + post['video_id']
    poster = f'<a class="video-poster" href="{url}" rel="{REL}" aria-label="{escape(post["title"], quote=True)}">{image}</a>' if image else ''
    return '<div class="player">' + poster + '<p class="watch-link">' + anchor(url, 'Watch on YouTube') + '</p></div>'


def entry_html(post, content):
    route = '/' + post['slug'] + '/'
    video = video_reference(post) if post['video_id'] else ''
    return ('<article class="entry"><h2 class="entry-title">' + anchor(route, post['title']) + '</h2>' + post_meta(post) + video
            + '<div class="entry-content">' + content + '</div>' + taxonomy(post) + '</article>')


def pager(url, label):
    return '<nav class="pager" aria-label="More posts">' + anchor(url, label) + '</nav>'


def home_stage(post):
    """Featured player area. It links to the local page and never embeds or contacts a player."""
    label = escape(post['title'], quote=True)
    return ('<div class="home-player"><a class="video-poster" href="/' + post['slug'] + '/" aria-label="Watch ' + label + '">'
            '<img src="' + escape(post['thumbnail'], quote=True) + '" alt="">'
            '<span class="stage-title">' + escape(post['title']) + '</span><span class="play-button" aria-hidden="true"></span></a></div>')


def home_page(posts, rendered, night):
    if night:
        hero = next((p for p in posts if p['video_id'] and p['thumbnail']), None)
        more = pager('/videos/', '\u2190 Older posts') if len(posts) > HOME_VIDEOS else ''
        return ('Latest Videos', post_list(posts[:HOME_VIDEOS], True) + more, 'home' if hero else 'gallery', home_stage(hero) if hero else '', '')
    more = pager('/archive/', '\u00ab Previous Entries') if len(posts) > HOME_POSTS else ''
    return ('Latest Posts', ''.join(entry_html(p, rendered[p['id']]) for p in posts[:HOME_POSTS]) + more, 'home', '', '')


def widget_image(photos, path, alt, width, height, href=None):
    if path not in photos:
        return ''
    image = f'<img src="{path}" alt="{escape(alt, quote=True)}" width="{width}" height="{height}" loading="lazy">'
    return f'<a href="{escape(href, quote=True)}" rel="{REL}">{image}</a>' if href else image


def steveonjava_sidebar(year_links, categories, names, photos):
    covers = ''.join(widget_image(photos, path, alt, 75, 99, href) for path, alt, href in PUBLICATIONS)
    html = '<h2>Publications</h2><p class="widget-covers">' + covers + '</p>' if covers else ''
    topics = ''.join(f'<li>{anchor(f"/category/{slug}/", names[slug])}</li>' for slug in sorted(categories, key=lambda slug: names[slug].lower()))
    html += '<h2>Steve On\u2026</h2><ul><li>' + anchor('/archive/', 'Everything') + '</li>' + topics + '</ul><h2>Archives</h2><ul>' + year_links + '</ul>'
    affiliation = widget_image(photos, CHAMPIONS, 'Java Champions', 160, 68)
    if affiliation:
        html += '<h2>Affiliations</h2><p class="widget-art">' + affiliation + '</p>'
    badges = ''.join('<p class="widget-art">' + widget_image(photos, path, alt, w, h) + '</p>' for path, alt, w, h in AWARDS if path in photos)
    if badges:
        html += '<h2>Awards</h2>' + badges + ('<p>2009 JavaOne Rock Star!</p>' if AWARDS[1][0] in photos else '')
    return html + '<h2>Disclaimer</h2><p>' + escape(DISCLAIMER) + '</p>'


def rebase(html, base):
    """Prefix every root-relative href and src with the project path.

    The generator emits only double-quoted attributes, and every text node is escaped, so a literal
    href="/..." inside post text appears as href=&quot;/...&quot; and is never matched here.
    """
    if not base:
        return html
    return re.sub(r'(\b(?:href|src)=")/(?!/)', lambda match: match.group(1) + base + "/", html)


def page(config, title, body, route, sidebar, layout="index", video="", meta=""):
    night = config["site"] == "nighthacking"
    nav_items = [("/", "Watch" if night else "Home"), ("/archive/", "Archive")]
    if night:
        nav_items.append(("/videos/", "Videos"))
    nav = ''.join(f'<a href="{url}"' + (' aria-current="page"' if route == url else '') + f'>{label}</a>' for url, label in nav_items)
    nav = '<nav class="site-nav" aria-label="Main navigation">' + nav + '</nav>'
    theme_image = config.get("theme_image")
    if night:
        logo = f'<img class="site-logo" src="{theme_image}" alt="NightHacking" width="230" height="28">' if theme_image else 'NightHacking'
        header = '<header class="masthead"><div class="masthead-inner"><a class="wordmark" href="/">' + logo + '</a>' + nav + '</div></header>'
    else:
        header = '<header class="masthead"><a class="wordmark" href="/">Steve On Java</a><p class="tagline">Hacking Java, JavaFX, and Flash with Agility</p><a class="header-current" href="' + config['main_site'] + f'" rel="{REL}">Stephen Chin</a></header>'
        image = f'<img class="header-photo" src="{theme_image}" alt="" width="880" height="200">' if theme_image else ''
        header += '<div class="header-scene">' + image + nav + '</div>'
    hidden = ' visually-hidden' if layout == 'home' and not night else ''
    heading = f'<h1 class="page-title{hidden}">{escape(title)}</h1>'
    aside = '<aside aria-label="Archive navigation">' + meta + sidebar + '</aside>'
    if not night:
        content = '<div class="columns"><main id="main" tabindex="-1">' + heading + body + '</main>' + aside + '</div>'
    elif layout == "post":
        content = '<main id="main" class="night-main" tabindex="-1"><section class="video-stage"><div class="stage-inner">' + heading + video + '</div></section><div class="columns post-columns">' + body + aside + '</div></main>'
    else:
        gallery = layout in {'gallery', 'home'}
        panel = 'gallery-panel' if gallery else 'archive-content'
        cols = 'columns gallery-columns' if gallery else 'columns'
        stage = '<section class="home-stage"><div class="stage-inner">' + video + '</div></section>' if layout == 'home' else ''
        content = '<main id="main" class="night-main" tabindex="-1">' + stage + '<div class="gallery-heading">' + heading + '</div><div class="' + cols + '"><section class="' + panel + '">' + body + '</section>' + aside + '</div></main>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}">
<meta name="description" content="{escape(title + ' | ' + config['title'], quote=True)}"><title>{escape(title)} | {escape(config['title'])}</title>
<link rel="canonical" href="{escape(config['canonical_base'] + route, quote=True)}"><link rel="stylesheet" href="/assets/archive.css"><script src="/assets/legacy.js" defer></script></head>
<body class="{config['site']}"><a class="skip-link" href="#main">Skip to content</a><div class="site-shell">
{header}<p id="legacy-status" role="status"></p><noscript><p class="no-js">{anchor('/archive/', 'Browse all posts')}</p></noscript>
{content}<footer><p>{anchor(config['main_site'], 'Current work at stephenchin.com')}</p></footer></div></body></html>'''


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
            fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[path.suffix.lower()]
            # Keep transparency for formats that support it, because flattening a white-on-clear logo
            # onto RGB turns its transparent pixels into a solid white box on a dark header.
            has_alpha = image.mode in {"RGBA", "LA", "PA"} or (image.mode == "P" and "transparency" in image.info)
            mode = "RGBA" if has_alpha and fmt in {"PNG", "WEBP"} else "RGB"
            clean = Image.new(mode, image.size)
            clean.paste(image.convert(mode))
            options = {"JPEG": {"quality": 95, "optimize": True}, "WEBP": {"quality": 95}, "PNG": {"optimize": True}}[fmt]
            clean.save(target, format=fmt, **options)
        photos.add(url)
    return photos


class Audit(HTMLParser):
    def __init__(self, output, route, base=""):
        super().__init__(convert_charrefs=True)
        self.output, self.route, self.base = output, route, base
        self.unrecovered = []
        self.has_robots = False
        self.has_csp = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        require(tag not in {"iframe", "object", "embed", "form", "base", "style"}, f"Forbidden HTML element: {tag}")
        require(not any(k.startswith("on") or k in {"style", "srcdoc", "srcset"} for k in attrs), "Active HTML attribute")
        require("prototype" not in attrs.get("class", "").split(), "Reader-facing prototype notice")
        if tag == "meta" and attrs.get("name") == "robots":
            self.has_robots = attrs.get("content") == "noindex,nofollow"
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
        require(audit.has_robots and audit.has_csp, f"Missing robots policy or CSP: {route}")
        # The home page repeats post bodies that have their own pages. Report each unrecovered link once, on the post.
        if route != "/":
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
    night = config["site"] == "nighthacking"
    names = {c["slug"]: c["name"] for p in posts for c in p["categories"]}
    year_links = ''.join(f'<li>{anchor(f"/archive/{year}/", year)}</li>' for year in sorted(years, reverse=True))
    if night:
        recent = '<h2>Recent Videos</h2><ul>' + ''.join('<li>' + anchor('/' + p['slug'] + '/', p['title']) + '</li>' for p in posts[:5]) + '</ul>'
        sidebar = recent + '<h2>Archives</h2><ul>' + year_links + '</ul><h2>Categories</h2><ul>'
        sidebar += ''.join(f'<li>{anchor(f"/category/{slug}/", names[slug])}</li>' for slug in sorted(categories)) + '</ul>'
    else:
        sidebar = steveonjava_sidebar(year_links, categories, names, photos)
    image = THEME_IMAGES[config['site']]
    config['theme_image'] = image if image in photos else None
    gallery = 'gallery' if night else 'index'
    # Render each post once. The home page and the post page share the same output, so missing images are reported once.
    rendered = {p["id"]: render_markdown(p["markdown"], config, routes, '/' + p["slug"] + '/', photos) for p in posts}
    # Each page holds its heading, content, layout, video-stage markup and sidebar metadata.
    pages = {"/": home_page(posts, rendered, night),
             "/archive/": ("Archive by year", ''.join(f'<section><h2>{anchor(f"/archive/{year}/", year)}</h2>{post_list(years[year])}</section>' for year in sorted(years, reverse=True)), 'index', '', ''),
             "/404.html": ("Page not found", '<p>' + anchor('/archive/', 'Browse the archive') + ' or ' + anchor('/', 'return home') + '.</p>', 'index', '', '')}
    if night:
        pages["/videos/"] = ("Videos", post_list([p for p in posts if p["video_id"]], True), 'gallery', '', '')
    for year, records in years.items():
        pages[f"/archive/{year}/"] = (year, post_list(records, night), gallery, '', '')
    for slug, records in categories.items():
        pages[f"/category/{slug}/"] = (names[slug], post_list(records, night), gallery, '', '')
    for post in posts:
        route = '/' + post['slug'] + '/'
        video = video_reference(post) if post['video_id'] else ''
        content = rendered[post['id']]
        body = '<article class="entry">' + ('' if night else post_meta(post) + video)
        body += '<div class="entry-content">' + content + '</div>'
        body += ('' if night else taxonomy(post)) + '</article>'
        meta = '<div class="video-meta"><p>Video By <strong>steveonjava</strong></p><p>Posted On <time datetime="' + post['date'][:10] + '">' + readable_date(post['date']) + '</time></p>' + taxonomy(post) + '</div>' if night else ''
        pages[route] = (post['title'], body, 'post', video if night else '', meta)
    (output / "assets").mkdir(exist_ok=True)
    shutil.copyfile(root / "theme" / "archive.css", output / "assets" / "archive.css")
    script = (root / "theme" / "legacy.js").read_text(encoding="utf-8")
    require(script.count("__POST_MAP__") == 1 and script.count("__BASE_PATH__") == 1, "Invalid legacy script template")
    mapping = {str(p["id"]): '/' + p['slug'] + '/' for p in posts}
    script = script.replace("__POST_MAP__", json.dumps(mapping, sort_keys=True)).replace("__BASE_PATH__", json.dumps(base))
    (output / "assets" / "legacy.js").write_text(script, encoding="utf-8")
    for route, (title, body, layout, video, meta) in pages.items():
        target = output / route.lstrip("/")
        if route.endswith("/"):
            target /= "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rebase(page(config, title, body, route, sidebar, layout, video, meta), base), encoding="utf-8")
    unresolved = check(output, base)
    report = {"status": "prototype", "review_status": "unreviewed", "base_path": base, "posts": len(posts), "pages": len(pages), "photos": len(photos), "unrecovered_links": unresolved, "missing_images": config["missing_images"]}
    (root / "build-report.json").write_text(json.dumps(report, indent=2) + '\n', encoding="utf-8")
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
