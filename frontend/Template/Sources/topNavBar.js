(function () {
  // 1. Work out the site root from this script's own URL.
  //    (document.currentScript only works here at the top level, not in callbacks.)
  var script = document.currentScript;
  //    The script lives in Template/Sources/, so the pages are one folder up.
  var SITE_ROOT = new URL('../', script.src);

  function link(path) {
    return new URL(path, SITE_ROOT).href;
  }
  //gets the theme if its in dark or light mode
  var THEME_KEY = 'tlc-theme';

  function getSavedTheme() {
    try {
      return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light';
    } catch (e) {
      return 'light'; // some browsers block localStorage on file://
    }
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) {}
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  applyTheme(getSavedTheme());

  // 3. Page links in the middle of the top bar, in order.
  var PAGES = [
    { label: 'Home', path: 'home.html' },
    { label: 'T Level', path: 'TLevel.html' },
    { label: 'Advice', path: 'advice.html' },
    { label: 'FAQ', path: 'faqs.html' },
    { label: 'Contact', path: 'contact.html' }
  ];

  //checking if the links have loaded on the page
  function isCurrent(href) {
    return new URL(href).pathname === location.pathname;
  }

  //gets the active page to be able to underrline it in the nav bar
  function currentAttrs(href) {
    return isCurrent(href) ? { cls: ' active', aria: ' aria-current="page"' } : { cls: '', aria: '' };
  }

  function navLink(label, path) {
    var href = link(path);
    var cur = currentAttrs(href);
    return '<a class="nav-link' + cur.cls + '" href="' + href + '"' + cur.aria + '>' + label + '</a>';
  }

  // the button for switch mode from dadrk to light
  function updateToggle(btn) {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.textContent = isDark ? 'Light mode' : 'Dark mode';
    btn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
    btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
  }

  //this actualy renders the bars
  function buildNav() {
    var signinHref = link('signin.html');
    var signin = currentAttrs(signinHref);

    var html =
      '<header class="site-header">' +
        '<nav class="nav-top" aria-label="Main">' +
          '<a class="brand" href="' + link('home.html') + '">T Level Connect</a>' +
          '<button type="button" class="nav-toggle" aria-expanded="false" aria-controls="nav-collapsible" aria-label="Menu">\u2630</button>' +
          '<div class="nav-collapsible" id="nav-collapsible">' +
            '<div class="nav-links">' +
              PAGES.map(function (p) { return navLink(p.label, p.path); }).join('') +
            '</div>' +
            '<div class="nav-right">' +
              '<form class="nav-search" role="search">' +
                '<input type="search" name="q" placeholder="Search" aria-label="Search the site">' +
                '<button type="submit">Search</button>' +
              '</form>' +
              '<a class="signin-btn' + signin.cls + '" href="' + signinHref + '"' + signin.aria + '>Sign in</a>' +
            '</div>' +
          '</div>' +
        '</nav>' +
        '<nav class="nav-second" aria-label="Accessibility and display">' +
          '<div class="nav-second-right">' +
            navLink('Accessibility', 'accessibility.html') +
            '<button type="button" class="theme-toggle"></button>' +
          '</div>' +
        '</nav>' +
      '</header>';

    document.body.insertAdjacentHTML('afterbegin', html);

    // Ask the Flask server if someone is signed in; if so, turn "Sign in" into "Account".
    // (Fails quietly when the page is opened as a file, so the button stays "Sign in".)
    fetch(link('api/session'), { credentials: 'same-origin' })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data || !data.signed_in) return;
        var btn = document.querySelector('.signin-btn');
        var accountHref = link('account');
        var cur = isCurrent(accountHref);
        btn.href = accountHref;
        btn.textContent = 'Account';
        btn.classList.toggle('active', cur);
        if (cur) {
          btn.setAttribute('aria-current', 'page');
        } else {
          btn.removeAttribute('aria-current');
        }
      })
      .catch(function () {});

    // Search is not working yet: stop the form from reloading the page.
    document.querySelector('.nav-search').addEventListener('submit', function (e) {
      e.preventDefault();
      // TODO: add real search here (read e.target.q.value).
    });

    // Light / dark mode toggle.
    var toggle = document.querySelector('.theme-toggle');
    updateToggle(toggle);
    toggle.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      saveTheme(next);
      updateToggle(toggle);
    });

    // Hamburger menu: collapses the links/search/sign-in group on narrow screens.
    var navToggle = document.querySelector('.nav-toggle');
    var navCollapsible = document.getElementById('nav-collapsible');

    function closeNavMenu() {
      navCollapsible.classList.remove('nav-collapsible--open');
      navToggle.setAttribute('aria-expanded', 'false');
    }

    function openNavMenu() {
      navCollapsible.classList.add('nav-collapsible--open');
      navToggle.setAttribute('aria-expanded', 'true');
    }

    navToggle.addEventListener('click', function () {
      if (navToggle.getAttribute('aria-expanded') === 'true') {
        closeNavMenu();
      } else {
        openNavMenu();
      }
    });

    // Close the menu on Escape.
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && navToggle.getAttribute('aria-expanded') === 'true') {
        closeNavMenu();
      }
    });

    // Close the menu once a link inside it is followed.
    navCollapsible.addEventListener('click', function (e) {
      if (e.target.closest('a')) closeNavMenu();
    });
  }

  //build the nav once the page's HTML has loaded.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildNav);
  } else {
    buildNav();
  }
})();
