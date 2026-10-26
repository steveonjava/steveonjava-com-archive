# SteveOnJava archive

A read-only static rebuild of **steveonjava.com**, preserving 143 published posts and 4 static pages from Stephen Chin's historical WordPress site. Post dates range from 2008-12-06 through 2019-12-11. Recovered text keeps the original wording, subject to the documented sanitizer and encoding losses.

Records remain unreviewed, and every rendered page retains `noindex,nofollow`. Full content conversion, source verification, rights clearance, merge approval, deployment and public indexing are separate gates.

## Content and evidence

- `content/`: inert JSON metadata and Markdown, including source hashes and conversion warnings.
- `assets/`: approved raster images decoded and reencoded without inherited metadata.
- `recovery-manifest.json`: source coverage, transformed image hashes, omissions and the offline outbound-host inventory.
- `rights.json`: one rights entry per raster, with owner-asserted rights explicitly distinguished from independent clearance.
- `link-status.json` and `docs/link-checks.md`: current offline review state and previous dated checks.
- `docs/bulk-review.md` and `docs/bulk-coverage.json`: batch scope, exclusions, encoding gaps and review boundaries.
- `docs/BUILD.md`: input schema, offline builder and CI review workflow.
- `AGENTS.md`: repository rules.

Comments, personal-data tables, drafts, private/password-protected material, form submissions, booking data, source executables and original image bytes are excluded. Third-party videos are linked, not copied or transcribed. Missing media and source losses are recorded in review metadata rather than on-page notices.

Builds and browser verification run in GitHub Actions. PR workflows are read-only and artifact-only, while the separate approved main-branch workflow handles Pages publication. Production changes require a reviewed PR. Content work does not authorize changes to domains, TLS, Pages settings or public indexing.

Part of Stephen Chin's public professional archive around [stephenchin.com](https://stephenchin.com).
