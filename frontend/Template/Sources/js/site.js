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

  // Lands a new page at the top, or at its #section. The browser can scroll to a
  // #section before our scripts change the layout (the T Levels tabs hide every
  // other route, the header and footer are added), and some mobile browsers keep
  // the old page's scroll during the page fade. Both left visitors at the bottom
  // of the next page. DOMContentLoaded runs after every deferred script, and load
  // after images, so the layout is final by then.
  // Back, forward and reload keep the scroll position the browser restores.
  var userMoved = false;
  function stop() { userMoved = true; }
  ['wheel', 'touchstart', 'keydown'].forEach(function (type) {
    window.addEventListener(type, stop, { once: true, passive: true });
  });
  function land() {
    if (userMoved) return;
    var nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
    if (nav && nav.type !== 'navigate') return;
    var id = decodeURIComponent(location.hash.slice(1));
    var target = id ? document.getElementById(id) : null;
    if (id && !target) return;
    // Jump rather than glide: motion.css turns on smooth scrolling.
    var html = document.documentElement;
    html.style.scrollBehavior = 'auto';
    if (target) {
      target.scrollIntoView();
    } else {
      window.scrollTo(0, 0);
    }
    html.style.scrollBehavior = '';
  }
  document.addEventListener('DOMContentLoaded', land);
  window.addEventListener('load', land);
})();
