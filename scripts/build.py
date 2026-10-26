#!/usr/bin/env python3
"""Compile a historical archive from local inert records. Never fetch content."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from html import escape, unescape
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.parse import parse_qsl, unquote, unquote_to_bytes, urlsplit, urlunsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PIL import Image

CONFIG_KEYS = {"site", "title", "canonical_base", "main_site", "status", "period_label"}
POST_KEYS = {"id", "type", "title", "slug", "date", "categories", "excerpt", "original_urls", "video_id", "thumbnail", "review_status", "provenance", "warnings"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PHOTO = re.compile(r"/wp-content/uploads/\d{4}/(?:0[1-9]|1[0-2])/[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:jpg|jpeg|png|webp)\Z")
VIDEO = re.compile(r"[A-Za-z0-9_-]{11}\Z")
RESERVED = {"archive", "category", "videos", "pages", "page", "assets", "wp-content", "404", "index"}
URI_SEGMENT = re.compile(r"(?:[a-z0-9]|%[0-9a-fA-F]{2})+(?:-(?:[a-z0-9]|%[0-9a-fA-F]{2})+)*\Z")
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
LEGACY_ID = re.compile(r"[1-9][0-9]{0,9}\Z")
LIST_PAGE_SIZE = 20
MAX_RECORDS = 10000
MAX_LINK_STATUSES = 20000
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


def load_json(path, maximum=1000000):
    require(path.is_file() and not path.is_symlink(), f"Missing or unsafe file: {path}")
    require(path.stat().st_size <= maximum, f"Oversized JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: require(False, f"Invalid JSON constant: {value}"))


def decode_uri_path(path):
    """Decode once for filesystem lookup; encoded ASCII is never a route spelling."""
    text(path, "URI path", 4096)
    require(path.startswith("/") and not path.startswith("//"), "Local path must be root relative")
    require(not re.search(r"%(?![0-9a-fA-F]{2})", path), "Malformed percent escape")
    require(all(int(value, 16) >= 128 for value in re.findall(r"%([0-9a-fA-F]{2})", path)), "Encoded ASCII in local path")
    try:
        decoded = unquote_to_bytes(path).decode("utf-8", errors="strict")
    except (UnicodeError, ValueError) as error:
        raise ValueError("Malformed UTF-8 path") from error
    require(not any(c in decoded for c in "\\%?#<>\"'"), "Unsafe local path character")
    require(not any(unicodedata.category(c).startswith("C") or (c.isspace() and c != "\u3000") for c in decoded), "Control or whitespace in local path")
    require(not any(part in {".", ".."} for part in decoded.split("/")), "URL traversal")
    require("//" not in decoded, "Empty path component")
    return decoded


def route_key(route):
    # Compare decoded spellings, including hex case and Unicode canonical equivalents.
    return unicodedata.normalize("NFC", decode_uri_path(route)).casefold()


def validate_slug(slug):
    require(isinstance(slug, str) and len(slug) <= 2048 and URI_SEGMENT.fullmatch(slug), "Invalid slug")
    decoded = decode_uri_path("/" + slug)[1:]
    require(len(decoded.encode("utf-8")) <= 255, "Oversized slug component")
    return decoded


def record_route(record):
    """The only source of a record URI. Preserve the original percent spelling."""
    validate_slug(record["slug"])
    route = record.get("route", "/" + record["slug"] + "/")
    require(isinstance(route, str) and 2 < len(route) <= 4096 and route.startswith("/") and route.endswith("/"), "Invalid record route")
    parts = route[1:-1].split("/")
    require(len(parts) <= 16, "Too many route components")
    for part in parts:
        validate_slug(part)
    first = unicodedata.normalize("NFC", validate_slug(parts[0])).casefold()
    require(first not in RESERVED, "Invalid or reserved slug/route")
    require(record["type"] == "page" or "route" not in record, "Only static pages may supply route")
    return route


def output_path(output, uri):
    decoded = decode_uri_path(uri)
    path = output / decoded.lstrip("/")
    if uri.endswith("/"):
        path /= "index.html"
    require(path.resolve().is_relative_to(output.resolve()), "Output path escaped root")
    require(not path.is_symlink(), "Symlink output target")
    return path


def safe_url(value, absolute=False, allowed_routes=(), allowed_hosts=()):
    text(value, "URL", 4096)
    require(bool(value), "Empty URL")
    require(not re.search(r"%(?![0-9a-fA-F]{2})", value), "Malformed percent escape")
    decoded = value
    try:
        for _ in range(4):
            decoded = unquote(decoded, errors="strict")
    except UnicodeError as error:
        raise ValueError("Malformed UTF-8 URL") from error
    # WP's original Japanese slugs contain an encoded ideographic space. This is
    # permitted ONLY in an exact validated record path, never arbitrary URLs,
    # authorities, queries, fragments, ASCII spaces, or other Unicode whitespace.
    inspection = decoded
    if "\u3000" in decoded:
        raw = urlsplit(value)
        require(not raw.scheme or raw.hostname in allowed_hosts, "Whitespace in URL")
        raw_path = raw.path
        require(route_key(raw_path) in {route_key(route) for route in allowed_routes}, "Whitespace in URL")
        parsed = urlsplit(decoded)
        inspection = urlunsplit(parsed._replace(path=parsed.path.replace("\u3000", "")))
    require(not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in inspection), "Whitespace in URL")
    require(not any(c in decoded for c in "\\<>\"'"), "Unsafe URL character")
    require(not decoded.startswith("//"), "Protocol-relative URL")
    parsed = urlsplit(decoded)
    require(parsed.scheme in {"", "http", "https"}, "Unsafe URL scheme")
    require(not parsed.username and not parsed.password, "URL credentials are forbidden")
    require(not parsed.scheme or bool(parsed.netloc), "URL host is required")
    require(not absolute or parsed.scheme in {"http", "https"}, "Absolute HTTP URL required")
    require(not parsed.netloc or parsed.scheme in {"http", "https"}, "Invalid URL authority")
    require(not any(part in {".", ".."} for part in parsed.path.split("/")), "URL traversal")
    # Local paths use the same single-decode rules in the renderer and the audit.
    if not parsed.scheme and urlsplit(value).path:
        path = urlsplit(value).path
        decode_uri_path(path if path.startswith("/") else "/" + path)
    return value


def video_url_id(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    candidate = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.lstrip("/")
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        values = [v for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k == "v"]
        if parsed.path == "/watch" and len(values) == 1:
            candidate = values[0]
        elif re.fullmatch(r"/(?:embed|shorts|v)/[A-Za-z0-9_-]{11}/?", parsed.path):
            candidate = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return candidate if candidate and VIDEO.fullmatch(candidate) else None


def link_state(url, config):
    if url in config.get("dead_links", set()) or video_url_id(url) in config.get("dead_video_ids", set()):
        return "dead"
    return config.get("link_status", {}).get(url, "unverified")


def note_external(config, url, current):
    if urlsplit(url).scheme:
        config.setdefault("external_urls", defaultdict(set))[url].add(current)


def apply_link_policy(html, config, current):
    """Apply offline link policy to ALL template anchors as well as body links.

    Only our own escaped renderer can emit markup; anchors cannot be nested and
    attribute values cannot contain literal angle brackets. No source HTML enters here.
    """
    def replace(match):
        opening, inner = match.group(1), match.group(2)
        href = re.search(r'\bhref="([^"]*)"', opening)
        if not href:
            return match.group(0)
        url = unescape(href.group(1))
        if not urlsplit(url).scheme:
            return match.group(0)
        note_external(config, url, current)
        if link_state(url, config) != "dead":
            return match.group(0)
        attrs = re.sub(r'\s+(?:href|rel)="[^"]*"', '', opening)
        return '<span' + attrs + '>' + inner + '</span>'
    return re.sub(r'<a\b([^>]*)>(.*?)</a>', replace, html, flags=re.S)


def collection_chunks(route, records):
    require(type(LIST_PAGE_SIZE) is int and 1 <= LIST_PAGE_SIZE <= 50, "Invalid list page size")
    total = max(1, (len(records) + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
    for index in range(total):
        current = route if index == 0 else f"{route}page/{index + 1}/"
        yield current, records[index * LIST_PAGE_SIZE:(index + 1) * LIST_PAGE_SIZE], index + 1, total


def collection_pager(route, number, total):
    links = []
    if number > 1:
        previous = route if number == 2 else f"{route}page/{number - 1}/"
        links.append(anchor(previous, "\u2190 Newer entries"))
    if number < total:
        links.append(anchor(f"{route}page/{number + 1}/", "Older entries \u2192"))
    return '<nav class="pager" aria-label="Archive pages">' + ' | '.join(links) + '</nav>' if links else ''


def register_routes(routes):
    seen = {}
    for route in routes:
        key = route_key(route)
        require(key not in seen, f"Duplicate slug or route collision: {route} and {seen.get(key)}")
        seen[key] = route
    return seen


def validate_asset_records(root, config):
    """Check inspected registry shapes against INPUT assets, never reencoded output.

    Registries remain optional for isolated synthetic fixtures. If supplied, each
    coverage gate is exact; absence is reported, not represented as rights clearance.
    Theme artwork evidence is distinct from the lab recovery manifest.
    """
    assets = {"/" + path.relative_to(root / "assets").as_posix(): path
              for path in (root / "assets").rglob("*") if path.is_file()}
    for url in assets:
        require(PHOTO.fullmatch(url), f"Unexpected asset: {url}")
    hashes = {}
    for url, path in assets.items():
        require(path.stat().st_size <= 20000000, "Oversized image")
        hashes[url] = hashlib.sha256(path.read_bytes()).hexdigest()
    def entries(items, label, provenance=False):
        require(isinstance(items, list) and len(items) <= 20000, f"Invalid {label} registry")
        found = set()
        for item in items:
            require(isinstance(item, dict), f"Invalid {label} entry")
            url = item.get("path")
            require(isinstance(url, str) and PHOTO.fullmatch(url), f"Invalid {label} path")
            require(url not in found, f"Duplicate {label} path: {url}")
            found.add(url)
            require(url in assets, f"Stale {label} path: {url}")
            digest = item.get("export_sha256")
            require(isinstance(digest, str) and HEX256.fullmatch(digest), f"Invalid {label} export hash")
            require(digest == hashes[url], f"{label} export hash mismatch: {url}")
            if provenance:
                digest = item.get("source_sha256")
                require(isinstance(digest, str) and HEX256.fullmatch(digest), f"Invalid {label} source hash")
                require(bool(text(item.get("transformation"), "transformation", 4000).strip()), f"Missing {label} transformation")
                if "site" in item:
                    require(item["site"] == config["site"], f"Wrong site in {label}")
                for field in ["width", "height", "bytes"]:
                    if field in item:
                        require(type(item[field]) is int and item[field] > 0, f"Invalid {label} {field}")
                if "bytes" in item:
                    require(item["bytes"] == assets[url].stat().st_size, f"{label} byte count mismatch: {url}")
            else:
                for field in ["rights_holder", "status", "basis"]:
                    require(bool(text(item.get(field), f"rights {field}", 4000).strip()), f"Missing rights {field}")
        return found
    rights_path = root / "rights.json"
    rights_present = rights_path.exists() or rights_path.is_symlink()
    if rights_present:
        rights = entries(load_json(rights_path, 8000000), "rights")
        require(rights == set(assets), "Incomplete rights coverage of actual assets")
    recovery_path, theme_path = root / "recovery-manifest.json", root / "docs/theme-art.json"
    recovery_present = recovery_path.exists() or recovery_path.is_symlink()
    theme_present = theme_path.exists() or theme_path.is_symlink()
    recovered, theme = set(), set()
    if recovery_present:
        manifest = load_json(recovery_path, 8000000)
        require(isinstance(manifest, dict) and "media" in manifest, "Invalid recovery-manifest.json")
        recovered = entries(manifest["media"], "recovery", True)
    if theme_present:
        theme = entries(load_json(theme_path, 8000000), "theme-art", True)
    if recovery_present or theme_present:
        require(recovered | theme == set(assets), "Incomplete image provenance coverage of actual assets")
    return {"assets": len(assets), "rights_checked": rights_present,
            "image_provenance_checked": recovery_present or theme_present,
            "lab_images": len(recovered), "theme_images": len(theme),
            "shared_theme_lab_images": sorted(recovered & theme),
            "input_sha256": hashes}


def validate(root):
    require(root.is_dir() and not root.is_symlink(), "Root must be a real directory")
    for directory in [root / "content", root / "assets", root / "theme", root / "docs"]:
        if directory.exists() or directory.is_symlink():
            require(not directory.is_symlink(), f"Symlink: {directory}")
            for path in directory.rglob("*"):
                require(not path.is_symlink(), f"Symlink: {path}")
                require(path.is_file() or path.is_dir(), f"Unexpected filesystem object: {path}")
    config = load_json(root / "archive.json")
    require(isinstance(config, dict) and set(config) == CONFIG_KEYS, "Invalid archive.json keys")
    require(isinstance(config["site"], str) and config["site"] in {"steveonjava", "nighthacking"}, "Invalid site")
    host = "steveonjava.com" if config["site"] == "steveonjava" else "nighthacking.tv"
    require(config["canonical_base"] == f"https://{host}", "Unexpected canonical_base")
    require(config["main_site"] == "https://stephenchin.com", "Unexpected main_site")
    require(config["status"] == "prototype", "Only prototype builds are permitted")
    # A CNAME file at the repository root marks a site that is bound to its own domain. GitHub ignores the file
    # for workflow deployments, so here it only tells the build to serve from the domain root.
    config["custom_domain"] = None
    marker = root / "CNAME"
    if marker.exists() or marker.is_symlink():
        require(marker.is_file() and not marker.is_symlink(), "CNAME must be a regular file")
        require(marker.read_text(encoding="utf-8") in {host, host + "\n"}, f"CNAME must name exactly {host}")
        config["custom_domain"] = host
    for key in ["title", "period_label"]:
        require(bool(text(config[key], key, 300).strip()), f"Empty {key}")
    # Optional owner-reviewed record of external link checks. Dead links render as plain text.
    dead, status = set(), {}
    status_path = root / "link-status.json"
    if status_path.exists() or status_path.is_symlink():
        status = load_json(status_path, 8000000)
        require(isinstance(status, dict) and len(status) <= MAX_LINK_STATUSES, "Invalid link-status.json")
        for url, state in status.items():
            safe_url(url, absolute=True)
            require(isinstance(state, str) and state in LINK_STATES, "Invalid link state")
            if state == "dead":
                dead.add(url)
    config["dead_links"] = dead
    config["link_status"] = status
    config["dead_video_ids"] = {video_url_id(url) for url in dead} - {None}
    config["missing_images"], config["unknown_legacy_ids"] = [], []
    config["external_urls"] = defaultdict(set)
    posts = []
    ids, category_names = set(), {}
    content = root / "content"
    require(content.is_dir(), "Missing content directory")
    require(all(p.is_file() and p.suffix in {".json", ".md"} for p in content.iterdir()), "Unexpected content file")
    record_files = sorted(content.glob("*.json"))
    require(len(record_files) <= MAX_RECORDS, "Too many content records")
    for path in record_files:
        p = load_json(path)
        require(isinstance(p, dict) and (set(p) == POST_KEYS or set(p) == POST_KEYS | {"route"}), f"Invalid post keys: {path.name}")
        require(type(p["id"]) is int and 0 < p["id"] <= 2147483647, "Invalid post ID")
        require(path.stem == str(p["id"]), "ID must match filename")
        require(p["id"] not in ids, "Duplicate post ID")
        ids.add(p["id"])
        require(isinstance(p["type"], str) and p["type"] in {"post", "page"} and p["review_status"] == "unreviewed", "Invalid post status or type")
        route = record_route(p)
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
            safe_url(url, absolute=True, allowed_routes=[route], allowed_hosts=ALIASES[config["site"]])
        require(p["video_id"] is None or isinstance(p["video_id"], str) and VIDEO.fullmatch(p["video_id"]), "Invalid YouTube ID")
        require(p["thumbnail"] is None or isinstance(p["thumbnail"], str) and PHOTO.fullmatch(p["thumbnail"]), "Invalid thumbnail")
        if p["thumbnail"]:
            require((root / "assets" / p["thumbnail"].lstrip("/")).is_file(), "Missing thumbnail")
        require(isinstance(p["provenance"], dict) and bool(p["provenance"]), "Provenance is required")
        provenance = p["provenance"]
        if "post_id" in provenance:
            require(type(provenance["post_id"]) is int and provenance["post_id"] == p["id"], "Provenance post ID mismatch")
        if "source_content_sha256" in provenance:
            require(isinstance(provenance["source_content_sha256"], str) and HEX256.fullmatch(provenance["source_content_sha256"]), "Invalid provenance source hash")
        require(isinstance(p["warnings"], list), "Invalid warnings")
        for warning in p["warnings"]:
            text(warning, "warning")
        md = path.with_suffix(".md")
        require(md.is_file() and md.stat().st_size <= 2000000, "Missing or oversized markdown")
        p["markdown"] = text(md.read_text(encoding="utf-8"), "markdown", 2000000)
        posts.append(p)
    require(bool(posts), "No historical records supplied. Add reviewed export inputs before building")
    require({p.stem for p in content.glob("*.md")} == {str(p["id"]) for p in posts}, "Orphan markdown file")
    register_routes(record_route(record) for record in posts)
    config["asset_review"] = validate_asset_records(root, config)
    return config, sorted(posts, key=lambda p: (p["date"], p["id"]), reverse=True)


def localize(url, config):
    lookup = config.get("route_lookup", {})
    safe_url(url, allowed_routes=lookup.values(), allowed_hosts=ALIASES[config["site"]])
    parsed = urlsplit(url)
    if parsed.hostname in ALIASES[config["site"]]:
        url = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "") + (f"#{parsed.fragment}" if parsed.fragment else "")
        parsed = urlsplit(url)
    if not parsed.scheme and parsed.path:
        path = parsed.path if parsed.path.startswith("/") else "/" + parsed.path
        path = lookup.get(route_key(path), path)
        url = urlunsplit(("", "", path, parsed.query, parsed.fragment))
    return url


def legacy_target(url, config, current):
    """Resolve strict WP IDs offline. Return (URL, unresolved-legacy flag)."""
    parsed = urlsplit(url)
    if parsed.scheme:
        return url, False
    params = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
              if key in {"p", "page_id"}]
    if not params:
        return url, False
    reason = "invalid"
    if len(params) == 1:
        key, value = params[0]
        if LEGACY_ID.fullmatch(value) and int(value) <= 2147483647:
            target = config.get("record_routes", {}).get(value)
            if target:
                return target + ("#" + parsed.fragment if parsed.fragment else ""), False
            reason = "unknown"
    config["unknown_legacy_ids"].append({"page": current, "target": url, "parameters": [list(pair) for pair in params], "reason": reason})
    return url, True


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
    md.validateLink = lambda value: bool(safe_url(value, allowed_routes=config.get("route_lookup", {}).values(), allowed_hosts=ALIASES[config["site"]]))
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
                original = token.attrGet("href")
                url = localize(original, config)
                note_external(config, url, current)
                if link_state(original, config) == "dead":
                    # Constant markup only. The dead address is never emitted as an href. Link text stays as plain text.
                    token.type, token.tag, token.attrs, token.content = "html_inline", "", {}, '<span class="dead-link">'
                    in_dead_link = True
                    continue
                url, unknown_legacy = legacy_target(url, config, current)
                token.attrSet("href", url)
                if urlsplit(url).scheme:
                    token.attrSet("rel", REL)
                elif unknown_legacy or (local_target(url, current) not in routes and local_target(url, current) not in photos and not url.startswith("#")):
                    token.attrSet("data-unrecovered", "true")
            if token.type == "link_close" and in_dead_link:
                token.type, token.tag, token.attrs, token.content = "html_inline", "", {}, '</span>'
                in_dead_link = False
                continue
            if token.type == "image":
                url = localize(token.attrGet("src"), config)
                safe_url(url, allowed_routes=config.get("route_lookup", {}).values())
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
        route = record_route(post)
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
    route = record_route(post)
    video = video_reference(post) if post['video_id'] else ''
    return ('<article class="entry"><h2 class="entry-title">' + anchor(route, post['title']) + '</h2>' + post_meta(post) + video
            + '<div class="entry-content">' + content + '</div>' + taxonomy(post) + '</article>')


def pager(url, label):
    return '<nav class="pager" aria-label="More posts">' + anchor(url, label) + '</nav>'


def home_stage(post):
    """Featured player area. It links to the local page and never embeds or contacts a player."""
    label = escape(post['title'], quote=True)
    return ('<div class="home-player"><a class="video-poster" href="' + record_route(post) + '" aria-label="Watch ' + label + '">'
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
    if config.get("has_pages"):
        nav_items.append(("/pages/", "Pages"))
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
    def __init__(self, output, route, base="", routes=()):
        super().__init__(convert_charrefs=True)
        self.output, self.route, self.base = output, route, base
        local_routes = list(routes)
        self.allowed_routes = local_routes + [base + item for item in local_routes]
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
            safe_url(url, allowed_routes=self.allowed_routes, allowed_hosts={"steveonjava.com", "nighthacking.tv"})
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
            path = output_path(self.output, target)
            if attrs.get("data-unrecovered") == "true" and tag == "a":
                self.unrecovered.append(url)
            else:
                require(path.is_file(), f"Broken local link on {self.route}: {url}")


class Canonical(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.urls.append(attrs.get("href"))


def check(output, base="", routes=None):
    require(isinstance(base, str) and BASE_PATH.fullmatch(base) is not None, "Invalid base path")
    output = Path(output)
    require(output.is_dir() and not output.is_symlink(), "Unsafe output directory")
    require(not any(path.is_symlink() for path in output.rglob("*")), "Symlink in generated output")
    stylesheet = (output / "assets/archive.css").read_text(encoding="utf-8")
    require(not re.search(r"url\s*\(|@import|expression\s*\(", stylesheet, re.I), "Unexpected CSS resource or active expression")
    # Read the canonical identity to preserve the exact original percent spelling
    # while proving that it names this decoded Unicode filesystem target.
    identities = []
    for file in sorted(output.rglob("*.html")):
        html = file.read_text(encoding="utf-8")
        canonical = Canonical()
        canonical.feed(html)
        require(len(canonical.urls) == 1 and isinstance(canonical.urls[0], str), "Missing or duplicate canonical route")
        parsed = urlsplit(canonical.urls[0])
        require(parsed.scheme == "https" and parsed.netloc in {"steveonjava.com", "nighthacking.tv"} and not parsed.query and not parsed.fragment, "Invalid canonical URL")
        route = parsed.path
        if route not in {"/", "/404.html"}:
            require(route.startswith("/") and route.endswith("/"), "Invalid generated route")
            for part in route[1:-1].split("/"):
                validate_slug(part)
        require(output_path(output, route).resolve() == file.resolve(), "Canonical URI does not match output path")
        identities.append((route, html))
    require(bool(identities), "No generated pages")
    discovered = register_routes(route for route, _ in identities)
    if routes is not None:
        require(set(discovered.values()) == set(routes), "Generated HTML coverage differs from route plan")
    unresolved = []
    for route, html in identities:
        audit = Audit(output, route, base, discovered.values())
        audit.feed(html)
        require(audit.has_robots and audit.has_csp, f"Missing robots policy or CSP: {route}")
        # The home page repeats bodies; report unrecovered links on the record.
        if route != "/":
            unresolved.extend({"page": route, "target": url} for url in audit.unrecovered)
    return unresolved


def build(root, base=""):
    require(isinstance(base, str) and BASE_PATH.fullmatch(base) is not None, "Invalid base path")
    root = Path(root).absolute()
    config, records = validate(root)
    require(not (config["custom_domain"] and base), "A site bound to a custom domain must be built for the domain root")
    posts = [record for record in records if record["type"] == "post"]
    static_pages = sorted((record for record in records if record["type"] == "page"), key=lambda record: (record["title"].casefold(), record["id"]))
    config["has_pages"] = bool(static_pages)
    config["record_routes"] = {str(record["id"]): record_route(record) for record in records}
    years, categories = defaultdict(list), defaultdict(list)
    for post in posts:
        years[post["date"][:4]].append(post)
        for category in post["categories"]:
            categories[category["slug"]].append(post)
    night = config["site"] == "nighthacking"
    # Plan all collections before rendering: every continuation participates in
    # collision checking, link rewriting, output, reporting, and browser coverage.
    collections = [("/archive/", "Archive by year", posts, "archive")]
    if night:
        collections.append(("/videos/", "Videos", [post for post in posts if post["video_id"]], "videos"))
    if static_pages:
        collections.append(("/pages/", "Pages", static_pages, "pages"))
    collections.extend((f"/archive/{year}/", year, years[year], "posts") for year in sorted(years, reverse=True))
    names = {category["slug"]: category["name"] for post in posts for category in post["categories"]}
    collections.extend((f"/category/{slug}/", names[slug], categories[slug], "posts") for slug in sorted(categories))
    chunks = [(start, title, kind, route, subset, number, total)
              for start, title, items, kind in collections
              for route, subset, number, total in collection_chunks(start, items)]
    route_list = ["/", "/404.html"] + list(config["record_routes"].values()) + [chunk[3] for chunk in chunks]
    config["route_lookup"] = register_routes(route_list)
    routes = set(route_list)
    output = root / "_site"
    require(not output.is_symlink(), "Output cannot be a symlink")
    report_path = root / "build-report.json"
    require(not report_path.is_symlink(), "Build report cannot be a symlink")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()
    photos = copy_photos(root, output)
    year_links = ''.join(f'<li>{anchor(f"/archive/{year}/", year)}</li>' for year in sorted(years, reverse=True))
    if night:
        recent = '<h2>Recent Videos</h2><ul>' + ''.join('<li>' + anchor(record_route(post), post['title']) + '</li>' for post in posts[:5]) + '</ul>'
        sidebar = recent + '<h2>Archives</h2><ul>' + year_links + '</ul><h2>Categories</h2><ul>'
        sidebar += ''.join(f'<li>{anchor(f"/category/{slug}/", names[slug])}</li>' for slug in sorted(categories)) + '</ul>'
    else:
        sidebar = steveonjava_sidebar(year_links, categories, names, photos)
    if static_pages:
        sidebar += '<h2>Pages</h2><ul><li>' + anchor('/pages/', 'All pages') + '</li></ul>'
    image = THEME_IMAGES[config['site']]
    config['theme_image'] = image if image in photos else None
    gallery = 'gallery' if night else 'index'
    # Render bodies once: home repeats the same prose, never duplicate evidence.
    rendered = {record["id"]: render_markdown(record["markdown"], config, routes, record_route(record), photos) for record in records}
    pages = {"/": home_page(posts, rendered, night),
             "/404.html": ("Page not found", '<p>' + anchor('/archive/', 'Browse the archive') + ' or ' + anchor('/', 'return home') + '.</p>', 'index', '', '')}
    for start, title, kind, route, subset, number, total in chunks:
        if kind == "archive":
            grouped = defaultdict(list)
            for record in subset:
                grouped[record["date"][:4]].append(record)
            body = ''.join(f'<section><h2>{anchor(f"/archive/{year}/", year)}</h2>{post_list(grouped[year])}</section>' for year in sorted(grouped, reverse=True))
            layout = 'index'
        elif kind == "pages":
            body = '<ul class="post-list" role="list">' + ''.join('<li class="card"><h2>' + anchor(record_route(record), record['title']) + '</h2></li>' for record in subset) + '</ul>'
            layout = 'index'
        else:
            body, layout = post_list(subset, night), gallery
        body += collection_pager(start, number, total)
        heading = title if number == 1 else f"{title} (Page {number})"
        pages[route] = (heading, body, layout, '', '')
    for record in records:
        route = record_route(record)
        video = video_reference(record) if record['video_id'] else ''
        content = rendered[record['id']]
        if record['type'] == 'page':
            body = '<article class="entry">' + video + '<div class="entry-content">' + content + '</div></article>'
            pages[route] = (record['title'], body, 'index', '', '')
            continue
        body = '<article class="entry">' + ('' if night else post_meta(record) + video)
        body += '<div class="entry-content">' + content + '</div>'
        body += ('' if night else taxonomy(record)) + '</article>'
        meta = '<div class="video-meta"><p>Video By <strong>steveonjava</strong></p><p>Posted On <time datetime="' + record['date'][:10] + '">' + readable_date(record['date']) + '</time></p>' + taxonomy(record) + '</div>' if night else ''
        pages[route] = (record['title'], body, 'post', video if night else '', meta)
    require(set(pages) == routes, "Generated pages disagree with planned routes")
    (output / "assets").mkdir(exist_ok=True)
    shutil.copyfile(root / "theme" / "archive.css", output / "assets" / "archive.css")
    script = (root / "theme" / "legacy.js").read_text(encoding="utf-8")
    require(script.count("__POST_MAP__") == 1 and script.count("__BASE_PATH__") == 1, "Invalid legacy script template")
    script = script.replace("__POST_MAP__", json.dumps(config["record_routes"], sort_keys=True)).replace("__BASE_PATH__", json.dumps(base))
    (output / "assets" / "legacy.js").write_text(script, encoding="utf-8")
    for route, (title, body, layout, video, meta) in pages.items():
        target = output_path(output, route)
        target.parent.mkdir(parents=True, exist_ok=True)
        html = apply_link_policy(page(config, title, body, route, sidebar, layout, video, meta), config, route)
        target.write_text(rebase(html, base), encoding="utf-8")
    unresolved = check(output, base, routes=routes)
    external = [{"url": url, "status": link_state(url, config), "pages": sorted(locations)}
                for url, locations in sorted(config["external_urls"].items())]
    report = {"status": "prototype", "review_status": "unreviewed", "base_path": base,
              "custom_domain": config["custom_domain"], "posts": len(posts), "static_pages": len(static_pages),
              "pages": len(pages), "photos": len(photos), "routes": sorted(routes),
              "record_routes": config["record_routes"], "unrecovered_links": unresolved,
              "missing_images": config["missing_images"], "unknown_legacy_ids": config["unknown_legacy_ids"],
              "external_links": external, "unverified_external_urls": [item["url"] for item in external if item["status"] == "unverified"],
              "asset_review": config["asset_review"]}
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding="utf-8")
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
