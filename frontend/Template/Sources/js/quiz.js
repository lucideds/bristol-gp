// T Level quiz: each answer's value is a route. The two routes with the most answers are shown.
// Ties are broken by ROUTE_ORDER; any other route level with second place is listed as "also worth a look".
(function () {
  var ROUTES = {
    digital: {
      name: 'Digital',
      text: 'You are curious and patient, and you enjoy working out tricky problems step by step. Digital could lead to jobs like software developer, data analyst or cyber security analyst.'
    },
    business: {
      name: 'Business',
      text: 'You are confident with people and good at keeping a group on track. Business could lead to jobs like project manager, business analyst or HR adviser.'
    },
    media: {
      name: 'Media',
      text: 'You are creative and full of ideas, and you like making things other people enjoy. Media could lead to jobs like content producer, video editor or marketing executive.'
    },
    finance: {
      name: 'Finance',
      text: 'You are careful and reliable, and you like to get things exactly right. Finance could lead to jobs like accountant, financial analyst or auditor.'
    },
    engineering: {
      name: 'Engineering',
      text: 'You are practical and hands-on, and you like to learn by doing. Engineering could lead to jobs like mechanical engineer or maintenance technician.'
    }
  };
  var ROUTE_ORDER = ['digital', 'business', 'media', 'finance', 'engineering'];

  var form = document.getElementById('quiz-form');
  if (!form) return;

  var error = document.getElementById('quiz-error');
  var result = document.getElementById('quiz-result');
  var title = document.getElementById('quiz-result-title');
  var also = document.getElementById('quiz-result-also');
  var matchCards = result.querySelectorAll('[data-match]');
  var questions = form.querySelectorAll('.quiz-question');
  var progress = document.getElementById('quiz-progress');
  var backBtn = document.getElementById('quiz-back');
  var nextBtn = document.getElementById('quiz-next');
  var submitBtn = document.getElementById('quiz-submit');
  var current = 0;

  // Show one question at a time. moveFocus is false on first load so the page doesn't jump.
  function showStep(index, moveFocus) {
    current = index;
    questions.forEach(function (question, i) {
      question.hidden = i !== index;
    });
    var last = index === questions.length - 1;
    progress.textContent = 'Question ' + (index + 1) + ' of ' + questions.length;
    progress.hidden = false;
    backBtn.hidden = index === 0;
    nextBtn.hidden = last;
    submitBtn.hidden = !last;
    if (moveFocus) {
      var target = questions[index].querySelector('input:checked') || questions[index].querySelector('input');
      target.focus();
    }
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  nextBtn.addEventListener('click', function () {
    var question = questions[current];
    if (!question.querySelector('input:checked')) {
      question.classList.add('quiz-question--missing');
      showError('Please choose an answer to carry on.');
      question.querySelector('input').focus();
      return;
    }
    question.classList.remove('quiz-question--missing');
    error.hidden = true;
    showStep(current + 1, true);
  });

  backBtn.addEventListener('click', function () {
    error.hidden = true;
    showStep(current - 1, true);
  });

  // Clear the "missing" warning as soon as an answer is picked
  form.addEventListener('change', function (event) {
    var question = event.target.closest('.quiz-question');
    if (question && question.classList.contains('quiz-question--missing')) {
      question.classList.remove('quiz-question--missing');
      error.hidden = true;
    }
  });

  showStep(0, false);

  function joinNames(keys) {
    var names = keys.map(function (key) { return ROUTES[key].name; });
    if (names.length < 2) return names.join('');
    return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();

    // Pressing Enter before the last question acts as "Next question"
    if (current < questions.length - 1) {
      nextBtn.click();
      return;
    }

    var counts = {};
    var firstUnanswered = null;
    ROUTE_ORDER.forEach(function (key) { counts[key] = 0; });

    questions.forEach(function (question) {
      var checked = question.querySelector('input:checked');
      question.classList.toggle('quiz-question--missing', !checked);
      if (checked) {
        counts[checked.value] += 1;
      } else if (!firstUnanswered) {
        firstUnanswered = question;
      }
    });

    if (firstUnanswered) {
      result.hidden = true;
      showStep(Array.prototype.indexOf.call(questions, firstUnanswered), true);
      showError('Please choose an answer to see your result.');
      return;
    }
    error.hidden = true;

    // Most answers first; equal counts keep ROUTE_ORDER (sort is stable)
    var ranked = ROUTE_ORDER.slice().sort(function (a, b) { return counts[b] - counts[a]; });
    var top = ranked.slice(0, matchCards.length);
    if (window.tlcTrack) window.tlcTrack('quiz', top[0]);   // The top match, for the analytics page

    top.forEach(function (key, i) {
      var matchCard = matchCards[i];
      var matchLink = matchCard.querySelector('.quiz-match-link');
      matchCard.className = 'route-card quiz-result-card route-card--' + key;
      matchCard.querySelector('.quiz-match-name').textContent = ROUTES[key].name;
      matchCard.querySelector('.quiz-match-text').textContent = ROUTES[key].text;
      matchLink.href = 'TLevel.html#' + key;
      matchLink.textContent = 'Read about the ' + ROUTES[key].name + ' T Level';
    });

    var second = counts[top[top.length - 1]];
    var tiedWithSecond = ranked.slice(top.length).filter(function (key) { return counts[key] === second; });
    if (counts[ranked[0]] === counts[ranked[ranked.length - 1]]) {
      also.textContent = 'Your answers were spread across all five routes, so it is worth reading about each one.';
      also.hidden = false;
    } else if (tiedWithSecond.length && second > 0) {
      also.textContent = 'You scored the same for ' + joinNames(tiedWithSecond) + ', so ' + (tiedWithSecond.length > 1 ? 'they are' : 'it is') + ' worth a look too.';
      also.hidden = false;
    } else {
      also.hidden = true;
    }

    // The result replaces the questions, like moving to a new page
    form.hidden = true;
    result.hidden = false;
    window.scrollTo(0, 0);
    title.focus({ preventScroll: true });
  });

  document.getElementById('quiz-restart').addEventListener('click', function () {
    form.hidden = false;
    form.reset();
  });

  form.addEventListener('reset', function () {
    form.hidden = false;
    result.hidden = true;
    error.hidden = true;
    questions.forEach(function (question) {
      question.classList.remove('quiz-question--missing');
    });
    // Runs before the browser clears the answers; focusing then is harmless
    showStep(0, true);
  });
})();
