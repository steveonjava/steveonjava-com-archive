# Full-content conversion review

This batch contains 143 published posts and 4 static pages, preserving 2008-12-06 through 2019-12-11 post dates. The input set includes the two earlier prototype posts, so it adds 141 posts and 4 static pages rather than duplicating them.

## Conversion and source boundaries

The converter rechecked every source row as published and non-password-protected inside the isolated lab. Only inert JSON, Markdown and freshly reencoded JPEG/PNG pixels were exported. The received bundle contains 1431 regular files across both sites. Its SHA-256 is `7545a2de6a3808f031d3592f1e8891334a8220ce23e701a5399ae3116b657c33`. Host validation checked every record hash, image hash, decoded dimensions and metadata removal before staging.

Comments, users, form submissions, booking data, private/draft/password-protected records, executable site code, PDFs, GIFs/animation, unpublished-parent images and orphan media remain excluded. `2016/04/DSC00151.jpg` remains withheld. Static text on the selected public pages is retained, but forms, upload controls, players and maps are not restored. Prior generated home/video/category navigation replaces the old CMS-only endpoints rather than republishing them as working features.

Original titles, dates and wording were not rewritten. The decoder preserves valid UTF-8, explicitly normalizes legacy nonbreaking spaces, and uses a fixed Windows-1252 error-byte repertoire established from bounded source diagnostics. Every such conversion is recorded in per-record warnings. Unknown undecodable bytes remain reported replacement characters. This site has 0 records with unknown encoding losses and 26 records with explicitly decoded known legacy bytes, with details in `bulk-coverage.json` and each record's warnings. No replacement wording was invented. Removal and omission notes stay in repository metadata, never rendered as archive caveats.

## Media and rights

This site's converted set contains 199 selected, hash-screened images. Every staged raster has a rights entry. Safe historical upload paths remain unchanged, while source filenames containing unsupported output characters are mapped to dated safe filenames. Each mapping is recorded as `source_path` and `path` in the recovery manifest. Existing approved theme artwork is preserved.

Rights remain owner-asserted and unreviewed, not independently cleared. Omission reasons and outbound hosts are in `recovery-manifest.json`, and aggregate coverage is in `bulk-coverage.json`.

## Links and video identities

No new external URL, thumbnail URL or provider endpoint was fetched. Newly inventoried destinations are `unverified` and must not be described as available. The existing dated link checks remain separate evidence, and their known-dead decisions remain intact. Rendering uses local files and nofollow external links, not network availability.

NightHacking now has 307 exact recording IDs, comprising 298 metadata-derived IDs and nine explicit author-body URL resolutions. Nine player-settings records omit an ID in their metadata, but the existing public author bodies and source-text inventories contain exact unique recording URLs. Those nine IDs were resolved offline and their unchanged Markdown hashes and original export JSON hashes are recorded in `video-identity-resolutions.json`. This does not establish playback availability. Normal CI is offline and any future provider checks need an explicit approved-ID list and separate permission.

One SteveOnJava source post retains its original public Stratus program contact address. It is author-published program contact prose, not recovered account or comment data. The text and metadata scan found no credential or private-host-path patterns. The apparent active-markup hit in post 3812 is Java generic syntax inside a fenced source example, not active HTML.

## Review and publication

Both existing themes, canonical domains and robots policy remain unchanged. `noindex,nofollow` stays in place, and indexing still requires a separate decision. DNS, TLS, Pages settings, branch protection and deployments were not changed by this conversion. Merging and publication require the owner's review and approval.

CI must validate every record and generated route, both desktop/mobile views, no-JavaScript browsing, local assets, legacy IDs, nested pages, encoded historical slugs and paginated collections. Build and browser reports belong in review artifacts outside the published site. The actual Actions results and screenshot review are reported in the pull request, not inferred from this document.
