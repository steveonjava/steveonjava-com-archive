# Rules for agents working in this repository

This is the SteveOnJava (steveonjava.com) archive. It is a read-only record of one old site, built from reviewed exports. Read `README.md` and `docs/BUILD.md` first.

## Hard rules

1. **Every change goes through a pull request.** Never push to `main`, merge, deploy, change Pages, DNS or registrar settings, or alter branch rules or repository settings without the owner's explicit instruction.
2. **Public sources and sanitised exports only.** Do not add comments, user data, drafts, private posts, original image bytes, executable code or anything from the old site's plugins or theme.
3. **The owner's voice is not yours.** Recovered posts keep their original wording and carry an `unreviewed` label. Do not write first-person memories or reflections for Stephen, and do not rewrite recovered posts.
4. **No video copying or transcription** (no yt-dlp, no speech-to-text) for anything published. Video posts link out.
5. **Every image needs an entry in `rights.json`.** A new asset without a rights entry is a failed review. Public availability is not permission.
6. **Check links before rendering them.** Record each external URL as `live`, `dead` or `unverified` in `link-status.json`, with the date and method in the pull request. Dead and hijacked links render as plain text.
7. **The build never fetches anything.** No network access during `scripts/build.py`. Provider outages must not change the output.
8. **`noindex,nofollow` stays** until the owner approves a separate launch pull request.
9. **No secrets, ever.** Do not copy tokens or keys into the repository, issues or pull request text.
10. **Say what you did not verify.** A pull request lists what was checked, how, and what remains unchecked.

## Verify before asking for review

CI runs the tests, the build, the audit and the browser checks. Locally, use a clean Python 3.13 environment with `requirements-preview.txt` and run `python -m unittest discover -s tests`, then `python scripts/build.py`.
