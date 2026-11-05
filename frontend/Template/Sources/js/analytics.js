// Analytics dashboard. Loaded with defer, so the page's HTML is ready when this runs.
(function () {
  // The Content Security Policy blocks style="" attributes in the HTML, so the server puts each
  // bar's length (0 to 100, relative to the biggest bar in its chart) in data-length and this copies
  // it into --bar-length, which analytics.css uses as a width or a height. Without JavaScript the
  // bars stay empty and the numbers still show. The donut charts are SVG and need no script.
  document.querySelectorAll('.analytics-bar-fill[data-length]').forEach(function (bar) {
    bar.style.setProperty('--bar-length', bar.getAttribute('data-length') + '%');
  });
})();
