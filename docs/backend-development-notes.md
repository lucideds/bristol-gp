# Pippin: Backend development notes

Last updated 23 October 2026

These notes cover how the site's backend was built and the decisions behind it. For the request and response details of each route, see "Endpoint structures and schemas".

## Overview

The backend is one Flask app. main.py serves the pages from frontend/Template, handles accounts and the contact form, and registers the chat routes from chat_api.py as a blueprint. bot/bot.py posts contact messages to Slack. Everything is configured through environment variables, loaded from a .env file next to main.py. The .env file and site.db are both git-ignored.

To run it locally, install requirements.txt (Flask, Flask-Limiter, Flask-WTF, requests, python-dotenv and slack_bolt), then run python main.py. Set FLASK_DEBUG=1 to turn on debug mode. It's off unless you set it, so it can't be left on by accident.

Settings:

- SECRET_KEY signs the session cookie. If it isn't set, a random key is made at startup, so everyone gets signed out on every restart. It must be set for the live site.
- HTTPS=1 marks the cookie Secure. It's off by default because browsers drop Secure cookies over plain http://, which breaks local sign-in.
- OPENROUTER_API_KEY, plus the optional OPENROUTER_MODEL and OPENROUTER_SITE_URL, are for the chatbot.
- SLACK_BOT_TOKEN, SLACK_APP_TOKEN and SLACK_CHANNEL_ID are for the Slack bot.

## Database

The database is SQLite, stored in site.db next to main.py. A file database is enough at this size and needs no extra service. init_db() runs at startup and creates the tables with CREATE TABLE IF NOT EXISTS, so a fresh checkout just works. There's no migration tool, so any change to a table has to be applied to existing databases by hand.

- users: id, name, email (UNIQUE), password_hash and created_at.
- messages: id, name, email, message and created_at.

Each request opens one connection the first time it needs one (get_db() keeps it in g) and closes it when the request ends. Rows come back as sqlite3.Row, so columns can be read by name. Every query uses ? placeholders and never string formatting, which stops SQL injection.

Emails are stored in lower case, so the UNIQUE rule also catches "Bob@x.com" and "bob@x.com". If an account is deleted or the database is reset while someone is signed in, load_user() clears their session so they don't get stuck.

## Authentication

Accounts use email and password, and Flask's signed session cookie remembers who's signed in. The only thing stored in the cookie is user_id. load_user() looks the user up once per request and puts them in g.user, and templates see them as current_user.

- Passwords are hashed with pbkdf2:sha256 through Werkzeug. We don't use the scrypt default because the Python that ships with macOS doesn't support it.
- Passwords must be 8 to 128 characters and include a capital letter, a number and a special character (anything that isn't a letter, number or space). auth.js checks the same rules in the browser, but the server check is the one that counts. Existing accounts with older, weaker passwords can still sign in. Names can be up to 100 characters, and emails up to 254 and must match a basic pattern.
- A failed sign-in always says "Incorrect email or password.", so nobody can use it to find out which emails are registered.
- Lockout: each wrong password shows "attempt x out of 3". The 3rd locks sign-in for that email for 15 minutes (MAX_LOGIN_ATTEMPTS and LOCKOUT_MINUTES in main.py), and a successful sign-in resets the count. Attempts are stored in the login_attempts table by email, not user id, so an unregistered email counts and locks exactly like a real one. The lock is timed rather than permanent because there is no password reset yet.
- The session is cleared on sign-in and sign-up, so an old session can't be reused (session fixation).
- @login_required protects /account and sends visitors to /login?next=... first. is_safe_redirect() only follows next if it's a path on this site, and it treats backslashes as slashes so tricks like "/\evil.com" are caught.
- Logout is POST-only, so another site can't sign people out with a link.
- /api/session tells the nav bar whether to show "Sign in" or "Account".

The sign-in and sign-up forms are both on login.html. Each posts to its own route (/login or /register), and both show login.html again if there's an error.

## Members-only downloads

The T Level spec PDFs live in resources/specs, outside frontend/Template/Sources, because Flask serves everything in Sources to anyone. GET /download/<name> is the only way to get them. Signed-out visitors are redirected to /login?next=/t-levels, and the T Levels page shows them a greyed-out "Log in to download" button that comes back to the same tab after sign-in. Only names in the DOWNLOADS dict in main.py work, so the URL can't be used to read other files. Responses are attachments with Cache-Control: private, no-store, and the route allows 30 a minute. This is a simpler version of the planned resources design (algorithm 4): no resources table and no public files yet. To add a file, put it in resources/specs and add a line to DOWNLOADS.

## Contact form

POST /contact checks the fields (all required, name up to 100 characters, a valid email, message up to 2000 characters) and saves the message to the messages table. The form shows the error or a thank-you on the same page.

If the Slack settings are there, the message is also posted to the Slack channel as Block Kit, with Mark Handled, Priority, Reply Needed and View JSON buttons. Clicking a button replies in that message's thread. A few rules keep this safe:

- The database is the record. The message is saved before anything is sent to Slack, and if Slack fails the error is only logged, so the visitor still sees the thank-you.
- Form text is escaped (&, < and >) before it goes to Slack, so something like <!channel> can't ping everyone.
- If slack_bolt isn't installed, or the tokens aren't set, the site still runs and skips Slack. Token checking is turned off when the bot is imported, so a bad token can't stop the site starting.
- The bot listens for button clicks over Socket Mode, which means no public webhook URL is needed. main.py starts it in the background, and only once in debug mode, because the reloader runs the file twice. To run the bot without the website, use python -m bot.slack_bot_runner.

The Slack message has fields for phone, programme and enquiry type, but the form doesn't collect those yet, so they show as N/A.

## Chatbot integration

The chat widget (Sources/js/chatWidget.js) sends the whole conversation to our server, and chat_api.py forwards it to OpenRouter. The API key stays on the server and the server keeps no chat history. The system prompt is added on the server and can't be changed by visitors. It keeps the assistant on T Levels and Amazon placements, stops it inventing dates, pay or eligibility, tells it not to ask under-18s for personal details, and gives safeguarding signposting (trusted adult, 999, Childline).

Before anything is sent to OpenRouter, both chat routes run the same checks in check_chat_request():

- A rate limit of 10 requests a minute per IP address, shared by both routes so using both doesn't double it. The response includes a Retry-After header.
- A 100 KB cap on the request body. That's bigger than the 16 KB form limit, so it's raised for this request only.
- Message checks: 1 to 20 messages, each up to 4000 characters, role must be user or assistant (never system), and the last message must be from the user. Any extra fields are dropped.
- If the API key isn't set, the route returns a 503.

Error messages sent to visitors never include the key, OpenRouter's own response or a traceback. Those details only go to the server log. A 429 from OpenRouter shows visitors "busy", and any other OpenRouter error shows "unavailable".

### Model change

We started on nvidia/nemotron-3.5-lightning:free with reasoning turned off. On 16 October the default changed to nvidia/nemotron-3.5-super-vl:free for better answers, and reasoning was turned back on at medium effort. On 22 October two follow-up changes went in to stop replies timing out or getting cut off:

- The OpenRouter read timeout went up from 30 to 90 seconds.
- Reasoning effort dropped from medium to low, so less of the 4096 max_tokens budget is spent on thinking. Reasoning is set to exclude, so the thinking is never sent back to us or to visitors.

Temperature is 0.3. The model can be changed without a code edit by setting OPENROUTER_MODEL, which is read on every request. Note that the comments in chat_api.py next to CHAT_REASONING still say "medium". Those are out of date.

### Streaming

POST /api/chat/stream sends the reply as Server-Sent Events, so it appears as it's being written. Each event is a delta, then either done or error. generate_chat_stream() reads OpenRouter's stream and passes on only the content text, never the reasoning. It also handles a few edge cases:

- It decodes the stream as UTF-8 itself. Otherwise requests guesses the encoding and characters like ’ and £ come out garbled.
- It skips OpenRouter's keep-alive comments and the final chunk that only holds token usage, and it trims leading whitespace from the first chunk.
- A reply with no text, a stream that ends before [DONE], or one that runs past 120 seconds in total ends with an error event, not a half-finished reply.
- The connection to OpenRouter is always closed, even if the visitor leaves partway through.
- Cache-Control: no-cache and X-Accel-Buffering: no stop proxies holding the reply back.

The widget uses streaming first and falls back to /api/chat if streaming doesn't work. The widget gives up on /api/chat after 40 seconds, but the server now waits up to 90 seconds for OpenRouter, so a slow reply can time out in the browser while the server is still waiting. REQUEST_TIMEOUT_MS in the widget should be raised to match.

## Interest endpoint (planned)

This isn't built yet. The plan is for signed-in users to register interest in one or more placement areas (digital, business, media, finance or engineering). GET, POST and DELETE on /api/interest would be sign-in only (401 if not signed in), and POST and DELETE would need the X-CSRFToken header. The request and response shapes are in "Endpoint structures and schemas". To build it:

- Add an interests table: id, user_id (referencing users), route, role, school (optional), contact_consent, created_at and updated_at, with UNIQUE(user_id, route) so a POST updates an existing row instead of adding a duplicate.
- Add it to init_db(). Because it's a new table, existing databases pick it up at startup without a migration.
- Check route and role against fixed lists, keep school to 100 characters or fewer, and require contact_consent to be true.
- Add a JSON-friendly sign-in check that returns 401, since @login_required redirects to the login page, and apply the 10 a minute limit on POST.

## Hardening

Most of this went in during the code review on 14 October (commits fcead4b and 27390e4).

- CSRF: Flask-WTF protects every POST form, and each form has a hidden csrf_token. The chat blueprint is exempt because it only accepts application/json, which a normal HTML form on another site can't send.
- Rate limits: Flask-Limiter allows 10 a minute on /login and /register and 5 a minute on /contact. Chat has its own limiter in chat_api.py. Both store their counts in memory, so they reset on restart and aren't shared between server processes.
- Request size: anything over 16 KB is rejected with a 413, except chat, which allows up to 100 KB.
- Secrets: there used to be a hardcoded fallback SECRET_KEY. It's now a random key at startup with a warning, and debug mode only turns on if you opt in.
- Cookies: SameSite=Lax always, and Secure when HTTPS=1.
- Input: every field has a length limit, emails are checked and lower-cased, and SQL always uses placeholders.
- Errors: 404, 500, 400 (CSRF), 413 and 429 each have a handler, so visitors never see a stack trace. The 404 page suggests the closest real page, and a URL with only the capitals wrong (like /FAQS) gets a 301 to the real page. That redirect only happens for GET and HEAD, so submitted form data isn't lost.

Before going live:

- Set SECRET_KEY and HTTPS=1.
- Run behind a proper WSGI server, not app.run().
- If the site sits behind a proxy, add Werkzeug's ProxyFix. Otherwise every visitor shares the proxy's IP address for rate limiting. We don't read X-Forwarded-For directly because anyone can fake it.
- If there's more than one server process, move Flask-Limiter to a shared store such as Redis.
