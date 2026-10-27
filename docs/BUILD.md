# Historical static archive builder

This template builds either SteveOnJava or NightHacking from validated local historical exports. Records belong in each archive repository, while synthetic records exist only in isolated unit tests. The builder and normal CI are offline. Provider requests require separate explicit authorization and an exact approved-ID list.

## Inputs

`archive.json` has exactly these keys: `site` (`steveonjava` or `nighthacking`), `title`, `canonical_base` (the matching original HTTPS domain), `main_site` (`https://stephenchin.com`), `status` (`prototype`), and `period_label`. Status and period labels are repository metadata, not page copy.

Each record has `content/<id>.json` and `content/<id>.md`. Required JSON fields remain `id`, `type`, `title`, `slug`, `date`, `categories`, `excerpt`, `original_urls`, `video_id`, `thumbnail`, `review_status`, `provenance`, and `warnings`. The only optional record field is `route`. Unknown or duplicate keys fail validation. No extra top-level archive configuration or separate pages registry is required.

- IDs are positive integers matching filenames, shared uniquely across posts and static pages. Types are `post` or `page`. Review status remains `unreviewed`. Only genuine exported static pages belong here, not search, login, form, account, or other dynamic endpoints. The exporter/owner selects eligible public records. The renderer cannot infer their original publication/privacy state from prose.
- Existing lowercase ASCII slugs retain their `/slug/` routes and single-hyphen validation. Original WordPress percent-encoded UTF-8 slugs are preserved **exactly**, including the spelling/case of percent escapes. They are never transliterated. Literal non-ASCII JSON slugs are not accepted.
- A static page may supply a root-relative directory `route`, such as `/training/course/`. Without it, the page uses `/slug/`. Post routes cannot be overridden. Nested static pages may share a leaf slug if their complete routes differ. Routes must end in `/`, contain at most 16 validated components, and have no authority, query, fragment, empty component, or traversal. Builder-owned namespaces (`archive`, `category`, `videos`, `pages`, `page`, `assets`, `wp-content`, `404`, `index`) are reserved at the root.
- URI-to-filesystem conversion decodes UTF-8 **once**, writing Unicode directory names while emitting encoded URIs in links, canonical addresses, legacy-ID maps, and reports. Malformed escapes/UTF-8, encoded ASCII (including slash, dot, percent, control, and double-decoding attempts), control/format characters, and whitespace are rejected. The sole whitespace exception is an ideographic space (`%e3%80%80`) inside a validated original record path. It is not an exception for arbitrary external URLs, authorities, queries, or fragments. Filesystem components are bounded to 255 UTF-8 bytes. Collision checks compare decoded, NFC-normalized, case-folded routes. No normalization rewrites the emitted URI or source record.
- Dates use `YYYY-MM-DD HH:MM:SS`, without inferring a source timezone.
- Categories contain consistent lowercase ASCII `slug` and plain-text `name` fields. Static page categories are retained as metadata but never enter the post category/year collections.
- Video IDs are null or validated 11-character YouTube IDs. Thumbnails are null or approved local upload paths.
- Excerpts are plain text. Provenance, original addresses and warnings remain in Git, not reader-facing review notes. Nonempty provenance is required. When the known `post_id` and `source_content_sha256` fields occur, the ID must match the record and the hash must be a lowercase SHA-256 value. A source-content hash is not compared with exported Markdown: those are different representations. Unrecognized provenance fields are not invented or interpreted as rights clearance.
- Inputs are bounded: at most 10,000 records. Each record JSON is at most 1 MB and Markdown at most 2 MB. Link/image registries are individually capped at 8 MB and 20,000 entries. Duplicate keys remain forbidden at every level.

### Link policy and offline reports

Optional `link-status.json` maps absolute external URLs to `live`, `dead`, or `unverified`. Absolute HTTP(S) destinations may retain once-encoded ASCII spaces (`%20`) or apostrophes (`%27`) in a path, query or fragment. Literal whitespace/quotes, encoded authority whitespace/quotes, userinfo, local-route/asset spaces, repeated decoding and control characters remain rejected. Missing entries are **unverified**, not implicitly checked. Dead links render their original label/artwork without a clickable address, commentary, or tooltip. This policy covers body links, video posters/watch links, and template/sidebar links. Other external links retain `nofollow noopener noreferrer`. A dead YouTube watch/short/embed URL is matched by validated video ID across `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `youtu.be` spellings. A conflicting live spelling does not resurrect that video. Inconclusive provider results are not treated as dead.

Retired site hosts become local routes, including the former `nighthacking.com` hosts. Known routes are canonicalized to the supplied URI spelling. Strict local `?p=ID` and `?page_id=ID` links are resolved offline through the same all-record route map used by the browser translator. Duplicate/mixed ID parameters, zero-padded/oversized IDs, and unknown IDs are reported. They cannot select arbitrary destinations. Known IDs preserve fragments when localized in body links. Unresolved historical targets are reported separately from generated navigation failures, without inserted disclaimers. No URL in evidence/provenance is fetched by compilation or validation.

### Assets, rights, and recovery evidence

Approved raster assets live under `assets/wp-content/uploads/YYYY/MM/`, with `.jpg`, `.jpeg`, `.png`, or `.webp` extensions. Existing historical mixed-case filenames remain supported. New exporter output may use dated lowercase ASCII JPEG/PNG paths. Builds decode and encode fresh pixels without inherited metadata, reject animation and symlinks, and bound dimensions and file size. Header/sidebar artwork follows the same safety path as post images.

The checked registry formats are the existing repository formats, not newly fabricated manifests:

- `rights.json`: an array of records with `path`, `export_sha256`, and nonempty `rights_holder`, `status`, and `basis`. Optional existing notes/source fields remain untouched. When supplied, its paths must match **all actual files in `assets/` exactly**, including unused images and theme artwork. Missing, duplicate, stale, and hash-mismatched entries fail.
- `recovery-manifest.json`: an object with a `media` array. Entries identify lab-recovered images using `path`, `export_sha256`, `source_sha256`, and `transformation`.
- `docs/theme-art.json`: an array of separately recovered public theme-art records with those image fields. Supplied `site` must match this archive. Theme evidence remains distinct from lab media evidence. One identical verified raster may have evidence from both sources, and `shared_theme_lab_images` records that overlap without duplicating the actual asset. If either provenance registry is supplied, their union must cover **all actual assets** exactly. Present positive `bytes`, `width`, and `height` fields are type-checked. `bytes` must match the input file. Registry source URLs are retained as evidence only and never fetched.

Export hashes are compared against the sanitized **input asset bytes**, before this builder's second metadata-stripping reencode. They are not output-image hashes. Source hashes are format-checked, not verified against excluded original bytes. Record-selection/approval keys in recovery manifests are not interpreted as an invented page-approval schema. Synthetic fixtures may omit the registries. `asset_review` then explicitly reports the corresponding checks as false. Registry absence is not clearance. Human rights/publication approval remains separate from successful integrity checks.

## Presentation and bounded discovery

Fresh CSS recreates the original rendered Freshy 2 (SteveOnJava) and Focus (NightHacking) layouts. No original stylesheet, theme code, plugin or CMS runs here. The visual references and measurements are in `docs/theme-reference.md`.

Review previews show the intended reader experience, with no prototype banners, unreviewed labels, source-review details, missing-artwork apologies, recovery explanations, or provider-opening boilerplate. Keep qualifications in commit messages and PR descriptions. Original prose is preserved. The renderer omits only exact standalone omission notices inserted by the exporter and suppresses missing-image placeholders without rewriting surrounding prose. Raw source HTML is escaped, never executed.

The approved home remains 10 full SteveOnJava posts or 15 NightHacking cards, with the existing featured-stage behavior when eligible local artwork exists. Missing hero artwork is allowed. Static pages never enter the home, post archive, recent-post/video sidebar, year/category lists, or `/videos/`.

Home, archive, year, category, post, and static-page routes work without JavaScript. NightHacking also has `/videos/`. When static pages exist, navigation links to `/pages/`. That index includes every supplied static page without JavaScript. No `/pages/` route or new navigation item is emitted when pages are absent.

The archive, videos, year, category, and static-page discovery lists are limited to **20 records per generated page**. Page one keeps its existing route. Continuations use `<collection>/page/2/`, `/page/3/`, etc. Previous/next navigation connects the complete stable sequence, with no dropped records or empty final continuation. `/archive/` retains year groupings within each bounded slice. Root/year/category route planning and collision checks happen before rendering.

The browser translator uses only the validated all-record map for `?p=ID` and `?page_id=ID`, supporting nested and encoded paths. It rejects invalid, duplicate, mixed, or unknown IDs instead of navigating externally. The 404 and unknown-ID fallback provide concise navigation. Every page retains the existing strict CSP, `noindex,nofollow`, current-site footer link, and resource restrictions until a separate launch decision.

## External build-report contract

`build-report.json` stays **outside `_site/`** and is never a published reader page. Existing counters retain their meaning: `posts` counts posts. `pages` counts **all generated HTML documents**, not only static pages. `photos` counts actual copied input images. Added fields are:

- `static_pages`: supplied records of type `page`.
- `routes`: a sorted array of **every generated root-relative URI**, including `/`, record routes, all index/pagination routes, and `/404.html`. Routes do not include the optional project prefix; CI joins them to `base_path`. Unicode record URI spellings remain percent-encoded exactly as supplied. Every route maps to exactly one generated HTML document, and the offline audit verifies coverage.
- `record_routes`: an object mapping **string IDs for all supplied records** to their encoded root-relative routes, without the project prefix. This is also the JavaScript translator map.
- `unknown_legacy_ids`: source-record `page`, original/localized `target`, decoded ID `parameters`, and `reason` (`unknown` or `invalid`). Record bodies render once, so home duplication does not duplicate this evidence.
- `external_links`: distinct emitted/body external URLs with their offline `status` and source/generated `pages`. Suppressed dead body/template links are included as evidence, never reader-facing notes. This is a rendering inventory, not a crawl of source/provenance URLs.
- `unverified_external_urls`: sorted distinct external URLs in that inventory without a supplied live/dead verdict, including explicitly unverified entries. No liveness claim is made.
- `asset_review`: actual asset count, `rights_checked` and `image_provenance_checked` booleans, separate lab/theme image counts, and input SHA-256 values.

`unrecovered_links` and `missing_images` remain separate arrays. The home repeats post bodies. Unresolved-link evidence is attributed to the record route, not the home. Known-dead links are not unrecovered local navigation. Audit filesystem lookups use the same strict one-decode mapping as file writes, including for encoded Unicode routes at project prefixes.

## GitHub Actions verification only

Do not build or serve this site locally. Local syntax checks do not import/run the builder or execute build-invoking tests. Add/maintain regression fixtures in `tests/test_build.py`, then exercise them in GitHub Actions.

`build.yml` has read-only permissions and no deploy step or secrets. On Python 3.13 CI runs pinned dependencies/unit tests, offline compilation/audit for both root and project prefixes, offline provider inventories, and sharded Chromium checks with every nonlocal resource request blocked. Browser verification must visit **every `routes` entry** at both widths and with JavaScript off, inspect record artwork decoding and overflow, and exercise all-record legacy IDs. No hero artwork is required when none was exported. Separate provider checks make no playback, captions, viewing, or reuse claim. Rejected requests/transport failures remain inconclusive.

The main preview artifact contains `_site/`, `build-report.json`, the offline video inventory and a deterministic route plan. Eight separate browser artifacts contain every route capture, per-mode status manifest, errors and a navigable review index. Artifacts upload even when a step fails. Reports remain outside `_site/`. Passing CI does not authorize merging or deployment. Workflow/provider/browser implementation belongs to its separate review. The route metadata contract above is the builder's integration interface.

## Project-site builds and deployment

GitHub Pages project sites live at `https://<owner>.github.io/<repo>/`. `python scripts/build.py --base-path /<repo>` prefixes every local root-relative `href`/`src` and the ID translator, while `--check-only --base-path /<repo>` audits them. Without the option, output serves a domain root. The browser-test server answers only under the selected prefix so escaping URLs fail. Canonical addresses and the report's `routes`/`record_routes` remain original domain-root URIs.

### Binding a custom domain

A `CNAME` file at the repository root switches both workflows to the domain-root build. It must contain exactly this archive's own host (`steveonjava.com` or `nighthacking.tv`), and the build rejects anything else, including a symlink. GitHub ignores `CNAME` for workflow deployments, so the file does not bind the domain. The domain is set in the repository's Pages settings by the owner. Add the file in the same change that the owner makes the setting, never earlier, because a root-path build served under `/<repo>/` has no working stylesheet or links. Without the file, the build keeps the `/<repo>/` prefix. A build with both a `CNAME` file and `--base-path` is rejected.

The separate `pages.yml` runs only on `main` or explicit manual dispatch. Its build job is read-only, with `pages: write` and `id-token: write` granted only to the deploy job. Feature-branch PRs only produce review artifacts. Merge and publication require owner approval independently of branch preparation.
