(function () {
  var script = document.currentScript;
  var SITE_ROOT = new URL('../../', script.src);

  function link(path) {
    return new URL(path, SITE_ROOT).href;
  }

  function isCurrent(href) {
    return new URL(href).pathname === location.pathname;
  }

  // Footer link columns. A null path is a placeholder until the page exists.
  var COLUMNS = [
    { heading: 'Explore', links: [
      { label: 'T Levels', path: 'TLevel.html' },
      { label: 'Placements', path: null },
      { label: 'Resources', path: 'advice.html' }
    ] },
    { heading: 'Help', links: [
      { label: 'Accessibility statement', path: null },
      { label: 'Privacy notice', path: 'privacy.html' },
      { label: 'Contact us', path: 'contact.html' }
    ] }
  ];

  function footerLink(item) {
    if (!item.path) return '<li><a href="#">' + item.label + '</a></li>';
    var href = link(item.path);
    var aria = isCurrent(href) ? ' aria-current="page"' : '';
    return '<li><a href="' + href + '"' + aria + '>' + item.label + '</a></li>';
  }

  function footerColumn(col, i) {
    var id = 'footer-heading-' + i;
    return (
      '<nav class="footer-col" aria-labelledby="' + id + '">' +
        '<h2 class="footer-heading" id="' + id + '">' + col.heading + '</h2>' +
        '<ul class="footer-links">' + col.links.map(footerLink).join('') + '</ul>' +
      '</nav>'
    );
  }

  // Adds the footer to the end of the page.
  function buildFooter() {
    var html =
      '<footer class="site-footer">' +
        '<div class="footer-inner">' +
          '<div class="footer-top">' +
            '<div class="footer-brand">' +
              '<img src="' + link('Sources/assests/amazon_logo.png') + '" alt="T Level placements at Amazon" width="150" height="70">' +
              '<p class="footer-tagline">Information, advice and support for T Level students.</p>' +
            '</div>' +
            COLUMNS.map(footerColumn).join('') +
          '</div>' +
          '<p class="footer-bottom"></p>' +
        '</div>' +
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
