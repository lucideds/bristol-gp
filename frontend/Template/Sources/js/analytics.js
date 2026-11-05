// Analytics dashboard: sizes the chart bars. The Content Security Policy blocks style=""
// attributes in the HTML, so the server puts each bar's length (0 to 100, relative to the
// biggest bar in its chart) in data-length and this copies it into --bar-length. analytics.css
// uses it as a width or a height. Without JavaScript the bars stay empty and the numbers still show.
document.querySelectorAll('.analytics-bar-fill[data-length]').forEach(function (bar) {
  bar.style.setProperty('--bar-length', bar.getAttribute('data-length') + '%');
});
