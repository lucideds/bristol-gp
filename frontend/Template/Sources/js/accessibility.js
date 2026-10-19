(function () {
  // Accessibility popup: text size, colours and a few reading aids, saved on this device.
  // Load this in <head> WITHOUT defer, so saved settings are applied before the page is drawn.
  // (document.currentScript only works here at the top level, not in callbacks.)
  // The script lives in Template/Sources/js/, so the icons are one folder up in assests/.
  var script = document.currentScript;
  var CLOSE_ICON_URL = new URL('../assests/a11y-close.svg', script.src).href;
  var CHECK_ICON_URL = new URL('../assests/a11y-check.svg', script.src).href; // Tick used by accessibility.css.

  var THEME_KEY = 'tlc-theme';     // Shared with the light / dark button in topNavBar.js.
  var SETTINGS_KEY = 'tlc-a11y';   // Everything else, as one JSON object.
  var THEMES = ['light', 'dark', 'high-contrast'];
  var SIZES = ['standard', 'large', 'extra-large'];
  var DEFAULTS = { textSize: 'standard', readableFont: false, reduceMotion: false, highlightLinks: false };

  var root = document.documentElement;

  // Reads the saved settings, falling back to the default for anything missing or broken.
  function loadSettings() {
    var saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    } catch (e) {
      saved = {};
    }
    if (typeof saved !== 'object') saved = {};
    return {
      textSize: SIZES.indexOf(saved.textSize) !== -1 ? saved.textSize : DEFAULTS.textSize,
      readableFont: saved.readableFont === true,
      reduceMotion: saved.reduceMotion === true,
      highlightLinks: saved.highlightLinks === true
    };
  }

  function loadTheme() {
    var t = null;
    try {
      t = localStorage.getItem(THEME_KEY);
    } catch (e) {}
    return THEMES.indexOf(t) !== -1 ? t : 'light';
  }

  // Some browsers block localStorage on file://, so saving can fail quietly.
  function saveSettings(s) {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
    } catch (e) {}
  }

  function saveTheme(t) {
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch (e) {}
  }

  // Puts the settings on <html> so the CSS in accessibility.css can use them.
  function applySettings(s) {
    root.setAttribute('data-text-size', s.textSize);
    root.classList.toggle('a11y-readable-font', s.readableFont);
    root.classList.toggle('a11y-reduce-motion', s.reduceMotion);
    root.classList.toggle('a11y-highlight-links', s.highlightLinks);
  }

  // Changes the theme and tells the nav bar so its light / dark button updates.
  function applyTheme(t) {
    root.setAttribute('data-theme', t);
    document.dispatchEvent(new CustomEvent('tlc:themechange'));
  }

  // Apply the saved choices straight away (the nav bar isn't built yet, so no event).
  var settings = loadSettings();
  applySettings(settings);
  root.setAttribute('data-theme', loadTheme());

  var dialog = null;
  var returnFocusTo = null;

  // One tile in the "Text size" or "Colours" group.
  function tile(name, value, label, sample, boxClass) {
    return '<label class="a11y-tile">' +
        '<input type="radio" class="a11y-visually-hidden" name="' + name + '" value="' + value + '">' +
        '<span class="a11y-tile-box' + (boxClass || '') + '">' +
          sample +
          '<span class="a11y-tile-label">' + label + '</span>' +
          '<span class="a11y-tile-check" aria-hidden="true"></span>' +
        '</span>' +
      '</label>';
  }

  function sizeTile(value, label) {
    return tile('a11y-text-size', value, label,
      '<span class="a11y-tile-sample a11y-tile-sample--' + value + '" aria-hidden="true">Aa</span>');
  }

  function colourTile(value, label, swatch) {
    return tile('a11y-theme', value, label,
      '<span class="a11y-swatch a11y-swatch--' + swatch + '" aria-hidden="true">Aa</span>',
      ' a11y-tile-box--colour');
  }

  // One on/off row. The checkbox is a switch for screen readers.
  function toggleRow(id, setting, title, desc) {
    return '<label class="a11y-toggle-row">' +
        '<span class="a11y-toggle-text">' +
          '<span id="a11y-' + id + '-title" class="a11y-toggle-title">' + title + '</span>' +
          '<span id="a11y-' + id + '-desc" class="a11y-toggle-desc">' + desc + '</span>' +
        '</span>' +
        '<span class="a11y-toggle-status" aria-hidden="true">Off</span>' +
        '<input type="checkbox" role="switch" class="a11y-visually-hidden" id="a11y-' + id + '"' +
          ' data-setting="' + setting + '" aria-labelledby="a11y-' + id + '-title" aria-describedby="a11y-' + id + '-desc">' +
        '<span class="a11y-switch" aria-hidden="true"></span>' +
      '</label>';
  }

  // Ticks the controls that match the current settings.
  function syncControls() {
    var theme = root.getAttribute('data-theme') || 'light';
    dialog.querySelectorAll('input[name="a11y-text-size"]').forEach(function (r) {
      r.checked = r.value === settings.textSize;
    });
    dialog.querySelectorAll('input[name="a11y-theme"]').forEach(function (r) {
      r.checked = r.value === theme;
    });
    dialog.querySelectorAll('input[data-setting]').forEach(function (c) {
      c.checked = settings[c.getAttribute('data-setting')];
      c.previousElementSibling.textContent = c.checked ? 'On' : 'Off';
    });
  }

  function openPanel(trigger) {
    if (!dialog || dialog.open) return;
    returnFocusTo = trigger || document.activeElement;
    syncControls();
    dialog.showModal();
    var first = dialog.querySelector('input[name="a11y-text-size"]:checked');
    if (first) first.focus();
  }

  function closePanel() {
    if (dialog.open) dialog.close();
    // Go back to whatever opened the popup, or to the nav button if that's gone.
    var target = returnFocusTo;
    if (!target || !target.isConnected || target === document.body) {
      target = document.querySelector('.nav-tool--accessibility');
    }
    if (target && target.focus) target.focus();
  }

  function build() {
    if (document.getElementById('a11y-panel')) return;

    var html =
      '<dialog id="a11y-panel" class="a11y-panel" aria-labelledby="a11y-title">' +
        '<div class="a11y-inner">' +
          '<div class="a11y-head">' +
            '<h2 id="a11y-title" class="a11y-title">Accessibility</h2>' +
            '<button type="button" class="a11y-close" aria-label="Close accessibility settings">' +
              '<img src="' + CLOSE_ICON_URL + '" alt="" width="24" height="24">' +
            '</button>' +
          '</div>' +
          '<fieldset class="a11y-section">' +
            '<legend class="a11y-label">Text size</legend>' +
            '<div class="a11y-tiles">' +
              sizeTile('standard', 'Standard') +
              sizeTile('large', 'Large') +
              sizeTile('extra-large', 'Extra large') +
            '</div>' +
          '</fieldset>' +
          '<fieldset class="a11y-section">' +
            '<legend class="a11y-label">Colours</legend>' +
            '<div class="a11y-tiles">' +
              colourTile('light', 'Light', 'light') +
              colourTile('dark', 'Dark', 'dark') +
              colourTile('high-contrast', 'High contrast', 'contrast') +
            '</div>' +
          '</fieldset>' +
          toggleRow('readable-font', 'readableFont', 'Dyslexia-friendly font', 'Use a more readable font') +
          toggleRow('reduce-motion', 'reduceMotion', 'Reduce motion', 'Turn off animations') +
          toggleRow('highlight-links', 'highlightLinks', 'Highlight links', 'Underline and outline all links') +
          '<div class="a11y-footer">' +
            '<button type="button" class="a11y-reset">Reset to default</button>' +
            '<button type="button" class="a11y-done">Done</button>' +
          '</div>' +
          '<p class="a11y-note">Your choices are saved on this device.</p>' +
        '</div>' +
      '</dialog>';

    document.body.insertAdjacentHTML('beforeend', html);
    dialog = document.getElementById('a11y-panel');
    // Load the tick now, so it's ready the first time the popup opens.
    new Image().src = CHECK_ICON_URL;

    // Changes apply and save straight away; the buttons only close the popup.
    dialog.addEventListener('change', function (e) {
      var el = e.target;
      if (el.name === 'a11y-text-size') {
        settings.textSize = el.value;
        applySettings(settings);
        saveSettings(settings);
      } else if (el.name === 'a11y-theme') {
        applyTheme(el.value);
        saveTheme(el.value);
      } else if (el.hasAttribute('data-setting')) {
        settings[el.getAttribute('data-setting')] = el.checked;
        applySettings(settings);
        saveSettings(settings);
        el.previousElementSibling.textContent = el.checked ? 'On' : 'Off';
      }
    });

    dialog.querySelector('.a11y-reset').addEventListener('click', function () {
      saveTheme('light');
      applyTheme('light');
      try {
        localStorage.removeItem(SETTINGS_KEY);
      } catch (e) {}
      settings = {
        textSize: DEFAULTS.textSize,
        readableFont: DEFAULTS.readableFont,
        reduceMotion: DEFAULTS.reduceMotion,
        highlightLinks: DEFAULTS.highlightLinks
      };
      applySettings(settings);
      syncControls();
    });

    dialog.querySelector('.a11y-done').addEventListener('click', closePanel);
    dialog.querySelector('.a11y-close').addEventListener('click', closePanel);

    // A click on the dialog itself (not its content) is a click on the backdrop.
    dialog.addEventListener('click', function (e) {
      if (e.target === dialog) closePanel();
    });

    // The browser fires "cancel" on Escape; close our way so focus goes back.
    dialog.addEventListener('cancel', function (e) {
      e.preventDefault();
      closePanel();
    });

    dialog.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        // Stop the chat and nav Escape handlers from also running.
        e.preventDefault();
        e.stopPropagation();
        closePanel();
        return;
      }
      if (e.key !== 'Tab') return;
      // Keep Tab and Shift+Tab inside the popup.
      var items = dialog.querySelectorAll('button, input[type="checkbox"], input[type="radio"]:checked');
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });

    // Old links to /accessibility land on /#accessibility: open the popup.
    if (location.hash === '#accessibility') {
      history.replaceState(null, '', location.pathname + location.search);
      openPanel(document.querySelector('.nav-tool--accessibility'));
    }
  }

  // The nav bar's Accessibility button opens the popup (works whichever script runs first).
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('.nav-tool--accessibility');
    if (!t) return;
    e.preventDefault();
    openPanel(t);
  });

  // Build the popup once the page's HTML has loaded.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
