"use strict";
(() => {
  // Includes posts AND static pages; only the offline validator supplies routes.
  const posts = Object.freeze(__POST_MAP__);
  const base = __BASE_PATH__;
  const params = new URLSearchParams(window.location.search);
  const ids = [...params.getAll("p"), ...params.getAll("page_id")];
  if (!ids.length) return;
  const status = document.getElementById("legacy-status");
  const id = ids[0];
  if (ids.length !== 1 || !/^[1-9][0-9]{0,9}$/.test(id) || Number(id) > 2147483647) {
    status.textContent = "This legacy ID is invalid. Browse the archive list instead.";
    return;
  }
  if (!Object.prototype.hasOwnProperty.call(posts, id)) {
    status.textContent = "Page not found. Browse the archive list instead.";
    return;
  }
  const path = posts[id];
  // Do not let a malformed map become a redirect primitive. Encoded bytes must
  // be non-ASCII UTF-8, never slash, dot, percent, whitespace/control escapes,
  // double decoding, a query, or a second authority. Preserve the URI spelling.
  if (typeof path !== "string" || path.length > 4096 || !path.startsWith("/") || !path.endsWith("/")) return;
  const parts = path.slice(1, -1).split("/");
  const reserved = new Set(["archive", "category", "videos", "pages", "page", "assets", "wp-content", "404", "index"]);
  if (parts.length > 16 || reserved.has(parts[0])) return;
  for (const part of parts) {
    if (!/^(?:[a-z0-9]|%[0-9a-fA-F]{2})+(?:-(?:[a-z0-9]|%[0-9a-fA-F]{2})+)*$/.test(part)) return;
    if ([...part.matchAll(/%([0-9a-fA-F]{2})/g)].some(match => parseInt(match[1], 16) < 128)) return;
    let decoded;
    try {
      decoded = decodeURIComponent(part);
    } catch (_) {
      return;
    }
    if (new TextEncoder().encode(decoded).length > 255 || /[\p{C}]/u.test(decoded) || /[^\S\u3000]/u.test(decoded)) return;
  }
  window.location.replace(base + path);
})();
