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

  function joinNames(keys) {
    var names = keys.map(function (key) { return ROUTES[key].name; });
    if (names.length < 2) return names.join('');
    return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();

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
      error.textContent = 'Please answer every question to see your result.';
      error.hidden = false;
      firstUnanswered.querySelector('input').focus();
      return;
    }
    error.hidden = true;

    // Most answers first; equal counts keep ROUTE_ORDER (sort is stable)
    var ranked = ROUTE_ORDER.slice().sort(function (a, b) { return counts[b] - counts[a]; });
    var top = ranked.slice(0, matchCards.length);

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

    result.hidden = false;
    title.focus();
  });

  form.addEventListener('reset', function () {
    result.hidden = true;
    error.hidden = true;
    questions.forEach(function (question) {
      question.classList.remove('quiz-question--missing');
    });
  });
})();
