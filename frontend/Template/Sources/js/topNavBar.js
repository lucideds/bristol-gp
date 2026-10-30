// The site header: logo, search, Accessibility and Sign in buttons, and the main page links.
// Loaded with defer after site.js, so the page's HTML is ready when this runs.
(function () {
  var link = TLC.link;
  var isCurrent = TLC.isCurrent;

  // Records a search, route view or quiz result for the analytics page.
  // Shared on window so tlevelTabs.js and quiz.js can use it (this script loads before them).
  // keepalive lets the request finish even if the page is changing (search moves to a new page).
  // Failures are ignored: analytics must never get in the visitor's way.
  window.tlcTrack = function (kind, value) {
    fetch(link('api/track'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: kind, value: value }),
      keepalive: true
    }).catch(function () {});
  };

  // Page links in the middle of the top bar, in order.
  var PAGES = [
    { label: 'Home', path: '' },
    { label: 'T Level', path: 't-levels' },
    { label: 'Advice', path: 'advice' },
    { label: 'FAQ', path: 'faqs' },
    { label: 'Contact', path: 'contact' }
  ];

  // Search index used by the search bar in the top bar.
  // Each entry is a place on the site: its title (also shown as a suggestion),
  // the page (plus #section) to open, and extra keywords people might type.
  // When you add a page or section, add an entry here so search can find it.
  var SEARCH_INDEX = [
    { title: 'Home', path: '',
      keywords: 'home main start welcome amazon placement career' },
    { title: 'Who are you?', path: '#home-audience-title',
      keywords: 'students schools colleges teachers parents guardians audience after gcses gcse during t level educational step' },
    { title: 'Explore placement routes', path: '#home-routes-title',
      keywords: 'routes pathways options explore five' },
    { title: 'Interested? Tell us.', path: '#home-cta-title',
      keywords: 'interested interest tell us questions' },

    { title: 'T Levels at Amazon', path: 't-levels',
      keywords: 't level tlevel tlevels qualification course routes overview general what t levels are choose a route' },
    { title: 'Digital route', path: 't-levels#digital',
      keywords: 'digital it tech technology computing computer software developer programming coding cloud infrastructure engineer data analyst support technician cyber security computer science' },
    { title: 'Business route', path: 't-levels#business',
      keywords: 'business analyst operations coordinator manager project management hr human resources advisor assistant management' },
    { title: 'Media route', path: 't-levels#media',
      keywords: 'media marketing executive assistant content creator producer video editor social media manager coordinator graphic design designer production creative' },
    { title: 'Finance route', path: 't-levels#finance',
      keywords: 'finance financial accounting accounts accountant auditor money payroll specialist administrator aat acca analyst trainee apprentice' },
    { title: 'Engineering route', path: 't-levels#engineering',
      keywords: 'engineering engineer mechanical electrical quality manufacturing processing control maintenance technician logistics fulfilment equipment' },

    { title: 'Advice', path: 'advice',
      keywords: 'advice guide guidance thinking about tips resources parents carers careers adviser advisor' },
    { title: 'Advice: Why choose a T Level', path: 'advice#why-choose',
      keywords: 'why choose reasons learn by doing practical real placement three a levels doors open benefits' },
    { title: 'Advice: How to apply for a placement', path: 'advice#how-to-apply',
      keywords: 'apply application steps how to apply interview prepare cv dates school college' },
    { title: 'Advice: Where it can lead', path: 'advice#where-it-leads',
      keywords: 'lead careers jobs example jobs by route future next step after university ucas apprenticeship work' },
    { title: 'Advice: Common worries', path: 'advice#common-worries',
      keywords: 'worries worried concerns common question team adjustments support change mind unsure nervous' },
    { title: 'Advice: Your path to a placement', path: 'advice#your-path',
      keywords: 'your path find timeline year 10 11 12 13 steps when gcse results start placement register interview journey plan' },

    { title: 'Which T Level suits you? (quiz)', path: 'quiz',
      keywords: 'quiz test which suits me match matches find my t level questions personality recommend' },

    { title: 'Frequently asked questions', path: 'faqs',
      keywords: 'faq faqs questions answers help' },
    { title: 'FAQ: About T Levels', path: 'faqs#about-t-levels',
      keywords: 'a levels difference eligibility eligible age gcse subjects qualification certificate grade pass merit distinction' },
    { title: 'FAQ: Industry placements', path: 'faqs#industry-placements',
      keywords: 'industry placement work experience hours length long duration skills network networking 315' },
    { title: 'FAQ: Amazon placements', path: 'faqs#amazon-placements',
      keywords: 'apply application how to apply cv benefits amazon' },
    { title: 'FAQ: After your T Level', path: 'faqs#after-your-t-level',
      keywords: 'after university uni degree apprenticeship apprenticeships jobs future opportunities next steps' },

    { title: 'Contact us', path: 'contact',
      keywords: 'contact email message get in touch support enquiry enquiries help interested' },

    { title: 'Privacy', path: 'privacy',
      keywords: 'privacy policy personal data gdpr' },
    { title: 'Privacy: What data we collect', path: 'privacy#data-we-collect',
      keywords: 'data collect collected email information' },
    { title: 'Privacy: What your data is used for', path: 'privacy#data-use',
      keywords: 'data use used marketing share sharing third parties' },
    { title: 'Privacy: How your password is protected', path: 'privacy#password-protection',
      keywords: 'password security hashed protected' },
    { title: 'Privacy: Data retention policy', path: 'privacy#data-retention',
      keywords: 'retention delete deletion keep account' },
    { title: 'Privacy: Your rights', path: 'privacy#your-rights',
      keywords: 'rights gdpr data protection act request correct' },
    { title: 'Privacy: Cookies', path: 'privacy#cookies',
      keywords: 'cookies cookie consent analytics pecr' },
    { title: 'Privacy: AI privacy notice', path: 'privacy#AI-data',
      keywords: 'ai chatbot chat bot assistant artificial intelligence zero data retention messages stored' },

    { title: 'Sign in', path: 'login',
      keywords: 'sign in signin login log in account' },
    { title: 'Register your interest', path: 'login#register',
      keywords: 'register registration sign up signup create account interest join' },
    // Opens the accessibility popup on the current page instead of navigating.
    { title: 'Accessibility settings', path: '#accessibility', opensAccessibility: true,
      keywords: 'accessibility a11y dark mode theme contrast high contrast text size font colour color' }
  ];

  // Words that carry no meaning for matching.
  var STOP_WORDS = ['a', 'an', 'and', 'the', 'to', 'of', 'for', 'in', 'on', 'at', 'is', 'are',
    'do', 'i', 'my', 'me', 'can', 'how', 'what', 'who', 'where', 'about', 'with', 'page'];

  function normalise(text) {
    return text.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function words(text) {
    return normalise(text).split(' ').filter(function (w) {
      return w && STOP_WORDS.indexOf(w) === -1;
    });
  }

  // Score one entry against the query. Higher is a better match; 0 means no match.
  function scoreEntry(entry, query) {
    var q = normalise(query);
    var title = normalise(entry.title);
    if (!q) return 0;
    if (title === q) return 1000;

    // Ignore the "FAQ: " / "Privacy: " label on sections so "faq" finds the FAQ page itself.
    var shortTitle = entry.title.replace(/^[^:]+:\s*/, '');
    var titleWords = words(shortTitle);
    var keywordWords = words(entry.keywords);
    var keywordText = ' ' + normalise(entry.keywords) + ' ';
    var score = 0;

    if (normalise(shortTitle).indexOf(q) !== -1) score += 50;
    // Multi-word keywords like "high contrast" or "sign up".
    if (q.indexOf(' ') !== -1 && keywordText.indexOf(' ' + q + ' ') !== -1) score += 40;

    words(query).forEach(function (w) {
      if (titleWords.indexOf(w) !== -1) {
        score += 10;
      } else if (keywordWords.indexOf(w) !== -1) {
        score += 6;
      } else if (w.length >= 3) {
        // Partial words: "eng" finds "engineering", "placements" finds "placement".
        var partial = titleWords.concat(keywordWords).some(function (k) {
          return k.indexOf(w) === 0 || (k.length >= 4 && w.indexOf(k) === 0);
        });
        if (partial) score += 3;
      }
    });
    // A whole page beats one of its sections when both match equally ("faq", "privacy").
    if (score > 0 && entry.path.indexOf('#') === -1) score += 1;
    return score;
  }

  var MAX_SUGGESTIONS = 8;

  // Matching entries, best first. Ties keep SEARCH_INDEX order.
  function findMatches(query) {
    return SEARCH_INDEX
      .map(function (entry, i) { return { entry: entry, score: scoreEntry(entry, query), i: i }; })
      .filter(function (m) { return m.score > 0; })
      .sort(function (a, b) { return b.score - a.score || a.i - b.i; })
      .map(function (m) { return m.entry; });
  }

  // Return the best matching entry, or null if nothing matches.
  function findBestMatch(query) {
    return findMatches(query)[0] || null;
  }

  function goTo(entry) {
    var a11yButton = document.querySelector('.nav-tool--accessibility');
    if (entry.opensAccessibility && a11yButton) {
      a11yButton.click();
      return;
    }
    var target = new URL(link(entry.path));
    // Same page and same #section: the browser won't move, so scroll there ourselves.
    if (target.pathname === location.pathname && target.hash && target.hash === location.hash) {
      var el = document.getElementById(target.hash.slice(1));
      if (el) {
        el.scrollIntoView();
        return;
      }
    }
    location.href = target.href;
  }

  // Marks the link to the current page, so the nav bar can underline it.
  function currentAttrs(href) {
    return isCurrent(href) ? { cls: ' active', aria: ' aria-current="page"' } : { cls: '', aria: '' };
  }

  function navLink(label, path) {
    var href = link(path);
    var cur = currentAttrs(href);
    return '<a class="nav-link' + cur.cls + '" href="' + href + '"' + cur.aria + '>' + label + '</a>';
  }

  function buildNav() {
    var signinHref = link('login');
    var signin = currentAttrs(signinHref);

    var html =
      '<header class="site-header">' +
        '<div class="nav-top">' +
          '<div class="nav-container nav-top-inner">' +
            '<a class="brand" href="' + link('') + '">' +
              '<img src="' + link('Sources/assets/amazon_logo.png') + '" alt="Home" width="102" height="34">' +
            '</a>' +
            '<form class="nav-search" role="search" action="' + link('') + '">' +
              '<input type="search" name="q" placeholder="Search T Levels and placements" aria-label="Search the site"' +
                ' role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="nav-search-list"' +
                ' autocomplete="off" aria-describedby="nav-search-status">' +
              '<ul class="nav-search-list" id="nav-search-list" role="listbox" aria-label="Search suggestions" hidden></ul>' +
              '<p class="nav-search-status" id="nav-search-status" role="status"></p>' +
              '<button type="submit" aria-label="Search">' +
                '<img src="' + link('Sources/assets/nav-search.svg') + '" alt="" width="24" height="24">' +
              '</button>' +
            '</form>' +
            '<div class="nav-tools">' +
              '<button type="button" class="nav-tool nav-tool--accessibility" aria-haspopup="dialog" aria-controls="a11y-panel">Accessibility</button>' +
              '<a class="nav-tool nav-tool--signin signin-btn' + signin.cls + '" href="' + signinHref + '"' + signin.aria + '>Sign in</a>' +
            '</div>' +
            '<button type="button" class="nav-toggle" aria-expanded="false" aria-controls="nav-collapsible" aria-label="Menu">\u2630</button>' +
          '</div>' +
        '</div>' +
        '<nav class="nav-second" aria-label="Main">' +
          '<div class="nav-container nav-second-inner">' +
            '<div class="nav-collapsible" id="nav-collapsible">' +
              '<div class="nav-links">' +
                PAGES.map(function (p) { return navLink(p.label, p.path); }).join('') +
              '</div>' +
            '</div>' +
          '</div>' +
        '</nav>' +
      '</header>';

    document.body.insertAdjacentHTML('afterbegin', html);

    // Ask the Flask server if someone is signed in; if so, turn "Sign in" into "Account".
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

    // Search: find the best matching page or section and go there.
    var searchForm = document.querySelector('.nav-search');
    var searchInput = searchForm.querySelector('input');
    var searchStatus = document.getElementById('nav-search-status');
    var searchList = document.getElementById('nav-search-list');
    var suggestions = [];
    var activeIndex = -1;

    // Suggestions dropdown (replaces the browser's <datalist> popup so it matches the site
    // and themes). Focus stays in the input; the highlighted option is announced through
    // aria-activedescendant, following the ARIA combobox pattern.
    function setActive(index) {
      activeIndex = index;
      Array.prototype.forEach.call(searchList.children, function (li, i) {
        li.setAttribute('aria-selected', i === index ? 'true' : 'false');
      });
      if (index === -1) {
        searchInput.removeAttribute('aria-activedescendant');
        return;
      }
      var li = searchList.children[index];
      searchInput.setAttribute('aria-activedescendant', li.id);
      li.scrollIntoView({ block: 'nearest' });
    }

    function closeSuggestions() {
      suggestions = [];
      setActive(-1);
      searchList.textContent = '';
      searchList.hidden = true;
      searchInput.setAttribute('aria-expanded', 'false');
    }

    // Bold the part of the title that matches what was typed.
    function optionLabel(li, title, query) {
      var at = title.toLowerCase().indexOf(query.toLowerCase());
      if (at === -1) {
        li.textContent = title;
        return;
      }
      var match = document.createElement('strong');
      match.textContent = title.slice(at, at + query.length);
      li.append(title.slice(0, at), match, title.slice(at + query.length));
    }

    function showSuggestions() {
      var query = searchInput.value.trim();
      suggestions = query ? findMatches(query).slice(0, MAX_SUGGESTIONS) : [];
      if (!suggestions.length) {
        closeSuggestions();
        return;
      }
      searchList.textContent = '';
      suggestions.forEach(function (entry, i) {
        var li = document.createElement('li');
        li.id = 'nav-search-option-' + i;
        li.className = 'nav-search-option';
        li.setAttribute('role', 'option');
        optionLabel(li, entry.title, query);
        searchList.appendChild(li);
      });
      setActive(-1);
      searchList.hidden = false;
      searchInput.setAttribute('aria-expanded', 'true');
    }

    function choose(entry, query) {
      window.tlcTrack('search', query.slice(0, 100));
      closeSuggestions();
      searchStatus.textContent = '';
      searchInput.value = '';
      goTo(entry);
    }

    searchInput.addEventListener('keydown', function (e) {
      var open = !searchList.hidden;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (!open) showSuggestions();
        if (suggestions.length) setActive((activeIndex + 1) % suggestions.length);
      } else if (e.key === 'ArrowUp' && open) {
        e.preventDefault();
        setActive(activeIndex <= 0 ? suggestions.length - 1 : activeIndex - 1);
      } else if (e.key === 'Escape' && open) {
        // Only close the list; the browser's own Escape would also wipe the typed text.
        e.preventDefault();
        e.stopPropagation();
        closeSuggestions();
      }
    });

    // Keep focus in the input when an option is pressed, so blur doesn't close the list first.
    searchList.addEventListener('mousedown', function (e) { e.preventDefault(); });

    searchList.addEventListener('mousemove', function (e) {
      var li = e.target.closest('[role="option"]');
      var index = Array.prototype.indexOf.call(searchList.children, li);
      if (li && index !== activeIndex) setActive(index);
    });

    searchList.addEventListener('click', function (e) {
      var li = e.target.closest('[role="option"]');
      if (!li) return;
      choose(suggestions[Array.prototype.indexOf.call(searchList.children, li)], searchInput.value.trim());
    });

    searchForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var query = searchInput.value.trim();
      if (activeIndex !== -1) {
        choose(suggestions[activeIndex], query);
        return;
      }
      closeSuggestions();
      if (!query) {
        searchStatus.textContent = 'Type a word to search, for example "digital" or "apply".';
        searchInput.focus();
        return;
      }
      var match = findBestMatch(query);
      if (!match) {
        window.tlcTrack('search', query.slice(0, 100));
        searchStatus.textContent = 'No results for "' + query + '". Try "T Levels", "placement" or "contact".';
        searchInput.focus();
        return;
      }
      choose(match, query);
    });

    // Typing refreshes the suggestions and clears any message; leaving the box hides both.
    searchInput.addEventListener('input', function () {
      searchStatus.textContent = '';
      showSuggestions();
    });
    searchInput.addEventListener('focus', showSuggestions);
    searchInput.addEventListener('blur', function () {
      searchStatus.textContent = '';
      closeSuggestions();
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

  buildNav();
})();
