// Advice page: highlights the side nav link for the section in view, runs the Your path year picker,
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

    initPath();

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

  // Your path: shows the year picker and marks the step for the chosen year with a
  // "You are here" label and aria-current="step". Without JavaScript the picker stays
  // hidden and the timeline still reads in full.
  function initPath() {
    var finder = document.querySelector('.path-finder');
    var status = document.querySelector('.path-status');
    var radios = Array.prototype.slice.call(document.querySelectorAll('input[name="path-year"]'));
    var steps = Array.prototype.slice.call(document.querySelectorAll('.path-step'));
    if (!finder || !status || !radios.length) return;

    // The step each year is at comes from data-year on the step
    function stepFor(year) {
      for (var i = 0; i < steps.length; i++) {
        if (steps[i].getAttribute('data-year') === year) return i;
      }
      return -1;
    }

    function mark(year) {
      steps.forEach(function (step) {
        step.removeAttribute('aria-current');
        var old = step.querySelector('.path-here');
        if (old) old.remove();
      });
      var index = stepFor(year);
      if (index === -1) return;
      var step = steps[index];
      step.setAttribute('aria-current', 'step');
      var badge = document.createElement('p');
      badge.className = 'path-here';
      badge.textContent = 'You are here';
      var body = step.querySelector('.path-step-body');
      body.insertBefore(badge, body.firstChild);

      var link = document.createElement('a');
      link.href = '#' + step.id;
      link.textContent = step.querySelector('h4').textContent;
      status.textContent = 'You are at step ' + (index + 1) + ': ';
      status.appendChild(link);
    }

    radios.forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (radio.checked) mark(radio.value);
      });
    });

    var checked = radios.filter(function (r) { return r.checked; })[0] || radios[0];
    finder.hidden = false;
    mark(checked.value);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
