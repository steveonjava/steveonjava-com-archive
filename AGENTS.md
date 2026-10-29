# Rules for agents working in this repository

This is the SteveOnJava (steveonjava.com) archive. It is a read-only record of one old site, built from reviewed exports. Read `README.md` and `docs/BUILD.md` first.

## Hard rules

1. **Every change goes through a pull request.** Never push to `main`, merge, deploy, change Pages, DNS or registrar settings, or alter branch rules or repository settings without the owner's explicit instruction.
2. **Public sources and sanitised exports only.** Do not add comments, user data, drafts, private posts, original image bytes, executable code or the old site's plugins, theme code or stylesheets. Historical upload artwork may be added only as reencoded local pixels with source and rights records.
3. **The owner's voice is not yours.** Recovered posts keep their original wording. Review states stay in JSON, commit messages and PR text, never reader-facing labels or caveats. Do not write first-person memories or reflections for Stephen, and do not rewrite recovered posts.
4. **No video copying or transcription** (no yt-dlp, no speech-to-text) for anything published. Video posts link out.
5. **Every image needs an entry in `rights.json`.** A new asset without a rights entry is a failed review. Public availability is not permission.
6. **Check links before rendering them.** Record each external URL as `live`, `dead` or `unverified` in `link-status.json`, with the date and method in the pull request. Dead and hijacked links render as plain text.
7. **The build never fetches anything.** No network access during `scripts/build.py`. Provider outages must not change the output.
8. **Indexing follows `archive.json`.** `status: launched` makes pages indexable and publishes `robots.txt` and `sitemap.xml`; `prototype` restores `noindex,nofollow`. Do not change the status without the owner's explicit instruction. See `docs/launch.md`.
9. **No secrets, ever.** Do not copy tokens or keys into the repository, issues or pull request text.
10. **Say what you did not verify.** A pull request lists what was checked, how, and what remains unchecked.

## Verify before asking for review

GitHub Actions runs tests, offline builds, audits and browser checks. Build review artifacts there, not with a local server. Check every supplied post at desktop and mobile widths, confirm images decode, and inspect the screenshots before asking for review. Never require a prototype banner in tests. Match the original themes by inspecting rendered public references and authoring fresh CSS, not copying old stylesheets.
