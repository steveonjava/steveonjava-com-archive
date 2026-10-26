# Link and video checks

## External links in the two posts

Checked on 2026-10-23 at 08:03 UTC with the owner's one-time exception, by a script that resolves names over DNS-over-HTTPS, pins the resolved public address, fetches one page per URL with curl (no cookies, no JavaScript, no rendering, 400 KB cap) and reads only the title. Results are recorded in `link-status.json`.

- `http://visage-lang.org/`: dead. No DNS record. Rendered as plain text.
- `http://www.svjugfx.org/calendar/14264038/`: dead. No DNS record. Rendered as plain text.
- `http://www.google.com/moderator/...`: dead. Google Moderator now redirects to a Google Search Help page. Rendered as plain text.
- `http://www.jugchennai.in/2011/02/20/...`: dead for this purpose. The domain redirects through three hops to an unrelated betting site. Rendered as plain text, because linking there would send readers to it.
- `http://tenthplanet.in/`: live (HTTP 200). A reachable address does not prove the same people run it as in 2011. Stays clickable with `nofollow noopener noreferrer`.
- `http://www.slideshare.net/steveonjava/javafx-20-and-alternative-languages`: unverified. SlideShare answered with a bot-check page. Stays clickable.
- `http://twitter.com/rajmahendra`: unverified. The check returned HTTP 520. Stays clickable.

Videos: none in these two posts.


## Bulk conversion: offline inventory

The content-expansion batch inventories all exported source destinations without fetching them. Newly added URLs are unverified. Known-dead results above are retained, and normal CI makes no provider requests. No current availability, ownership or playback claim is inferred from a syntactically valid URL or video ID. See `bulk-review.md` and `bulk-coverage.json`.
