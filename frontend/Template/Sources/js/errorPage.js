// "Go back" button on the error pages. Lives in its own file because the
// Content-Security-Policy blocks inline onclick="" handlers.
document.addEventListener('DOMContentLoaded', function () {
  var backButton = document.querySelector('[data-action="go-back"]');
  if (backButton) {
    backButton.addEventListener('click', function () {
      history.back();
    });
  }
});
