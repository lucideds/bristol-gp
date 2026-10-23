// Advice page: highlights the side nav link for the section in view,
// and wires the "Ask a question" button to the chat widget (chatWidget.js).
(function () {
  function init() {
    var links = Array.prototype.slice.call(document.querySelectorAll('.advice-nav a[href^="#"]'));
    var sections = links.map(function (link) {
      return document.getElementById(link.getAttribute('href').slice(1));
    });

    function mark(index) {
      links.forEach(function (link, i) {
        if (i === index) {
          link.setAttribute('aria-current', 'true');
        } else {
          link.removeAttribute('aria-current');
        }
      });
    }

    // The current section is the last one whose top has scrolled past a third of the screen.
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
      mark(current);
    }

    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();

    // The chat button only works with JavaScript, so it starts hidden.
    var ask = document.querySelector('[data-open-chat]');
    if (ask) {
      ask.hidden = false;
      ask.addEventListener('click', function () {
        var toggle = document.querySelector('.chat-toggle');
        if (toggle && toggle.getAttribute('aria-expanded') !== 'true') toggle.click();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
