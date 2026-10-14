(function () {
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var TITLES = { signin: 'Sign in', register: 'Create account' };

  function init() {
    var tabs = {
      signin: document.getElementById('tab-signin'),
      register: document.getElementById('tab-register')
    };
    var panels = {
      signin: document.getElementById('panel-signin'),
      register: document.getElementById('panel-register')
    };
    var heading = document.getElementById('auth-title');
    var signinForm = document.getElementById('signin-form');
    var registerForm = document.getElementById('register-form');

    // ---------- Inline errors ----------

    function errorFor(input) {
      return document.getElementById(input.id + '-error');
    }

    function showError(input, msg) {
      var el = errorFor(input);
      input.setAttribute('aria-invalid', 'true');
      el.querySelector('.field-error-text').textContent = msg;
      el.hidden = false;
    }

    function clearError(input) {
      var el = errorFor(input);
      input.removeAttribute('aria-invalid');
      el.querySelector('.field-error-text').textContent = '';
      el.hidden = true;
    }

    function hasError(input) {
      return input.getAttribute('aria-invalid') === 'true';
    }

    function clearAll(form) {
      Array.prototype.forEach.call(form.querySelectorAll('input'), clearError);
    }

    // ---------- Field rules: each returns an error message, or '' if valid ----------

    function checkEmail(input) {
      var v = input.value.trim();
      if (!v) return 'Enter your email address';
      if (!EMAIL_RE.test(v)) return 'Enter a valid email address';
      return '';
    }

    var rules = {
      'signin-email': checkEmail,
      'signin-password': function (input) {
        return input.value ? '' : 'Enter your password';
      },
      'register-name': function (input) {
        return input.value.trim() ? '' : 'Enter your name';
      },
      'register-email': checkEmail,
      'register-password': function (input) {
        if (!input.value) return 'Enter your password';
        if (input.value.length < 8) return 'Passwords must be at least 8 characters';
        return '';
      },
      'register-confirm': function (input) {
        if (!input.value) return 'Type your password again';
        if (input.value !== document.getElementById('register-password').value) return 'Passwords must match';
        return '';
      }
    };

    function validate(input) {
      var msg = rules[input.id](input);
      if (msg) {
        showError(input, msg);
      } else {
        clearError(input);
      }
      return !msg;
    }

    // ---------- Sign in / Sign up switch ----------

    function setMode(mode, focusTab) {
      var other = mode === 'register' ? 'signin' : 'register';

      tabs[mode].setAttribute('aria-selected', 'true');
      tabs[mode].tabIndex = 0;
      tabs[other].setAttribute('aria-selected', 'false');
      tabs[other].tabIndex = -1;

      panels[mode].hidden = false;
      panels[other].hidden = true;
      clearAll(panels[other].querySelector('form'));

      heading.textContent = TITLES[mode];
      document.title = TITLES[mode] + ' – T Level Connect';

      // Update the URL without reloading or adding a history entry.
      history.replaceState(null, '', mode === 'register' ? '#register' : location.pathname + location.search);

      if (focusTab) tabs[mode].focus();
    }

    function modeFromUrl() {
      if (location.hash === '#register') return 'register';
      if (new URLSearchParams(location.search).get('mode') === 'register') return 'register';
      return 'signin';
    }

    setMode(modeFromUrl(), false);

    window.addEventListener('hashchange', function () {
      if (location.hash === '#register' || location.hash === '#signin') {
        setMode(location.hash === '#register' ? 'register' : 'signin', false);
      }
    });

    tabs.signin.addEventListener('click', function () { setMode('signin', false); });
    tabs.register.addEventListener('click', function () { setMode('register', false); });

    // Arrow keys / Home / End move between tabs (WAI-ARIA tabs pattern).
    tabs.signin.parentNode.addEventListener('keydown', function (e) {
      var current = tabs.register.getAttribute('aria-selected') === 'true' ? 'register' : 'signin';
      var next = null;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') next = current === 'signin' ? 'register' : 'signin';
      if (e.key === 'Home') next = 'signin';
      if (e.key === 'End') next = 'register';
      if (next) {
        e.preventDefault();
        setMode(next, true);
      }
    });

    // "Create an account" / "Sign in" text links under the forms.
    Array.prototype.forEach.call(document.querySelectorAll('[data-auth-switch]'), function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var mode = a.getAttribute('data-auth-switch');
        setMode(mode, false);
        panels[mode].querySelector('input').focus();
      });
    });

    // ---------- Submit: block only when invalid, otherwise post natively ----------

    function onSubmit(e) {
      var inputs = e.target.querySelectorAll('input');
      var firstInvalid = null;
      Array.prototype.forEach.call(inputs, function (input) {
        if (!validate(input) && !firstInvalid) firstInvalid = input;
      });
      if (firstInvalid) {
        e.preventDefault();
        firstInvalid.focus();
      }
    }

    signinForm.addEventListener('submit', onSubmit);
    registerForm.addEventListener('submit', onSubmit);

  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
