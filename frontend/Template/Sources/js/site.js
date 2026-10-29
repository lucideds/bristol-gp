// Helpers shared by the nav bar, footer and chat widget. Loaded with defer, before them.
(function () {
  // This script lives in Template/Sources/js/, so the site root is two folders up.
  // (document.currentScript only works here at the top level, not in callbacks.)
  var ROOT = new URL('../../', document.currentScript.src);

  window.TLC = {
    // A full URL for a path on this site, e.g. link('t-levels#media') or link('api/chat').
    link: function (path) {
      return new URL(path, ROOT).href;
    },
    // True if the link points at the page being shown (used for aria-current).
    isCurrent: function (href) {
      return new URL(href, location.href).pathname === location.pathname;
    }
  };
})();
