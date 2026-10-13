(function () {
  /**
   * Sends the user's message to the AI.
   * Not connected yet, so it does nothing and returns null (no reply shown).
   * @param {string} text The message the user typed (already trimmed).
   * @returns {Promise<string|null>} The AI's reply, or null for no reply.
   */
  async function sendMessage(text) {
    // TODO: call the AI here and return its reply.
    return null;
  }

  var panel, list, input, toggle;

  /**
   * Shows a message in the chat list.
   * @param {'user'|'assistant'} role Who sent the message.
   * @param {string} text The message text (shown as plain text, never HTML).
   */
  function addMessage(role, text) {
    var msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--' + role;
    msg.textContent = text;
    list.appendChild(msg);
    list.scrollTop = list.scrollHeight;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return; // ignore empty or space-only messages

    addMessage('user', text);
    input.value = '';

    try {
      var reply = await sendMessage(text);
      if (reply) addMessage('assistant', reply);
    } catch (err) {
      console.error('Chat message failed:', err);
    }
  }

  function isOpen() {
    return !panel.hidden;
  }

  function openChat() {
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Close chat');
    input.focus();
  }

  function closeChat() {
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open chat');
    toggle.focus();
  }

  // Adds the chat button and popup to the end of the page.
  function buildChat() {
    var html =
      '<button type="button" class="chat-toggle" aria-label="Open chat" aria-expanded="false" aria-controls="chat-panel">' +
        'T buddy' +
      '</button>' +
      '<div id="chat-panel" class="chat-panel" role="dialog" aria-label="Chat" hidden>' +
        '<div class="chat-header">' +
          '<span class="chat-title">ask T buddy</span>' +
          '<button type="button" class="chat-close" aria-label="Close chat">\u00D7</button>' +
        '</div>' +
        '<div class="chat-messages" aria-live="polite"></div>' +
        '<form class="chat-form">' +
          '<input type="text" class="chat-input" aria-label="Type a message" placeholder="Type a message\u2026" autocomplete="off">' +
          '<button type="submit" class="chat-send">Send</button>' +
        '</form>' +
      '</div>';

    document.body.insertAdjacentHTML('beforeend', html);

    toggle = document.querySelector('.chat-toggle');
    panel = document.getElementById('chat-panel');
    list = panel.querySelector('.chat-messages');
    input = panel.querySelector('.chat-input');

    toggle.addEventListener('click', function () {
      if (isOpen()) {
        closeChat();
      } else {
        openChat();
      }
    });
    panel.querySelector('.chat-close').addEventListener('click', closeChat);
    // Enter in the input submits the form.
    panel.querySelector('.chat-form').addEventListener('submit', handleSubmit);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) closeChat();
    });
  }

  // Build the chat once the page's HTML has loaded.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildChat);
  } else {
    buildChat();
  }
})();
