// Sign in / sign up and account pages: checks the fields before they're sent, and on the sign-in
// page switches between the sign-in and sign-up forms.
// Loaded with defer, so the page's HTML is ready when this runs.
(function () {
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var TITLES = { signin: 'Sign in', register: 'Create account' };

  var panels = {
    signin: document.getElementById('panel-signin'),
    register: document.getElementById('panel-register')
  };
  var heading = document.getElementById('auth-title');

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

  // Only inputs with a rule have an error element (the "Keep me signed in" checkbox has neither).
  function clearAll(form) {
    Array.prototype.forEach.call(form.querySelectorAll('input:not([type="hidden"])'), function (input) {
      if (rules[input.id]) clearError(input);
    });
  }

  // ---------- Error summary at the top of the card ----------

  var summary = document.getElementById('auth-error-summary');
  var summaryList = summary && summary.querySelector('.auth-error-summary-list');

  function hideSummary() {
    if (!summary) return;
    summaryList.textContent = '';
    summary.hidden = true;
  }

  function showSummary(invalidInputs) {
    if (!summary) return;
    summaryList.textContent = '';
    invalidInputs.forEach(function (input) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#' + input.id;
      a.textContent = errorFor(input).querySelector('.field-error-text').textContent;
      a.addEventListener('click', function (e) {
        e.preventDefault();
        input.focus();
      });
      li.appendChild(a);
      summaryList.appendChild(li);
    });
    summary.hidden = false;
  }

  // ---------- Show / Hide password ----------

  function setPasswordVisible(toggle, input, visible) {
    input.type = visible ? 'text' : 'password';
    toggle.textContent = visible ? 'Hide' : 'Show';
    toggle.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
  }

  function eachToggle(root, fn) {
    Array.prototype.forEach.call(root.querySelectorAll('.password-toggle'), function (toggle) {
      var input = document.getElementById(toggle.getAttribute('aria-controls'));
      if (input) fn(toggle, input);
    });
  }

  eachToggle(document, function (toggle, input) {
    toggle.addEventListener('click', function () {
      setPasswordVisible(toggle, input, input.type === 'password');
    });
  });

  // ---------- Field rules: each returns an error message, or '' if valid ----------
  // The same rules and messages as the form checks in main.py, which checks everything again.

  function checkName(input) {
    var v = input.value.trim();
    if (!v) return 'Enter your name';
    if (v.length > 100) return 'Name must be 100 characters or fewer';
    return '';
  }

  function checkEmail(input) {
    var v = input.value.trim();
    if (!v) return 'Enter your email address';
    if (v.length > 254 || !EMAIL_RE.test(v)) return 'Enter an email address in the correct format, like name@example.com';
    return '';
  }

  function checkNewPassword(input) {
    var v = input.value;
    if (!v) return 'Enter your password';
    if (v.length < 8) return 'Password must be at least 8 characters';
    if (v.length > 128) return 'Password must be 128 characters or fewer';
    if (!/[A-Z]/.test(v)) return 'Password must include a capital letter';
    if (!/[0-9]/.test(v)) return 'Password must include a number';
    if (!/[^A-Za-z0-9\s]/.test(v)) return 'Password must include a special character, such as ! ? # or @';
    return '';
  }

  function checkConfirm(passwordId) {
    return function (input) {
      if (!input.value) return 'Type your password again';
      if (input.value !== document.getElementById(passwordId).value) return 'Passwords do not match';
      return '';
    };
  }

  function checkCurrentPassword(input) {
    return input.value ? '' : 'Enter your current password';
  }

  var rules = {
    'signin-email': checkEmail,
    'signin-password': function (input) {
      return input.value ? '' : 'Enter your password';
    },
    'register-name': checkName,
    'register-email': checkEmail,
    'register-password': checkNewPassword,
    'register-confirm': checkConfirm('register-password'),
    'account-name': checkName,
    'account-email': checkEmail,
    'email-current-password': checkCurrentPassword,
    'password-current': checkCurrentPassword,
    'password-new': checkNewPassword,
    'password-confirm': checkConfirm('password-new')
  };

  function validate(input) {
    if (!rules[input.id]) return true;
    var msg = rules[input.id](input);
    if (msg) {
      showError(input, msg);
    } else {
      clearError(input);
    }
    return !msg;
  }

  // ---------- Sign in / Sign up switch (sign-in page only) ----------

  if (panels.signin && panels.register) {
    // The first setMode runs on page load and must keep any server error in the summary.
    var modeReady = false;

    function setMode(mode) {
      var other = mode === 'register' ? 'signin' : 'register';
      panels[mode].hidden = false;
      panels[other].hidden = true;
      clearAll(panels[other].querySelector('form'));
      if (modeReady) hideSummary();

      heading.textContent = TITLES[mode];
      document.title = TITLES[mode] + ' – T Level placements at Amazon';

      // Update the URL without reloading or adding a history entry.
      history.replaceState(null, '', mode === 'register' ? '#register' : location.pathname + location.search);
    }

    function modeFromUrl() {
      if (location.hash === '#register') return 'register';
      if (new URLSearchParams(location.search).get('mode') === 'register') return 'register';
      // The server shows this page at /register when sign-up fails, so open that form.
      if (location.pathname === '/register') return 'register';
      return 'signin';
    }

    setMode(modeFromUrl());
    modeReady = true;

    window.addEventListener('hashchange', function () {
      if (location.hash === '#register' || location.hash === '#signin') {
        setMode(location.hash === '#register' ? 'register' : 'signin');
      }
    });

    // "Create an account" / "Sign in" buttons under the forms.
    Array.prototype.forEach.call(document.querySelectorAll('[data-auth-switch]'), function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var mode = a.getAttribute('data-auth-switch');
        setMode(mode);
        panels[mode].querySelector('input:not([type="hidden"])').focus();
      });
    });
  }

  // ---------- Account page: pencil opens one form at a time, Cancel closes it ----------
  // Without JavaScript the pencil and Cancel are plain links to /account?edit=<form> and /account.

  function accountRow(el) {
    var row = el.closest('.account-row');
    return {
      edit: row.querySelector('.account-edit'),
      value: row.querySelector('.account-value'),
      form: row.querySelector('.account-form')
    };
  }

  function closeAccountForm(row) {
    if (row.form.hidden) return;
    row.form.reset();
    clearAll(row.form);
    eachToggle(row.form, function (toggle, input) { setPasswordVisible(toggle, input, false); });
    row.form.hidden = true;
    row.value.hidden = false;
    row.edit.hidden = false;
  }

  var editLinks = document.querySelectorAll('[data-account-edit]');

  Array.prototype.forEach.call(editLinks, function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      Array.prototype.forEach.call(editLinks, function (other) { closeAccountForm(accountRow(other)); });
      hideSummary();
      var row = accountRow(link);
      row.value.hidden = true;
      row.edit.hidden = true;
      row.form.hidden = false;
      row.form.querySelector('input:not([type="hidden"]):not([hidden])').focus();
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll('[data-account-cancel]'), function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      var row = accountRow(link);
      closeAccountForm(row);
      hideSummary();
      row.edit.focus();
    });
  });

  // Drop ?edit= from the address once the page has loaded, so a refresh shows the plain page.
  if (editLinks.length && location.search) history.replaceState(null, '', location.pathname);

  // ---------- Submit: block only when invalid, otherwise post natively ----------

  function onSubmit(e) {
    var inputs = e.target.querySelectorAll('input:not([type="hidden"])');
    var invalid = [];
    Array.prototype.forEach.call(inputs, function (input) {
      if (!validate(input)) invalid.push(input);
    });
    if (invalid.length) {
      showSummary(invalid);
      e.preventDefault();
      invalid[0].focus();
    } else {
      hideSummary();
      // Post passwords from a password field, so the browser doesn't save them as plain text.
      eachToggle(e.target, function (toggle, input) { setPasswordVisible(toggle, input, false); });
    }
  }

  Array.prototype.forEach.call(document.querySelectorAll('form.auth-form'), function (form) {
    form.addEventListener('submit', onSubmit);
  });
})();
