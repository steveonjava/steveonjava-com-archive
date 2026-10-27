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


## Owner-approved external link check, 2026-10-27

The owner approved one online check of 511 external URLs taken from the two archives' build reports. Each request resolved the name over DNS-over-HTTPS, pinned a public address, re-validated every redirect hop, read only the page title and capped the body. YouTube addresses were not fetched; they went to the public oEmbed metadata endpoint only. The counts were 206 working, 111 dead and 194 inconclusive.

Four `www.sfandroid.org` URLs in posts 1763 and 1774 now redirect to an online-gambling site on an unrelated domain. At the owner's direction the group's event link, which appears once in each post, now points to the group's current Meetup page, `https://www.meetup.com/sfandroid/`, marked `live` in `link-status.json`. That page was read once and describes a San Francisco Android developer group. The old event page no longer exists, so the link goes to the group rather than to that event. The three member-profile links in post 1763 name individual people, so they are marked `dead`; the build renders their link text as plain text and never emits the address. The other 107 dead results and the 194 inconclusive ones are not changed by this commit. Two further original project sites, `www.lejos.org` and `fest.easytesting.org`, now redirect within their own domains to pages titled as online gambling, which suggests the domains were taken over; that rests on page titles only. At the owner's direction the leJOS link in post 4995 now points to `https://lejos.sourceforge.io/` and the FEST link in post 515 to `https://github.com/easytesting/fest-assert-core`. Both new addresses were read once and describe the same projects; they are marked `live` in `link-status.json`. The FEST wiki link in post 729 has no equivalent target, so it is marked `dead` and renders as plain text.

## Bulk conversion: offline inventory

The content-expansion batch inventories all exported source destinations without fetching them. Newly added URLs are unverified. Known-dead results above are retained, and normal CI makes no provider requests. No current availability, ownership or playback claim is inferred from a syntactically valid URL or video ID. See `bulk-review.md` and `bulk-coverage.json`.
