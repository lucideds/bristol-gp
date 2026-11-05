# Pippin: Backend development notes

Last updated 5 November 2026

These notes cover how the site's backend was built and the decisions behind it. For the request and response details of each route, see "Endpoint structures and schemas".

## Overview

The backend is one Flask app. main.py serves the pages from frontend/Template, handles accounts, the contact form, downloads and analytics, and registers the chat routes from chat_api.py as a blueprint. extensions.py holds the rate limiter, which both files share. bot/bot.py posts contact messages to Slack. Everything is configured through environment variables, loaded from a .env file next to main.py. The .env file and site.db are both git-ignored.

To run it locally, install requirements.txt (Flask, Flask-Limiter, Flask-WTF, requests, python-dotenv and slack_bolt), then run python main.py. Set FLASK_DEBUG=1 to turn on debug mode. It's off unless you set it, so it can't be left on by accident.

Settings:

- SECRET_KEY signs the session cookie. If it isn't set, the app makes one the first time it starts and saves it to .env, so everyone stays signed in across restarts. The file is created readable by its owner only, and it's locked while the key is written so two server processes starting at once can't make different keys. If .env can't be written, a random key is used for that run, with a warning, and everyone is signed out when the app restarts.
- HTTPS=1 marks the cookie Secure and turns on HSTS. It's off by default because browsers drop Secure cookies over plain http://, which breaks local sign-in.
- OPENROUTER_API_KEY, plus the optional OPENROUTER_MODEL and OPENROUTER_SITE_URL, are for the chatbot.
- SLACK_BOT_TOKEN, SLACK_APP_TOKEN and SLACK_CHANNEL_ID are for the Slack bot.
- ANALYTICS_EMAILS is a comma-separated list of account emails that may open the analytics page. If it's empty, nobody can.

## Pages and URLs

Every page extends base.html and has a short URL, such as /faqs or /t-levels. The pages used to be linked by their file names, so OLD_PAGE_URLS in main.py redirects addresses like /faqs.html or /signin.html to the short URL with a 301, keeping any query string. Old links and bookmarks still work, and new pages go in that list rather than getting their own .html routes.

## Database

The database is SQLite, stored in site.db next to main.py. A file database is enough at this size and needs no extra service. init_db() creates the tables with CREATE TABLE IF NOT EXISTS. It runs the first time get_db() opens the database, not when main.py is imported, so a fresh checkout just works and a test can point DATABASE at a temporary file before anything is created. There's no migration tool, so any change to an existing table has to be applied to existing databases by hand.

- users: id, name, email (UNIQUE), password_hash and created_at.
- messages: id, name, email, message and created_at.
- login_attempts: email (the primary key), failed_count and locked_until, for the sign-in lockout.
- analytics_events: id, kind, value and created_at, for the analytics page.
- interests and interest_routes: registered interest, one interests row per user and one interest_routes row per route chosen (see "Register your interest" below).

Each request opens one connection the first time it needs one (get_db() keeps it in g) and closes it when the request ends. Rows come back as sqlite3.Row, so columns can be read by name. Every query uses ? placeholders and never string formatting, which stops SQL injection.

Emails are stored in lower case, so the UNIQUE rule also catches "Bob@x.com" and "bob@x.com". If an account is deleted or the database is reset while someone is signed in, load_user() clears their session so they don't get stuck.

## Authentication

Accounts use email and password, and Flask's signed session cookie remembers who's signed in. The only thing stored in the cookie is user_id. load_user() looks the user up once per request and puts them in g.user, and templates see them as current_user.

- Passwords are hashed with pbkdf2:sha256 through Werkzeug. We don't use the scrypt default because the Python that ships with macOS doesn't support it.
- Passwords must be 8 to 128 characters and include a capital letter, a number and a special character (anything that isn't a letter, number or space). Names can be up to 100 characters, and emails up to 254 and must match a basic pattern. The checks are name_error(), email_error() and password_error() in main.py, shared by the sign-up, contact and account forms. auth.js checks the same rules in the browser with the same messages, but the server check is the one that counts. Existing accounts with older, weaker passwords can still sign in.
- A wrong email or password always gets the same message, "Incorrect email or password (attempt x out of 3).", so nobody can use it to find out which emails are registered. Empty boxes just get "Incorrect email or password." and don't count as an attempt.
- Lockout: the 3rd wrong password in a row locks sign-in for that email for 15 minutes (MAX_LOGIN_ATTEMPTS and LOCKOUT_MINUTES in main.py), and a successful sign-in resets the count. While it's locked, sign-in is refused without checking the password, and the message says how many minutes are left. Attempts are stored in the login_attempts table by email, not user id, so an unregistered email counts and locks exactly like a real one. Locks that have run out are deleted on the next failed sign-in. The lock is timed rather than permanent because there is no password reset yet.
- The session is cleared on sign-in, sign-up and password change, so an old session can't be reused (session fixation).
- @login_required protects /account, the account change forms and /analytics, and sends visitors to /login?next=... first. is_safe_redirect() only follows next if it's a path on this site, and it treats backslashes as slashes so tricks like "/\evil.com" are caught. Both sign-in and sign-up follow next.
- Logout is POST-only, so another site can't sign people out with a link.
- /api/session tells the nav bar whether to show "Sign in" or "Account".

The sign-in and sign-up forms are both on login.html. Each posts to its own route (/login or /register), and both show login.html again if there's an error.

## Changing account details

The account page lists the user's name, email and password, each with a "Change" link that opens a small form for just that detail, and the date they joined. The link points to /account?edit=name (or email, or password), so it works without JavaScript; auth.js opens the form in place instead. Each form posts to its own route, /account/name, /account/email or /account/password. ACCOUNT_FORMS in main.py maps each name to the function that makes the change and the message shown when it works.

- Changing the email or the password needs the current password (current_password_error()). The email is what people sign in with, so this stops someone using a computer that was left signed in to take over the account.
- A new email must be valid and not used by another account. A new password follows the same rules as sign-up.
- After a password change the session is cleared and the user is signed straight back in with a fresh one.
- On success the route redirects to /account with a message (Post/Redirect/GET), so refreshing doesn't send the form again. On an error the page is shown again with that form open and what the user typed.
- The routes are limited to 10 a minute, like sign-in, because two of them check a password.

There is no delete-account option yet, so deletion requests go through the Contact page.

## Members-only downloads

The T Level spec PDFs live in resources/specs, outside frontend/Template/Sources, because Flask serves everything in Sources to anyone. GET /download/<name> is the only way to get them. Signed-out visitors are redirected to /login?next=/t-levels, and the T Levels page shows them a greyed-out "Log in to download" button that comes back to the same tab after sign-in. Only names in the DOWNLOADS dict in main.py work, so the URL can't be used to read other files. Responses are attachments with Cache-Control: private, no-store, and the route allows 30 a minute. This is a simpler version of the planned resources design (algorithm 4): no resources table and no public files yet. To add a file, put it in resources/specs and add a line to DOWNLOADS.

## Contact form

POST /contact checks the fields (all required, name up to 100 characters, a valid email, message up to 2000 characters) and saves the message to the messages table. Each problem is shown next to its own field, and all of them are listed in an error summary at the top. When it works, the route redirects back to /contact, which shows the thank-you once, so refreshing can't send the message twice.

If the Slack settings are there, the message is also posted to the Slack channel as Block Kit, with the name, email and message, and Mark Handled, Priority, Reply Needed and View JSON buttons. The first three reply in that message's thread, and View JSON opens a pop-up with the raw submission. A few rules keep this safe:

- The database is the record. The message is saved before anything is sent to Slack, and if Slack fails the error is only logged, so the visitor still sees the thank-you.
- Form text is escaped (&, < and >) before it goes to Slack, so something like <!channel> can't ping everyone.
- If slack_bolt isn't installed, or the tokens aren't set, the site still runs and skips Slack. Token checking is turned off when the bot is imported, so a bad token can't stop the site starting.
- The bot listens for button clicks over Socket Mode, which means no public webhook URL is needed. main.py starts it in the background, and only once in debug mode, because the reloader runs the file twice. To run the bot without the website, use python -m bot.bot.

## Analytics

The analytics page (/analytics) shows the team how the site is used: enquiries and new accounts from the existing tables, plus searches, route views and quiz results from analytics_events. Each figure is shown in total and for the last 7 days, with the 10 most common searches.

- The browser sends events to POST /api/track. The search box sends what was typed, the T Levels page sends each route tab opened (once per visit), and the quiz sends its top match.
- Route views and quiz results are only accepted for the five real route names, and searches are lower-cased, have extra spaces removed and are capped at 100 characters, so the counts can't fill up with junk. The route allows 30 a minute.
- No user id or IP address is stored with an event, only what happened and when.
- Only signed-in users whose email is in ANALYTICS_EMAILS can open the page. Everyone else gets a 404, as if it didn't exist, and it's left out of the 404 page's "Did you mean" suggestions. The account page only shows its link to people who can open it.
- /api/track is exempt from CSRF for the same reason as the chat routes: it only accepts JSON.

## Chatbot integration

The chat widget (Sources/js/chatWidget.js) sends the whole conversation to our server, and chat_api.py forwards it to OpenRouter. The API key stays on the server and the server keeps no chat history. The system prompt is added on the server and can't be changed by visitors. It keeps the assistant on T Levels and Amazon placements, stops it inventing dates, pay or eligibility, tells it not to ask under-18s for personal details, and gives safeguarding signposting (trusted adult, 999, Childline).

### Guardrails

The prototype review on 2 November found that the assistant blocked off-topic subjects but not on-topic answers in the wrong form. Oli got it to explain the Engineering route as a Python script, and it would also write poems, answer as a pirate and return JSON. Since 3 November:

- The system prompt says how to reply, not just what about: plain English sentences only, in the assistant's own voice. No code of any kind, JSON, tables, poems, songs, stories or jokes, no characters or accents, and no other languages. Asked for any of these, it refuses in one sentence and offers to answer normally. It can still say in words whether a course involves coding.
- The prompt says visitors can't change the rules, whoever they claim to be, and that earlier assistant messages may have been edited, since the browser sends the history. It has four example refusals, including Oli's.
- chat_knowledge.md is wrapped in reference_information tags, and a short reminder of the rules follows it. Before this, the rules were about 18 KB back from where the model writes its reply.
- Temperature went from 0.3 to 0.2.
- The server checks replies with looks_like_code(): code fences, a reply that opens with { or [, and lines that start like code (def, print(, import, variable assignments, HTML tags, SELECT ... FROM and so on). The patterns are case-sensitive so normal sentences don't match. A match replaces the reply with CODE_REFUSAL. Assistant messages sent in the history get the same check, so a made-up earlier reply with code in it is passed on as the refusal.

Poems, role-play and other languages are only blocked by the prompt, because they can't be told apart from prose reliably. A second AI call to check each message would catch more but doubles the wait and the cost of each reply, so it's left as further development.

The cases are in check_chat_guardrails.py, which calls the real model through the OpenRouter key in .env: 14 that must be refused and 5 that must still be answered, such as "Do I need to know Python for the Digital T Level?" and a safeguarding message. Before the change, 4 of the original 12 attacks got through. After it, all 19 cases passed three runs each (57/57).

The assistant also answers from chat_knowledge.md, a hand-kept copy of the site's page text, which is added to the system prompt when the server starts. It doesn't update itself, so it has to be edited when page wording, password rules or the lockout settings change, followed by a server restart.

Before anything is sent to OpenRouter, both chat routes run the same checks:

- A rate limit of 10 requests a minute per IP address, shared by both routes so using both doesn't double it. It uses the same Flask-Limiter as the rest of the site (a shared limit with scope "chat"), and going over it returns a JSON 429 with a Retry-After header.
- A 100 KB cap on the request body. That's bigger than the 16 KB form limit, so it's raised for this request only.
- Message checks: 1 to 20 messages, each up to 4000 characters, role must be user or assistant (never system), and the last message must be from the user. Any extra fields are dropped.
- If the API key isn't set, the route returns a 503.

Problems are raised as a ChatError with a message and status code, and the blueprint turns that into the {"error": ...} response. Error messages sent to visitors are fixed constants at the top of chat_api.py. They never include the key, OpenRouter's own response or a traceback, which only go to the server log. A 429 from OpenRouter shows visitors "busy", and any other OpenRouter error shows "unavailable".

### Model change

We started on nvidia/nemotron-3.5-lightning:free with reasoning turned off. On 16 October the default changed to nvidia/nemotron-3.5-super-vl:free for better answers, and reasoning was turned back on at medium effort. On 22 October two follow-up changes went in to stop replies timing out or getting cut off:

- The OpenRouter read timeout went up from 30 to 90 seconds.
- Reasoning effort dropped from medium to low, so less of the 4096 max_tokens budget is spent on thinking. Reasoning is set to exclude, so the thinking is never sent back to us or to visitors.

On 5 November the default changed to anthropic/claude-sonnet-5.5, because we wanted better performance from the chat assistant than the free Nemotron model gave. It's a paid model, so it also doesn't share the free tier's rate limits. The 57/57 guardrail result above was measured on Nemotron, so check_chat_guardrails.py needs to be run again on Sonnet.

At the same time, every request started sending OpenRouter's provider settings {"zdr": true, "data_collection": "deny"} (CHAT_PROVIDER in chat_api.py). OpenRouter then only routes the request to endpoints with zero data retention, and fails it rather than fall back to one that stores chat messages or trains on them. This applies whatever OPENROUTER_MODEL is set to. Before this, zero data retention relied on production setting the paid Nemotron model, because the :free default kept data. smoke_test.py checks that the settings are sent.

Temperature is 0.2 (0.3 until 3 November). The model can be changed without a code edit by setting OPENROUTER_MODEL, which is read on every request.

### Streaming

POST /api/chat/stream sends the reply as Server-Sent Events, so it appears as it's being written. Each event is a delta, then either done or error. If the reply so far looks like code, the server stops reading, sends a replace event with the refusal (the widget swaps out any text already shown) and then done. generate_chat_stream() reads OpenRouter's stream and passes on only the content text, never the reasoning. It also handles a few edge cases:

- It decodes the stream as UTF-8 itself. Otherwise requests guesses the encoding and characters like ’ and £ come out garbled.
- It skips OpenRouter's keep-alive comments and the final chunk that only holds token usage, and it trims leading whitespace from the first chunk.
- A reply with no text, a stream that ends before [DONE], or one that runs past 120 seconds in total ends with an error event, not a half-finished reply.
- The connection to OpenRouter is always closed, even if the visitor leaves partway through.
- Cache-Control: no-cache and X-Accel-Buffering: no stop proxies holding the reply back.

The widget uses streaming first and falls back to /api/chat if streaming doesn't work. The widget gives up on /api/chat after 40 seconds, but the server waits up to 90 seconds for OpenRouter, so a slow reply can time out in the browser while the server is still waiting. REQUEST_TIMEOUT_MS in the widget should be raised to match.

## Register your interest

Built on 2 November 2026. Signed-in users can register interest in one or more placement routes on /interest, in three steps (About you, Your interests, Check and send), or through GET, POST and DELETE on /api/interest. They can see, change and remove it from the account page. The request and response shapes are in "Endpoint structures and schemas".

- Storage: two tables, added to init_db(), so existing databases pick them up the next time the app opens them, without a migration. interests has one row per user (user_id as the primary key, role, school, year_group, contact_consent, created_at, updated_at). interest_routes has one row per route chosen, with (user_id, route) as the primary key. The first plan was one row per route with the role and school repeated on each. That suited a per-route API but not a form where you tick several routes, so the answers about the person and the routes were split.
- One user, one interest: save_interest() upserts the interests row and replaces the user's interest_routes rows, so sending again updates rather than duplicates. remove_interest() deletes from both tables itself, because SQLite only enforces REFERENCES when PRAGMA foreign_keys is on.
- Shared logic: the page and the API use the same checks (role_error(), school_error(), routes_error(), year_group_error(), consent_error()) and the same save and remove functions, so they can't disagree. Roles, routes and year groups are checked against fixed lists. School is 100 characters or fewer. contact_consent must be true.
- Steps: one route, with the step picked by ?step=. The answers so far are kept in the session (interest_draft) until the last step saves them, so the page works without JavaScript. Consent is asked for again each time, even when updating saved answers, because a consent box should never be ticked for you.
- Sign-in: the page shows a sign-in panel rather than redirecting, so visitors see what it's for first. The API has its own api_login_required(), which returns a 401 JSON error instead of redirecting to /login.
- Slack: saving, updating and removing call send_interest_to_slack() in bot/bot.py. The message has the name, email, role, school, year group and routes (just name and email for a removal), with the Mark Handled and View JSON buttons. If Slack fails, the error is logged and the answers stay saved.
- Removing: the account page's Remove link opens a confirmation (/account?edit=remove-interest), and only "Yes, remove it" deletes anything. Removing doesn't delete the earlier Slack messages about that person.
- Limits: 10 POSTs a minute on /interest, and 10 POSTs or DELETEs a minute on /api/interest. The CSRF error handler returns JSON for /api/ paths.

## Hardening

Most of this went in during the code reviews on 14 October (commits fcead4b and 27390e4) and 29 October.

- CSRF: Flask-WTF protects every POST form, and each form has a hidden csrf_token. The chat blueprint and /api/track are exempt because they only accept application/json, which a normal HTML form on another site can't send.
- Rate limits: Flask-Limiter (set up in extensions.py) allows 10 a minute on /login, /register, the account change forms, /interest and /api/interest, 5 a minute on /contact, 30 a minute on downloads and /api/track, and 10 a minute shared across the chat routes. The counts are kept in memory, so they reset on restart and aren't shared between server processes.
- Request size: anything over 16 KB is rejected with a 413, except chat, which allows up to 100 KB.
- Secrets: there used to be a hardcoded fallback SECRET_KEY. The app now makes a random one and saves it to .env, and debug mode only turns on if you opt in.
- Cookies: SameSite=Lax always, and Secure when HTTPS=1.
- Security headers on every response: a Content Security Policy that only allows the site's own scripts, styles, fonts and requests (Amazon Ember and the readable-font option's Atkinson Hyperlegible are both self-hosted), with inline scripts, styles and onclick="" blocked. Also X-Frame-Options: DENY, X-Content-Type-Options: nosniff, a strict Referrer-Policy, and HSTS when HTTPS=1. This is why all page behaviour lives in Sources/js and all styles in Sources/css.
- Input: every field has a length limit, emails are checked and lower-cased, and SQL always uses placeholders.
- Errors: 404, 500, 400 (CSRF), 413 and 429 each have a handler, so visitors never see a stack trace. The 404 page suggests the closest real page, and a URL with only the capitals wrong (like /FAQS) gets a 301 to the real page. That redirect only happens for GET and HEAD, so submitted form data isn't lost.

Before going live:

- Keep SECRET_KEY the same between deploys, either the one saved to .env or one you set yourself, and set HTTPS=1.
- Run behind a proper WSGI server, not app.run(). The Slack bot is only started from main.py's own start-up block, so start it separately with python -m bot.bot.
- If the site sits behind a proxy, add Werkzeug's ProxyFix. Otherwise every visitor shares the proxy's IP address for rate limiting. We don't read X-Forwarded-For directly because anyone can fake it.
- If there's more than one server process, move Flask-Limiter to a shared store such as Redis.
