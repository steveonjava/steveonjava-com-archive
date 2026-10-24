# Original theme references

These references were inspected as rendered public Wayback pages. No lab access or theme-code export was needed. The replacement stylesheet was authored from screenshots and computed visual measurements, not copied from the original CSS. This means the archive can reproduce the old visual identity without executing the old WordPress installation.

## SteveOnJava: Freshy 2

Reference: [June 2012 home capture](https://web.archive.org/web/20120609010313if_/http://steveonjava.com:80/). The inspected single-post capture was [JavaFX and HTML5 at JavaOne India](https://web.archive.org/web/20120609010313if_/http://javafx.steveonjava.com/javafx-and-html5-at-javaone-india/). That public page supplied a single-post layout reference, not subdomain content for republication.

At a 1280-pixel viewport, the visible frame is 880 pixels wide with a 10-pixel top margin, a 77-pixel title band, and a 200-pixel motorcycle-photo header (Source: home capture above). Those proportions determine the reconstruction, because a wide header and oversized type were the main departures in the first approximation.

Measured visual tokens (Source: the same rendered capture and screenshot pixels):

- Body stripe colors: `#373737` and `#404040`, broad diagonal bands.
- Shell gradient: white toward the left, `#ebebeb` at the right.
- Wordmark: Trebuchet/Arial fallback, 26.75px, regular italic, letter spacing -2px, `#3d3d3d`.
- Original tagline: "Hacking Java, JavaFX, and Flash with Agility", 12.16px bold italic, `#8d8d8d`.
- Header: the blue motorcycle and black leather scene, with an 80px dark navigation overlay at its lower edge.
- Nav: uppercase small sans-serif, white outline and glossy treatment, active slate `#627579`.
- Body: Arial/Verdana, 12.16px with 20.67px line height, `#232323`.
- Main/sidebar columns: 700px and 180px, including padding. Main text width is 660px.
- Post headings: Trebuchet/Arial fallback, 23.1px, regular, letter spacing -1px, navy `#002f7d`.
- Byline: 11px navy. Body links: slate `#627579`.
- Sidebar headings: 18.24px regular with a 2px slate left rule.
- Category box: white, 1px `#c6c6c6` border, 11px labels and bold black links.

### SteveOnJava home page

Measured from the June 2012 home capture (Source: the capture above, rendered at 1280 pixels):

- The home page is a river of the ten newest posts, each with its full body, byline and the bordered Comments/Categories/Tags box, followed by a "Previous Entries" pager. This is the largest departure of the first reconstruction, which listed two excerpts under a "Latest Posts" heading.
- Post paragraphs use an 8.5px vertical margin. A post's categories box is 31px tall for one line, with a 1px `#c6c6c6` border on white.
- The pager link is 12.16px slate `#627579`, placed under the last post at the left edge of the column.
- The title band carries an orange `#ee7700` italic "rss" link and a search box at the right. Neither is reproduced, because the feed and search no longer exist.
- Sidebar widgets, in order: Twitter button, location badge and Travel Map links (not reproduced), then Publications (two 75x99 book covers, 10px apart), Upcoming Talks (event badges, not reproduced because the events passed), "Steve On..." (a plain link list of category archives), Archives (a dropdown, rendered as the year list), Affiliations (Java Champions logo, 160x68), Awards (DZone MVB badge and the 2009 JavaOne Rock Star Duke) and Disclaimer.
- Widget headings share the 18.24px slate style with a 2px left rule. Widget bodies are 12px, with a 23px list line height.
- The footer is a 48px band at the bottom of the shell.

The motorcycle image is a separate historical upload, not a screenshot or stylesheet fragment. Its exact public capture and transformation are in `theme-art.json`. It is decoded and reencoded without inherited metadata before inclusion.

## NightHacking: Focus

References: [October 2019 home capture](https://web.archive.org/web/20191014201429if_/http://nighthacking.tv/) and [G1 GC with Kirk Pepperdine](https://web.archive.org/web/20191014200645if_/http://nighthacking.tv/g1-gc-with-kirk-pepperdine/).

The original uses a full-width dark header and video stage above a centered light content panel, rather than the boxed layout used by SteveOnJava (Source: both captures above). Separate page structures are needed to reproduce that distinction instead of giving both sites the same layout with different colors.

Measured visual tokens (Source: rendered captures above and screenshot pixels):

- Body: warm `#f6f4f2`, Helvetica Neue/Arial fallback, 13px with 19.5px line height, `#404040`.
- Header: 48px full-width gradient from `#181818` to `#212326`, centered 960px inner row.
- Branding: original 230x28 local raster logo, displayed near 214x26.
- Navigation: right-aligned, 12px light gray.
- Post stage: full-width `#070707`, with a centered 960px inner area.
- Post title: centered white 42px, light weight, 42px line height.
- Body card: white with a thin gray border, centered 960px width and 16px inset.
- Body/sidebar: about 648px and 248px with a 30px gap.
- Gallery: three equal desktop columns, about 301px thumbnails, 12px gutters and 15px row gaps.
- Card titles: centered 15px light white type over a translucent black band at the thumbnail's lower edge.
- Sidebar: 14px medium-weight headings and plain 13px dark-gray links.
- Footer: full-width `#2a2b2f`, about 70px high.

### NightHacking home page

Measured from the October 2019 home capture (Source: the capture above, rendered at 1280 pixels):

- A 777x437 featured stage sits directly under the 48px header on a `#1c1c1c` band that ends about 9px below the stage. The original was a live-stream embed, so the reconstruction uses the newest video's thumbnail as a local poster with a play button that links to the archive page.
- Below the stage the page returns to the warm `#f6f4f2` background. The original then showed a line of announcement text and a row of 320x165 event banners. Neither is reproduced, because the announcement is out of date and the banners are not in the export.
- The "Latest Videos" heading sits above the panel on the page background, left-aligned with it, in 18px light-weight type, color about `#2d3033`.
- The panel is 960px wide with a 1px light border and about 16px of padding. Thumbnails are 301x162 in three columns, with 12px column gaps and 15px row gaps.
- Fifteen videos appear per page, followed by an "Older posts" link at 13px `#404040`.
- The Follow button and the "Labs" menu item are not reproduced. Neither has a working destination.

## Deliberate functional differences

The reconstruction keeps the old visual structure but does not revive comment forms, login widgets, tracking, a live Twitter feed, or an automatically loaded player. Available content determines navigation, so there are no fake historical menu destinations. A video thumbnail and simple watch link occupy the video stage without contacting YouTube during page load. Mobile widths reflow instead of reproducing the old layout's overflow.

Review state, recovery qualifications, image-rights questions and verification limits stay in Git and PR discussion, not in reader pages or page metadata. Source prose is not rewritten. A separate CI oEmbed check reports public metadata accessibility without claiming playback, viewing or reuse permission.
