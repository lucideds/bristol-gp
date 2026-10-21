// T Level page: vertical tabs ("General info" plus one per route).
// Without JavaScript the tab list stays hidden and every section shows in order.
// The URL hash (#digital, #business, ...) picks the tab, so links like TLevel.html#media keep working.
(function () {
  function init() {
    var tablist = document.querySelector('.tlevel-tabs');
    if (!tablist) return;

    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    var panels = tabs.map(function (tab) {
      return document.getElementById(tab.getAttribute('aria-controls'));
    });
    var DEFAULT_ID = panels[0].id;
    var crumbs = document.getElementById('tlevel-breadcrumb');

    // Home / T Levels on "General info"; Home / T Levels / <Route> on a route tab.
    // Earlier items are links; the last one is the current page.
    function updateBreadcrumb(index) {
      if (!crumbs) return;
      var html = '<li><a href="home.html">Home</a></li>';
      if (index === 0) {
        html += '<li aria-current="page">T Levels</li>';
      } else {
        html += '<li><a href="TLevel.html" data-tab-link="' + DEFAULT_ID + '">T Levels</a></li>' +
          '<li aria-current="page">' + tabs[index].textContent + '</li>';
      }
      crumbs.innerHTML = html;
    }

    function indexOfId(id) {
      for (var i = 0; i < panels.length; i++) {
        if (panels[i].id === id) return i;
      }
      return -1;
    }

    function select(index, options) {
      options = options || {};
      tabs.forEach(function (tab, i) {
        var on = i === index;
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
        tab.tabIndex = on ? 0 : -1;
        panels[i].hidden = !on;
      });
      updateBreadcrumb(index);

      if (options.updateUrl) {
        var id = panels[index].id;
        history.replaceState(null, '', id === DEFAULT_ID ? location.pathname + location.search : '#' + id);
      }
      if (options.focusTab) tabs[index].focus();
      if (options.focusPanel) panels[index].focus();
    }

    function selectFromHash() {
      var index = indexOfId(location.hash.slice(1));
      select(index === -1 ? 0 : index);
    }

    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () {
        select(i, { updateUrl: true });
      });
    });

    // Vertical tabs on desktop, a horizontal row on small screens: accept both arrow pairs.
    tablist.addEventListener('keydown', function (e) {
      var current = tabs.indexOf(document.activeElement);
      if (current === -1) return;
      var next;
      switch (e.key) {
        case 'ArrowDown':
        case 'ArrowRight': next = (current + 1) % tabs.length; break;
        case 'ArrowUp':
        case 'ArrowLeft': next = (current - 1 + tabs.length) % tabs.length; break;
        case 'Home': next = 0; break;
        case 'End': next = tabs.length - 1; break;
        default: return;
      }
      e.preventDefault();
      select(next, { updateUrl: true, focusTab: true });
    });

    // Route pills and the "T Levels" breadcrumb open their tab and move focus to its content.
    // Delegated, because the breadcrumb links are rebuilt on every tab change.
    // Modifier clicks (new tab / window) keep the normal link behaviour.
    document.addEventListener('click', function (e) {
      var link = e.target.closest && e.target.closest('a[data-tab-link]');
      if (!link || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var index = indexOfId(link.getAttribute('data-tab-link'));
      if (index === -1) return;
      e.preventDefault();
      select(index, { updateUrl: true, focusPanel: true });
    });

    window.addEventListener('hashchange', selectFromHash);

    tablist.hidden = false;
    document.querySelector('.tlevel-layout').classList.add('tlevel-layout--tabs');
    selectFromHash();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
