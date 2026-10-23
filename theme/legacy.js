"use strict";
(() => {
  const posts = Object.freeze(__POST_MAP__);
  const params = new URLSearchParams(window.location.search);
  if (!params.has("p")) return;
  const ids = params.getAll("p");
  const status = document.getElementById("legacy-status");
  const id = ids[0];
  if (ids.length !== 1 || !/^[1-9][0-9]{0,9}$/.test(id)) {
    status.textContent = "This legacy post ID is invalid. Browse the archive list instead.";
    return;
  }
  if (!Object.prototype.hasOwnProperty.call(posts, id)) {
    status.textContent = "This post ID is not included in this prototype. Browse the archive list instead.";
    return;
  }
  const path = posts[id];
  if (!/^\/[a-z0-9]+(?:-[a-z0-9]+)*\/$/.test(path)) return;
  window.location.replace(path);
})();
