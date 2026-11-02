// The site footer. Loaded with defer after site.js, so the page's HTML is ready when this runs.
(function () {
  var link = TLC.link;

  // Footer link columns. Add "Placements" and "Accessibility statement" here once those pages exist.
  var COLUMNS = [
    { heading: 'Explore', links: [
      { label: 'T Levels', path: 't-levels' },
      { label: 'Resources', path: 'advice#resources' }
    ] },
    { heading: 'Help', links: [
      { label: 'Privacy notice', path: 'privacy' },
      { label: 'Contact us', path: 'contact' }
    ] }
  ];

  function footerLink(item) {
    var href = link(item.path);
    var aria = TLC.isCurrent(href) ? ' aria-current="page"' : '';
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
              '<img src="' + link('Sources/assets/amazon_logo.png') + '" alt="T Level placements at Amazon" width="150" height="70">' +
              '<p class="footer-tagline">Information, advice and support for T Level students.</p>' +
            '</div>' +
            COLUMNS.map(footerColumn).join('') +
          '</div>' +
        '</div>' +
      '</footer>';

    document.body.insertAdjacentHTML('beforeend', html);
  }

  buildFooter();
})();
