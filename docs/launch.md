# Launch record

The owner directed the launch of `steveonjava.com` on 2026-10-28. The launch pull request sets `status` to `launched` in `archive.json`; merging it is the owner's approval.

## What changed

- Every page carries `<meta name="robots" content="index,follow">` instead of `noindex,nofollow`.
- The build publishes `/robots.txt` and `/sitemap.xml`.
- Links to other sites keep `rel="nofollow noopener noreferrer"`.
- Content, routes, images and theme are unchanged.

## Rights position

The owner treats this site as an archive and as fair use, and has decided that no further rights review will be done. `rights.json` is unchanged: it still holds one entry per image with the status recorded when the image was added (`unreviewed` or `owner-asserted, unreviewed`). No entry was upgraded to cleared, and the build still requires an entry for every image. The owner's position is recorded here as stated; this file makes no legal claim of its own.

## Reverting

Set `status` back to `prototype` in a pull request. The next build restores `noindex,nofollow` and publishes neither `robots.txt` nor `sitemap.xml`. Search engines that have already indexed pages drop them only when they next crawl the site.
