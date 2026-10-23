# Historical archive prototype

This reusable template builds either SteveOnJava or NightHacking from supplied historical exports. It contains no historical sample records. Synthetic records exist only in isolated unit tests. This is an unreviewed prototype, not a complete recovery or a deployable production archive.

## Inputs

Create `archive.json` with exactly these keys:

- `site`: `steveonjava` or `nighthacking`
- `title`: the archive title
- `canonical_base`: `https://steveonjava.com` or `https://nighthacking.tv`, matching the site
- `main_site`: `https://stephenchin.com`
- `status`: `prototype`
- `period_label`: a truthful description of the period covered

Add each exported record as `content/<id>.json` and its inert Markdown transcription as `content/<id>.md`. JSON fields are `id`, `type`, `title`, `slug`, `date`, `categories`, `excerpt`, `original_urls`, `video_id`, `thumbnail`, `review_status`, `provenance`, and `warnings`. Unknown keys and duplicate JSON keys fail validation.

- IDs are positive integers and match filenames. Type is `post`. Review status is `unreviewed`.
- Slugs contain lowercase ASCII letters, digits, and single hyphens. Routes remain `/slug/`.
- Dates use `YYYY-MM-DD HH:MM:SS`. No source timezone is inferred.
- Categories are lists of objects with `slug` and `name`. Names must agree for shared slugs.
- Original URLs are nonempty lists of explicit HTTP or HTTPS links.
- Video IDs are null or 11-character YouTube IDs. Availability is unknown.
- Thumbnails are null or approved local paths under `/wp-content/uploads/YYYY/MM/`.
- Provenance is a nonempty JSON object. Preserve source evidence and export details.
- Warnings are lists of strings. Excerpts are plain text, not HTML.

Optionally add `link-status.json`, an object that maps each absolute external URL to `live`, `dead` or `unverified`. A `dead` link renders as plain text with a note, and its address is not emitted as an `href`. `live` and `unverified` links stay clickable with `nofollow noopener noreferrer`. Record the date and method of each check in the pull request, because a reachable address does not prove the same owner still runs it. Links to the retired hosts of the archived site itself (for NightHacking, both `nighthacking.tv` and `nighthacking.com`) become local routes. The original addresses appear on each post as plain text only, and provenance data stays in `content/<id>.json` and is never rendered.

Place only approved raster photos in `assets/wp-content/uploads/YYYY/MM/`. Supported extensions are `.jpg`, `.jpeg`, `.png`, and `.webp`. Builds decode and reencode photos to strip metadata. Images are bounded and animation is rejected. No original theme artwork is included. The SteveOnJava header uses an explicitly labeled gradient because the historical motorcycle photo is unavailable.

Markdown supports paragraphs, emphasis, links, images, lists, and fenced code. Raw HTML is escaped. Dangerous schemes, URL credentials, protocol-relative links, traversal, and symlinks fail validation. Remote images and unavailable local images become honest omission notes. External links have `nofollow noopener noreferrer`. Source prose is not rewritten.

## Local verification

Use Python 3.13. Install dependencies in a virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/build.py
python scripts/build.py --check-only
python -m http.server 8000 --directory _site --bind 127.0.0.1
```

The build performs no network retrieval. Dependency installation is a separate setup step. The build rejects empty content rather than inventing archive records. Unit tests construct temporary synthetic roots and do not need real exports.

All pages carry a prototype banner and current-site link. Browse without JavaScript through the home, archive, year, category, and post pages. NightHacking also has `/videos/`. Old `?p=ID` links translate only through the strict generated local map when JavaScript is enabled. Without JavaScript, the archive remains usable and explains the limitation.

Unknown historical links are marked as not included. `404.html` gives an accurate recovery notice and routes back to the archive. `build-report.json` records posts, pages, photos, and unrecovered historical links. The compiler checks generated navigation, local resources, unsafe HTML, and external link attributes. Unknown historical destinations are reported, not falsely declared recovered.

## Preview screenshots

```sh
python -m pip install -r requirements-preview.txt
python -m playwright install chromium
python scripts/screenshots.py
```

The screenshot helper serves only localhost, blocks nonlocal requests, checks JavaScript and no-JavaScript browsing, exercises the ID translator, and captures desktop and mobile home and post pages. It does not contact YouTube. No iframe, tracking, remote fonts, external image loading, or live forms are included.

## CI and no-deploy policy

The GitHub Actions workflow runs unit tests, builds `_site/`, audits it, and creates preview screenshots on Python 3.13. It uploads static files and screenshots as an expiring artifact. Repository permissions are read-only. It has no deployment, Pages configuration, credentials, secrets, privileged PR trigger, publishing, or merge step.

Review source provenance, content accuracy, images, links, privacy, rights, and browser screenshots before any future production proposal. Publishing is outside this prototype. Do not treat a passing build as editorial approval or evidence that a video still exists.

## Project-site builds

GitHub Pages serves a project repository at `https://<owner>.github.io/<repo>/`, not at a domain root. `python scripts/build.py --base-path /<repo>` prefixes every local `href` and `src` with that path and writes the same prefix into `assets/legacy.js`. The audit then checks every local URL against the prefix and fails on any URL outside it. Without the option, the build is for a domain root, which is what a custom domain gives. `python scripts/screenshots.py --base-path /<repo>` serves the build only under that prefix, so any URL that escapes the prefix returns 404 and fails the run. The prefix is one lowercase path segment.
