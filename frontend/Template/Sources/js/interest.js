// Register your interest page: moves focus to the error summary or the "Interest registered"
// heading after the server replies, so screen reader and keyboard users land on the result.
// The "Ask a question" button is handled by chatWidget.js (data-open-chat).
(function () {
  var focusTarget = document.querySelector('[data-interest-focus]');
  if (focusTarget) focusTarget.focus();
})();
