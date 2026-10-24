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

## Deliberate functional differences

The reconstruction keeps the old visual structure but does not revive comment forms, login widgets, tracking, a live Twitter feed, or an automatically loaded player. Available content determines navigation, so there are no fake historical menu destinations. A video thumbnail and simple watch link occupy the video stage without contacting YouTube during page load. Mobile widths reflow instead of reproducing the old layout's overflow.

Review state, recovery qualifications, image-rights questions and verification limits stay in Git and PR discussion, not in reader pages or page metadata. Source prose is not rewritten. A separate CI oEmbed check reports public metadata accessibility without claiming playback, viewing or reuse permission.
