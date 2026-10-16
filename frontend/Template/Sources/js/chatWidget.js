(function () {
  // Work out the chat API URL from this script's own URL, like topNavBar.js does.
  // (document.currentScript only works here at the top level, not in callbacks.)
  // The script lives in Template/Sources/js/, so the site root is two folders up.
  var script = document.currentScript;
  var API_URL = new URL('../../api/chat', script.src).href;            // Whole reply at once (fallback).
  var STREAM_URL = new URL('../../api/chat/stream', script.src).href;  // Reply streamed word by word.
  var SPARKLE_URL = new URL('../assests/chat-ai-sparkle.svg', script.src).href;              // Header + launcher icon.
  var SPARKLE_SMALL_URL = new URL('../assests/chat-ai-sparkle-small.svg', script.src).href;  // "AI-generated" badge icon.
  var SEND_ICON_URL = new URL('../assests/chat-send.svg', script.src).href;                  // Send button icon.
  var LEARN_MORE_URL = new URL('../../faqs.html', script.src).href;                           // Disclaimer link.

  var MAX_HISTORY = 12;          // Most recent messages sent to the server each time.
  var MAX_STORED_REPLY = 4000;   // Long replies are shortened in the history (not on screen).
  var REQUEST_TIMEOUT_MS = 40000;       // For /api/chat: give up after this long.
  var STREAM_IDLE_TIMEOUT_MS = 40000;   // For streaming: give up if nothing arrives for this long.
  var TIMEOUT_ERROR = 'The assistant took too long to reply. Please try again.';
  var INTERRUPTED_ERROR = 'The assistant\u2019s reply was interrupted. Please try again.';
  var GENERIC_ERROR = 'Sorry, something went wrong. Please try again.';

  var history = [];   // This visit's conversation: [{role, content}, ...]
  var pending = false; // True while waiting for a reply.
  var greeted = false;

  var panel, list, input, toggle, sendButton, typing;
  var streamEl = null;   // The bubble a reply is being streamed into.
  var streamText = null; // The text inside it.

  /**
   * Sends the conversation to the server and returns the AI's reply.
   * @param {{role: string, content: string}[]} messages The conversation so far.
   * @returns {Promise<string>} The reply text.
   * @throws {Error} With a friendly message the user can read.
   */
  async function sendMessage(messages) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);
    var res;
    try {
      res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: messages }),
        signal: controller.signal
      });
    } catch (err) {
      if (err && err.name === 'AbortError') {
        throw new Error(TIMEOUT_ERROR);
      }
      throw new Error("Sorry, I couldn't reach the assistant. Please check your connection and try again.");
    } finally {
      clearTimeout(timer);
    }

    var data = {};
    try {
      data = await res.json();
    } catch (e) {
      data = {};
    }
    if (!res.ok || !data || typeof data.reply !== 'string') {
      throw new Error((data && typeof data.error === 'string' && data.error) || GENERIC_ERROR);
    }
    return data.reply;
  }

  // An error that means "streaming didn't work here, try the normal /api/chat route instead".
  function fallbackError() {
    var err = new Error(GENERIC_ERROR);
    err.fallback = true;
    return err;
  }

  /**
   * Sends the conversation to the streaming endpoint and calls onDelta with each new bit of text.
   * The server sends Server-Sent Events: "data: {...}" lines with {"delta": "text"}, then
   * {"done": true} at the end, or {"error": "message"} if something went wrong.
   * @param {{role: string, content: string}[]} messages The conversation so far.
   * @param {function(string): void} onDelta Called with each new piece of reply text.
   * @returns {Promise<string>} The whole reply once it has finished.
   * @throws {Error} With a friendly message. err.fallback is true if /api/chat should be tried
   *   instead (only when no text was shown), and err.partial holds any text already shown.
   */
  async function streamMessage(messages, onDelta) {
    if (!window.ReadableStream || !window.TextDecoder) throw fallbackError();

    var controller = new AbortController();
    var timer = null;
    // Restarted whenever something arrives, so long replies that keep coming aren't cut off.
    function resetTimer() {
      clearTimeout(timer);
      timer = setTimeout(function () { controller.abort(); }, STREAM_IDLE_TIMEOUT_MS);
    }
    var text = '';

    function fail(err) {
      err.partial = text;
      return err;
    }

    try {
      resetTimer();
      var res;
      try {
        res = await fetch(STREAM_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
          body: JSON.stringify({ messages: messages }),
          signal: controller.signal
        });
      } catch (err) {
        if (err && err.name === 'AbortError') throw fail(new Error(TIMEOUT_ERROR));
        throw fail(fallbackError());
      }
      resetTimer();

      // Streaming route missing (e.g. an older server): use /api/chat instead.
      if (res.status === 404 || res.status === 405) throw fail(fallbackError());
      if (!res.ok) {
        // The server said what went wrong (rate limit, bad request...). Retrying won't help.
        var data = {};
        try {
          data = await res.json();
        } catch (e) {
          data = {};
        }
        throw fail(new Error((data && typeof data.error === 'string' && data.error) || GENERIC_ERROR));
      }
      var type = res.headers.get('Content-Type') || '';
      if (type.indexOf('text/event-stream') === -1 || !res.body || !res.body.getReader) {
        throw fail(fallbackError());
      }

      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      while (true) {
        var result;
        try {
          result = await reader.read();
        } catch (err) {
          if (err && err.name === 'AbortError') throw fail(new Error(TIMEOUT_ERROR));
          break; // Connection dropped; handled below.
        }
        resetTimer();
        if (result.done) break;

        buffer += decoder.decode(result.value, { stream: true }).replace(/\r\n/g, '\n');
        var events = buffer.split('\n\n');
        buffer = events.pop(); // The last piece may be half an event; keep it for next time.

        for (var i = 0; i < events.length; i++) {
          var dataLines = [];
          var lines = events[i].split('\n');
          for (var j = 0; j < lines.length; j++) {
            var line = lines[j];
            if (line.indexOf('data:') === 0) {
              line = line.slice(5);
              if (line.charAt(0) === ' ') line = line.slice(1);
              dataLines.push(line);
            }
            // Anything else (e.g. ": comment" lines) is ignored.
          }
          if (!dataLines.length) continue;

          var ev;
          try {
            ev = JSON.parse(dataLines.join('\n'));
          } catch (e) {
            continue; // Skip anything we can't read.
          }
          if (!ev) continue;
          if (typeof ev.delta === 'string') {
            text += ev.delta;
            onDelta(ev.delta);
          } else if (typeof ev.error === 'string') {
            var serverErr = new Error(ev.error || GENERIC_ERROR);
            serverErr.serverError = true;
            throw fail(serverErr);
          } else if (ev.done === true) {
            try { reader.cancel(); } catch (e) { /* already finished */ }
            return text;
          }
        }
      }

      // The stream ended without "done" or "error".
      if (text === '') throw fail(fallbackError());
      throw fail(new Error(INTERRUPTED_ERROR));
    } finally {
      clearTimeout(timer);
    }
  }

  function scrollToBottom() {
    list.scrollTop = list.scrollHeight;
  }

  // The "AI-generated" label shown at the top of every AI reply.
  function makeAiBadge() {
    var badge = document.createElement('span');
    badge.className = 'chat-badge chat-msg-badge';
    var icon = document.createElement('img');
    icon.src = SPARKLE_SMALL_URL;
    icon.alt = '';
    icon.className = 'chat-badge-icon';
    badge.appendChild(icon);
    badge.appendChild(document.createTextNode('AI-generated'));
    return badge;
  }

  // Puts the text in a message bubble (as plain text, never HTML). AI replies also get the badge.
  function fillMessage(msg, role, text) {
    if (role === 'assistant') {
      msg.appendChild(makeAiBadge());
      var body = document.createElement('span');
      body.className = 'chat-msg-text';
      body.textContent = text;
      msg.appendChild(body);
    } else {
      msg.textContent = text;
    }
  }

  /**
   * Shows a message in the chat list.
   * @param {'user'|'assistant'|'error'} role Who sent the message.
   * @param {string} text The message text (shown as plain text, never HTML).
   * @returns {HTMLElement} The new message element.
   */
  function addMessage(role, text) {
    var msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--' + role;
    fillMessage(msg, role, text);
    list.appendChild(msg);
    scrollToBottom();
    return msg;
  }

  // Creates the bubble a streamed reply is written into.
  // It's hidden from screen readers while it grows, so they don't read out every word;
  // finishStreamBubble() swaps in a normal bubble that is read out once.
  function startStreamBubble() {
    streamEl = document.createElement('div');
    streamEl.className = 'chat-msg chat-msg--assistant chat-msg--streaming';
    streamEl.setAttribute('aria-hidden', 'true');
    streamEl.appendChild(makeAiBadge());
    var body = document.createElement('span');
    body.className = 'chat-msg-text';
    streamText = document.createTextNode('');
    body.appendChild(streamText);
    streamEl.appendChild(body);
    list.setAttribute('aria-busy', 'true');
    list.appendChild(streamEl);
    scrollToBottom();
  }

  // Adds text to the streaming bubble (as plain text, never HTML).
  function appendStream(delta) {
    // Only follow the new text if the user hasn't scrolled up to read something.
    var nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
    streamText.appendData(delta);
    if (nearBottom) scrollToBottom();
  }

  // Replaces the streaming bubble with a normal one holding the whole text (or removes it if empty).
  function finishStreamBubble() {
    if (streamEl && streamEl.parentNode) {
      var fullText = streamText.data.trim();
      if (fullText) {
        var msg = document.createElement('div');
        msg.className = 'chat-msg chat-msg--assistant';
        fillMessage(msg, 'assistant', fullText);
        list.replaceChild(msg, streamEl);
      } else {
        list.removeChild(streamEl);
      }
    }
    streamEl = null;
    streamText = null;
    list.removeAttribute('aria-busy');
  }

  // Shows the "T buddy is typing…" bubble with three animated dots.
  function showTyping() {
    typing = document.createElement('div');
    typing.className = 'chat-msg chat-msg--assistant chat-msg--typing';

    var label = document.createElement('span');
    label.className = 'chat-visually-hidden';
    label.textContent = 'T buddy is typing\u2026';
    typing.appendChild(label);

    var dots = document.createElement('span');
    dots.setAttribute('aria-hidden', 'true');
    for (var i = 0; i < 3; i++) {
      var dot = document.createElement('span');
      dot.className = 'chat-typing-dot';
      dots.appendChild(dot);
    }
    typing.appendChild(dots);

    list.appendChild(typing);
    scrollToBottom();
  }

  function hideTyping() {
    if (typing && typing.parentNode) typing.parentNode.removeChild(typing);
    typing = null;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    var text = input.value.trim();
    if (pending || !text) return; // ignore empty messages, or new ones while waiting

    addMessage('user', text);
    history.push({ role: 'user', content: text });
    input.value = '';

    pending = true;
    sendButton.disabled = true;
    showTyping();

    var shown = false; // Has any reply text appeared yet?
    try {
      var reply = await streamMessage(history.slice(-MAX_HISTORY), function (delta) {
        if (!shown) {
          shown = true;
          hideTyping();
          startStreamBubble();
        }
        appendStream(delta);
      });
      finishStreamBubble(); // Screen readers hear the whole reply once.
      // Only saved to the history once the reply has fully arrived.
      history.push({ role: 'assistant', content: reply.trim().slice(0, MAX_STORED_REPLY) });
    } catch (err) {
      if (err && err.fallback && !shown) {
        // Streaming didn't work and nothing was shown yet, so ask for the whole reply instead.
        // The typing bubble stays up while we wait.
        try {
          var full = await sendMessage(history.slice(-MAX_HISTORY));
          hideTyping();
          addMessage('assistant', full);
          history.push({ role: 'assistant', content: full.slice(0, MAX_STORED_REPLY) });
          return; // "finally" below still runs.
        } catch (err2) {
          err = err2;
        }
      }
      hideTyping();
      finishStreamBubble(); // Keep any text that already arrived on screen.
      // Forget the failed message so a retry doesn't send it twice (it stays on screen).
      history.pop();
      addMessage('error', (err && err.message) || GENERIC_ERROR);
    } finally {
      hideTyping();
      if (streamEl) finishStreamBubble();
      list.removeAttribute('aria-busy');
      pending = false;
      sendButton.disabled = false;
      if (isOpen()) input.focus();
    }
  }

  function isOpen() {
    return !panel.hidden;
  }

  function openChat() {
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Close T buddy chat');
    if (!greeted) {
      greeted = true;
      // Shown only, not sent to the server.
      addMessage('assistant', "Hi, I'm T buddy. I can help with T Levels, industry placements at Amazon, preparing for a placement and finding your way around this site. How can I help?");
    }
    input.focus();
  }

  function closeChat() {
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open T buddy chat');
    toggle.focus();
  }

  // Adds the chat button and popup to the end of the page.
  function buildChat() {
    var html =
      '<button type="button" class="chat-toggle" aria-label="Open T buddy chat" aria-expanded="false" aria-controls="chat-panel">' +
        '<img src="' + SPARKLE_URL + '" alt="" class="chat-toggle-icon">' +
        'T buddy' +
      '</button>' +
      '<div id="chat-panel" class="chat-panel" role="dialog" aria-labelledby="chat-title" aria-describedby="chat-disclaimer" hidden>' +
        '<div class="chat-header">' +
          '<span id="chat-title" class="chat-title">' +
            '<img src="' + SPARKLE_URL + '" alt="" class="chat-title-icon">' +
            'Ask a question' +
          '</span>' +
          '<span class="chat-badge chat-header-badge">AI assistant</span>' +
          '<button type="button" class="chat-close" aria-label="Close chat">\u00D7</button>' +
        '</div>' +
        '<div class="chat-messages" role="log" aria-live="polite" aria-relevant="additions"></div>' +
        '<form class="chat-form">' +
          '<input type="text" class="chat-input" aria-label="Type a message" placeholder="Type your question" autocomplete="off" maxlength="2000">' +
          '<button type="submit" class="chat-send" aria-label="Send">' +
            '<img src="' + SEND_ICON_URL + '" alt="" class="chat-send-icon">' +
          '</button>' +
        '</form>' +
        '<p id="chat-disclaimer" class="chat-disclaimer">' +
          'AI responses may be inaccurate. Check important information and don\u2019t share personal details. ' +
          '<a href="' + LEARN_MORE_URL + '">Learn more</a>' +
        '</p>' +
      '</div>';

    document.body.insertAdjacentHTML('beforeend', html);

    toggle = document.querySelector('.chat-toggle');
    panel = document.getElementById('chat-panel');
    list = panel.querySelector('.chat-messages');
    input = panel.querySelector('.chat-input');
    sendButton = panel.querySelector('.chat-send');

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
