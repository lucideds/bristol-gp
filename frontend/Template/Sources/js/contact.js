// Contact page: moves focus to the error summary or the "Message sent" heading after the server
// replies, so screen reader and keyboard users land on the result of sending the form.
// The "Ask a question" button is handled by chatWidget.js (data-open-chat).
(function () {
  var focusTarget = document.querySelector('[data-contact-focus]');
  if (focusTarget) focusTarget.focus();
})();
