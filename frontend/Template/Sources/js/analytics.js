// Analytics dashboard. Loaded with defer, so the page's HTML is ready when this runs.
(function () {
  // The Content Security Policy blocks style="" attributes in the HTML, so the server puts each
  // bar's length (0 to 100, relative to the biggest bar in its chart) in data-length and this copies
  // it into --bar-length, which analytics.css uses as a width or a height. Without JavaScript the
  // bars stay empty and the numbers still show. The donut charts are SVG and need no script.
  document.querySelectorAll('.analytics-bar-fill[data-length]').forEach(function (bar) {
    bar.style.setProperty('--bar-length', bar.getAttribute('data-length') + '%');
  });

  // Marks the section nav link for the section in view, as the Advice page does.
  var links = Array.prototype.slice.call(document.querySelectorAll('.analytics-nav a[href^="#"]'));
  var sections = links.map(function (link) {
    var heading = document.getElementById(link.getAttribute('href').slice(1));
    return heading && heading.closest('section');
  });

  function update() {
    var line = window.innerHeight / 3;
    var current = 0;
    sections.forEach(function (section, i) {
      if (section && section.getBoundingClientRect().top <= line) current = i;
    });
    // At the bottom of the page, the last section may never reach the line.
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
      current = sections.length - 1;
    }
    links.forEach(function (link, i) {
      if (i === current) {
        link.setAttribute('aria-current', 'true');
      } else {
        link.removeAttribute('aria-current');
      }
    });
  }

  if (links.length) {
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();
  }
})();
