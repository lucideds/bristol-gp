// Contact page: moves focus to the error summary or the "Message sent" heading after the
// server replies, and wires the "Ask a question" button to the T buddy chat widget.
// Loaded after chatWidget.js, so by DOMContentLoaded the widget's button exists if it loaded.
(function () {
  function init() {
    // Screen reader and keyboard users land on the result of sending the form.
    var focusTarget = document.querySelector('[data-contact-focus]');
    if (focusTarget) focusTarget.focus();

    // The assistant panel stays hidden unless the chat widget is on the page.
    var chatToggle = document.querySelector('.chat-toggle');
    var panel = document.getElementById('contact-assistant');
    var button = document.getElementById('contact-open-chat');
    if (!chatToggle || !panel || !button) return;
    panel.hidden = false;
    button.addEventListener('click', function () {
      // Opening the widget moves focus into its message box.
      if (chatToggle.getAttribute('aria-expanded') !== 'true') {
        chatToggle.click();
      } else {
        var input = document.querySelector('.chat-input');
        if (input) input.focus();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
