# Historical static archive builder

This template builds either SteveOnJava or NightHacking from validated local historical exports. Records belong in each archive repository, while synthetic records exist only in isolated unit tests.

## Inputs

`archive.json` has exactly these keys: `site` (`steveonjava` or `nighthacking`), `title`, `canonical_base` (the matching original HTTPS domain), `main_site` (`https://stephenchin.com`), `status` (`prototype`), and `period_label`. Status and period labels are repository metadata, not page copy.

Each record has `content/<id>.json` and `content/<id>.md`. JSON fields are `id`, `type`, `title`, `slug`, `date`, `categories`, `excerpt`, `original_urls`, `video_id`, `thumbnail`, `review_status`, `provenance`, and `warnings`. Unknown or duplicate keys fail validation.

- IDs are positive integers matching filenames. Type is `post`, with review state kept in JSON.
- Slugs are lowercase ASCII words separated by single hyphens. Routes remain `/slug/`.
- Dates use `YYYY-MM-DD HH:MM:SS`, without inferring a source timezone.
- Categories contain consistent `slug` and `name` fields.
- Video IDs are null or validated 11-character YouTube IDs.
- Thumbnails are null or approved local upload paths.
- Excerpts are plain text. Provenance, original addresses and warnings are retained in Git, never rendered as review notes.

Optional `link-status.json` maps absolute external URLs to `live`, `dead`, or `unverified`. Dead or hijacked links become plain text without commentary or a tooltip. Other external links retain `nofollow noopener noreferrer`. Retired site hosts become local routes, and unresolved historical targets are reported in the build artifact without inserted disclaimers.

Approved raster assets live under `assets/wp-content/uploads/YYYY/MM/`, with `.jpg`, `.jpeg`, `.png`, or `.webp` extensions. Builds decode and encode fresh pixels without inherited metadata, reject animation and bound dimensions and file size. Header artwork uses the same safety path as post images. Source locators, transformations, hashes and rights states are recorded in Git.

## Presentation

Fresh CSS recreates the original rendered Freshy 2 (SteveOnJava) and Focus (NightHacking) layouts. No original stylesheet, theme code, plugin or CMS runs here. The visual references and measurements are in `docs/theme-reference.md`.

Review previews show the intended reader experience, with no prototype banners, unreviewed labels, source-review details, missing-artwork apologies, recovery explanations, or provider-opening boilerplate. Keep qualifications in commit messages and PR descriptions. Original prose is preserved. The renderer omits only exact standalone omission notices inserted by the exporter and suppresses missing-image placeholders without rewriting surrounding prose.

Home, archive, year, category and post routes work without JavaScript. NightHacking also has `/videos/`. The strict local `?p=ID` translator uses only validated routes. The 404 and unknown-ID fallback provide concise navigation. Every page keeps CSP and `noindex,nofollow` until a separate launch decision, and the footer links to the current site.

## GitHub Actions verification

`build.yml` has read-only permissions and no deploy step or secrets. On Python 3.13 it runs:

1. Pinned dependencies and unit tests covering both themes, hostile synthetic input, metadata separation, artwork, and provider-response classification.
2. Offline compilation and audit for a domain root, then for the project's GitHub Pages path.
3. A separate public YouTube oEmbed metadata check. It makes no playback, captions, viewing or reuse claim. Rejected requests and transport failures remain inconclusive rather than declaring a video deleted.
4. Chromium browser tests with every nonlocal resource request blocked. All supplied posts, home, archive, videos and 404 routes get desktop and mobile screenshots. Tests check images decode, original desktop geometry, overflow, keyboard access, no-JavaScript browsing and legacy IDs.

The `archive-prototype-preview` artifact contains `_site/`, `screenshots/`, `build-report.json`, and `video-checks.json`. Reports remain outside `_site/` so review evidence is not published with reader pages. `build-report.json` lists missing images and unresolved historical links. Passing CI does not authorize merging or deployment.

## Project-site builds and deployment

GitHub Pages project sites live at `https://<owner>.github.io/<repo>/`. `python scripts/build.py --base-path /<repo>` prefixes every local `href` and `src` and the ID translator, while `--check-only --base-path /<repo>` audits them. Without the option, output serves a domain root. The browser-test server answers only under the selected prefix so escaping URLs fail.

The separate `pages.yml` runs only on `main` or explicit manual dispatch. Its build job is read-only, with `pages: write` and `id-token: write` granted only to the deploy job. Feature-branch PRs only produce review artifacts. Merge and publication require owner approval independently of branch preparation.
