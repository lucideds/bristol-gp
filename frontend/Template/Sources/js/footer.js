(function () {
  var script = document.currentScript;
  var SITE_ROOT = new URL('../../', script.src);

  function link(path) {
    return new URL(path, SITE_ROOT).href;
  }

  function isCurrent(href) {
    return new URL(href).pathname === location.pathname;
  }

  // Adds the footer with the privacy link to the end of the page.
  function buildFooter() {
    var privacyHref = link('privacy.html');
    var aria = isCurrent(privacyHref) ? ' aria-current="page"' : '';

    var html =
      '<footer class="site-footer">' +
        '<a href="' + privacyHref + '"' + aria + '>Privacy</a>' +
      '</footer>';

    document.body.insertAdjacentHTML('beforeend', html);
  }

  // Build the footer once the page's HTML has loaded.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildFooter);
  } else {
    buildFooter();
  }
})();
