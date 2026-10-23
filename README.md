# SteveOnJava archive (prototype)

A read-only static rebuild of **steveonjava.com**, a site that ran on WordPress and was later compromised. Text and a small set of cleared images were exported from a forensic copy of the old site. The pages here are rebuilt from that export by a Python script. Nothing is copied from the old theme, plugins or database.

**Status: prototype, unreviewed.** This repository has no deploy workflow, GitHub Pages is not enabled, and every page carries `noindex,nofollow`. steveonjava.com does not serve this build.

## What is in the prototype

Two recovered posts: JavaFX 2.0 With Alternative Languages at the SvJugFx (2010-10-14) and JavaFX 2.0 at the Chennai JUG (2011-02-21). Every record is labelled `unreviewed`. The wording, dates and images are exactly what the export produced, so errors in the originals remain.

## What is deliberately not here

- Comments and user data
- Drafts, private and password-protected posts
- Executable code, plugins and theme code of the old site
- Original image files (the export re-encodes the pixels without metadata)
- Material from the old subdomains (the owner chose to ignore them)
- A transcript or copy of any video. Video posts link to YouTube.

## How it is built and checked

GitHub Actions only (`.github/workflows/build.yml`, read-only permissions, no secrets, actions pinned to commit hashes). It runs the unit tests, builds the site, audits links, drives a headless browser through the pages (including with JavaScript off) and uploads a 7-day preview artifact. See `docs/BUILD.md` for the input format.

## Records kept next to the content

- `recovery-manifest.json`: which posts and images the export contains, with hashes and what was excluded
- `rights.json`: one rights entry per image. Every entry is "owner-asserted, unreviewed" until a person clears it.
- `link-status.json` and `docs/link-checks.md`: the external link and video checks, with date and method
- `AGENTS.md`: the rules for any agent that works on this repository

Part of the work to rebuild Stephen Chin's public record around [stephenchin.com](https://stephenchin.com).
