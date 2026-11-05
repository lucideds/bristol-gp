# T Level placements at Amazon

This is a website about T Levels and T Level industry placements at Amazon, built for the Amazon Emerging Talent Programs team. Its audience is students, parents and carers, and teachers or careers advisers.

The site is a small Flask app. It serves HTML pages, stores user accounts, contact form messages and registered interest in SQLite, runs an AI chat assistant through OpenRouter, and can post contact form messages and registered interest to a Slack channel.

## Quick start

You need Python 3.9 or newer. 

```bash
cd bristol-gp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the values (see "Configuration")
FLASK_DEBUG=1 python main.py
```

Open http://127.0.0.1:5000.

`FLASK_DEBUG=1` turns on Flask's debugger and auto-reload. Leave it off anywhere other than your own machine.

The database file `site.db` is created next to `main.py` the first time a page needs it. To reset the data, stop the app and delete `site.db`.

Open the pages through Flask, not by double-clicking the HTML files. The templates contain Jinja tags such as `{{ csrf_token() }}`, and the forms, sign-in state and chat widget all need the server.

## Configuration

Settings are read from environment variables. `main.py` and `bot/bot.py` also load a `.env` file from the project folder. Real environment variables take priority over `.env`. Never commit `.env`; it is already in `.gitignore`.

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | No | Signs the session cookie. If it is unset, the app generates one on first start and saves it to `.env`, so restarts keep everyone signed in. If `.env` can't be written, a random key is used for that run and everyone is signed out when the app restarts. |
| `OPENROUTER_API_KEY` | For the chat widget | OpenRouter API key. Without it, the chat API returns 503 and the rest of the site still works. |
| `OPENROUTER_MODEL` | No | Model ID. Defaults to `anthropic/claude-sonnet-5.5`. Every request is limited to zero data retention endpoints (`CHAT_PROVIDER` in `chat_api.py`). |
| `OPENROUTER_SITE_URL` | No | Public URL of the site, sent to OpenRouter as the `HTTP-Referer` header. Defaults to the request's host URL. |
| `SLACK_BOT_TOKEN` | For Slack | Bot token (`xoxb-...`) used to post messages. |
| `SLACK_CHANNEL_ID` | For Slack | Channel that receives contact form messages. |
| `SLACK_APP_TOKEN` | For Slack buttons | App-level token (`xapp-...`) for Socket Mode, so the buttons on Slack messages respond. |
| `FLASK_DEBUG` | No | Set to `1` for debug mode. |
| `ANALYTICS_EMAILS` | For the analytics page | Comma-separated account emails that may open `/analytics`. If it's empty, nobody can. |
| `HTTPS` | When served over HTTPS | Set to `1` to mark the session cookie `Secure`. Leave it unset for local `http://` testing, or the browser drops the cookie and nobody can stay signed in. |

The chat and Slack settings are read when they are used, so a missing value turns off that feature without stopping the site.

## Project layout

```
bristol-gp/
├── main.py                 Flask app: page routes, accounts, contact form, register interest, error pages, database setup
├── chat_api.py             Blueprint for /api/chat and /api/chat/stream (OpenRouter proxy)
├── extensions.py           The rate limiter, shared by main.py and chat_api.py
├── chat_knowledge.md       Facts about the site that the chat assistant answers from
├── bot/
│   └── bot.py              Slack bot: posts contact messages and interest, handles the message buttons
├── send_slack_test.py      Sends one fake contact message to Slack to check the setup
├── seed_db.py              Fills site.db with made-up test data (--reset removes it)
├── check_chat_guardrails.py  Sends test conversations to the real chat model and checks it refuses or answers
├── smoke_test.py           Runs the backend through the Flask test client and prints PASS or FAIL per case
├── requirements.txt
├── .env.example            Template for .env
├── site.db                 SQLite database (created on first run, not committed)
├── resources/specs/        Members-only T Level spec PDFs, served by /download/<name>
└── frontend/Template/      Jinja templates (Flask's template_folder)
    ├── base.html           Shared <head> and <body>; every page extends it
    ├── home.html, TLevel.html, advice.html, faqs.html, quiz.html, contact.html, privacy.html
    ├── login.html          Sign-in and sign-up forms on one page
    ├── account.html        Signed-in users only
    ├── interest.html       Register your interest, three steps (sign-in panel when signed out)
    ├── analytics.html      Site analytics, for emails listed in ANALYTICS_EMAILS
    ├── 404.html, 500.html
    └── Sources/            Static files (Flask's static_folder, served at /Sources/...)
        ├── css/
        ├── fonts/          Self-hosted Amazon Ember, and Atkinson Hyperlegible with its licence
        ├── js/
        └── assets/         Images and icons
```

## Backend

### Routes

Every link on the site uses these short URLs. The old file-name addresses, such as `/faqs.html` or `/signin.html`, redirect to them (see `OLD_PAGE_URLS` in `main.py`), so old links and bookmarks keep working.

| URL | Methods | Template or response |
|---|---|---|
| `/` | GET | `home.html` |
| `/t-levels` | GET | `TLevel.html` |
| `/advice` | GET | `advice.html` |
| `/faqs` | GET | `faqs.html` |
| `/privacy` | GET | `privacy.html` |
| `/quiz` | GET | `quiz.html` |
| `/contact` | GET, POST | `contact.html`. POST saves the message and posts it to Slack. Limited to 5 POSTs per minute per IP. |
| `/login` | GET, POST | `login.html`, sign-in form. Limited to 10 POSTs per minute. |
| `/register` | GET, POST | `login.html`, sign-up form. Limited to 10 POSTs per minute. |
| `/logout` | POST | Clears the session and redirects home. |
| `/account` | GET | `account.html`. Requires sign-in. `?edit=name`, `?edit=email` or `?edit=password` opens that change form, and `?edit=remove-interest` opens the "Remove your interest" confirmation, so the links work without JavaScript. |
| `/account/<form>` | POST | Saves one account detail (`name`, `email` or `password`), or removes the user's interest (`remove-interest`). See `ACCOUNT_FORMS` in `main.py`. Redirects to `/account` with a success message, or shows the page again with the form open and the error. Requires sign-in. Limited to 10 POSTs per minute. |
| `/interest` | GET, POST | `interest.html`, Register your interest. Visitors who aren't signed in see links to sign in or create an account. `?step=about`, `?step=interests` or `?step=check` picks the step; each step's POST checks only that step, keeps the answers in the session and redirects to the next step. The final POST saves the answers and posts them to Slack. Limited to 10 POSTs per minute. |
| `/analytics` | GET | `analytics.html`, a dashboard of totals (with the last 7 days), registered interest by route, role and year group (the last two as donut charts) and school, visitor activity per day for 14 days, programme views, quiz results and top searches. Requires sign-in with an email in `ANALYTICS_EMAILS`; anyone else signed in gets a 404. |
| `/download/<name>` | GET | A spec PDF from `resources/specs/`. Requires sign-in. Limited to 30 per minute. |
| `/accessibility` | GET | Redirects to `/#accessibility`. The settings are now a popup on every page. |
| `/<page>.html` | GET | Redirects an old file-name address to its short URL. |
| `/api/track` | POST | Records an analytics event, `{"kind": "search" \| "view" \| "quiz", "value": "..."}`. JSON only, 30 per minute per IP. Views and quiz results must be one of the five route names; searches are lower-cased and up to 100 characters. |
| `/api/session` | GET | `{"signed_in": bool, "name": ...}`, used by `topNavBar.js`. |
| `/api/interest` | GET, POST, DELETE | The signed-in user's interest as JSON. GET returns `{"interest": {...} \| null}`. POST `{"role", "school", "year_group", "routes": [...], "contact_consent": true}` saves it (201 new, 200 updated, 400 `{"errors": {...}}`). DELETE removes it (204). 401 if not signed in. POST and DELETE need the `X-CSRFToken` header and are limited to 10 per minute. |
| `/api/chat` | POST | Chat reply as JSON. |
| `/api/chat/stream` | POST | Chat reply as Server-Sent Events. |

### Adding a page

1. Create `frontend/Template/<name>.html` that extends `base.html`. List the page's own stylesheets and scripts (file names without the extension) and fill in the title and content:

   ```jinja
   {% extends "base.html" %}
   {% set page_css = ["components", "example"] %}
   {% set page_js = ["example"] %}
   {% block title %}Example{% endblock %}
   {% block content %}
     <main class="tlevel-page">...</main>
   {% endblock %}
   ```

2. Add a route in `main.py` next to the other public pages:

   ```python
   @app.route("/example")
   def example():
       return render_template("example.html")
   ```

3. To show it in the navigation, add it to the link lists in `Sources/js/topNavBar.js` and, if needed, `Sources/js/footer.js`, using the short URL (`'example'`). `topNavBar.js` also has a list of pages used by the search box. Link to it from other pages as `/example`.
4. To make a page sign-in only, add `@login_required` under the route decorators.

The 404 handler builds its list of pages from the routes, so a new page is included in "Did you mean...?" suggestions and case-correcting redirects (`/FAQS` goes to `/faqs`) without further work.

### Database

`init_db()` in `main.py` creates the tables if they don't exist. `get_db()` runs it the first time the app opens the database:

- `users`: `id`, `name`, `email` (unique, stored in lower case), `password_hash`, `created_at`
- `messages`: `id`, `name`, `email`, `message`, `created_at`
- `login_attempts`: failed sign-ins per email, used for the lockout (3 wrong passwords lock that email for 15 minutes). Expired locks are cleared out on later failed sign-ins.
- `analytics_events`: `id`, `kind` (`search`, `view` or `quiz`), `value`, `created_at`. Sent by `topNavBar.js` (searches), `tlevelTabs.js` (each route tab, once per visit) and `quiz.js` (the top match). No user id or IP is stored.
- `interests`: one row per user who registered interest: `user_id` (primary key), `role`, `school`, `year_group`, `contact_consent` (always 1), `created_at`, `updated_at`.
- `interest_routes`: `user_id`, `route`, one row per route chosen, primary key `(user_id, route)`. `save_interest()` replaces a user's rows each time, and `remove_interest()` deletes from both tables, since SQLite doesn't enforce the `REFERENCES` without `PRAGMA foreign_keys`.

There are no migrations. `CREATE TABLE IF NOT EXISTS` does not change existing tables, so if you change a schema, either alter `site.db` by hand or delete it and let the app recreate it.

To fill it with made-up test data (30 accounts, about two thirds with registered interest, 8 contact messages and 14 days of analytics events), run `.venv/bin/python -W ignore seed_db.py`. It copies `site.db` to `site.db.bak` first. Seeded emails end `@seed.example.com` and every seeded password is `Passw0rd!`. `seed_db.py --reset` removes the seeded accounts, interest and messages but not the analytics events; restore `site.db.bak` to undo those too.

To look at the data:

```bash
sqlite3 site.db "SELECT id, name, email, created_at FROM messages ORDER BY id DESC LIMIT 10;"
```

### Accounts and security

- Passwords are hashed with `pbkdf2:sha256`. The Werkzeug default, scrypt, is missing from the Python that ships with macOS.
- Sign-in stores `user_id` in Flask's signed session cookie. `load_user()` loads the user into `g.user` on each request, and templates see it as `current_user`.
- Every POST form needs a CSRF token from Flask-WTF. Add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to any new form. The chat blueprint is exempt because it only accepts JSON.
- The `next` parameter on `/login` and `/register` is only followed if `is_safe_redirect()` confirms it is a path on this site.
- On the account page, changing the email or the password needs the current password (`current_password_error()`), in case someone else is using a computer that was left signed in. Changing the name doesn't. A password change starts a fresh session, as signing in does.
- The form checks (`name_error()`, `email_error()`, `password_error()`, `current_password_error()`, `message_error()` in `main.py`) are shared by the contact, sign-up and account forms. `auth.js` repeats them in the browser with the same messages, so change both together.
- The interest checks (`role_error()`, `school_error()`, `routes_error()`, `year_group_error()`, `consent_error()`) are only in `main.py`, shared by `/interest` and `/api/interest`. The page has no browser-side checks.
- Form field limits: name 100 characters, email 254, message 2000, password 8 to 128. Requests over 16 KB are rejected, except chat requests, which allow 100 KB.
- Rate limits use Flask-Limiter (set up in `extensions.py`). They are kept in memory, so they reset when the app restarts and are not shared between processes.

## AI chat (`chat_api.py`)

The chat widget sends the conversation to the Flask server, which forwards it to OpenRouter with the API key and a fixed system prompt. The key never reaches the browser.

Request body for both endpoints:

```json
{ "messages": [ { "role": "user", "content": "What is a T Level?" } ] }
```

Validation rules: 1 to 20 messages, each with role `user` or `assistant` (visitors cannot send `system` messages), up to 4000 characters each, and the last message must be from the user.

- `/api/chat` returns `{"reply": "..."}` or `{"error": "..."}` with a status code.
- `/api/chat/stream` returns `text/event-stream`. Each event is `data: {"delta": "..."}`, then `data: {"done": true}` at the end, or `data: {"error": "..."}` if something fails part-way. `data: {"replace": "..."}` means "discard the text so far and show this instead" (see Guardrails). Errors found before streaming starts come back as normal JSON errors.

Settings are constants at the top of the file: `CHAT_SYSTEM_PROMPT`, `CHAT_RATE_LIMIT` (10 requests per minute per IP, shared by both endpoints; going over returns a JSON 429 with `Retry-After`), `CHAT_TIMEOUT`, `CHAT_MAX_TOKENS` and `CHAT_REASONING`. The messages visitors see are constants too. The model's reasoning is excluded from responses.

The assistant also answers from `chat_knowledge.md`, a hand-kept copy of the site's page text. It doesn't update itself, so edit it when page wording, password rules or the lockout settings change, then restart the server.

To change what the assistant says or refuses to say, edit `CHAT_SYSTEM_PROMPT` and the short `CHAT_REMINDER` that follows the reference text. Many visitors are under 18, so keep the safeguarding rules in it.

### Guardrails

The prompt limits replies to plain English sentences in the assistant's own voice: no code, JSON, tables, poems, songs, stories, characters or other languages, even on T Level topics. Prompts can be talked round, so the server also runs `looks_like_code()` on every reply. If a reply looks like code, `/api/chat` returns `CODE_REFUSAL` instead, and `/api/chat/stream` stops and sends it as a `replace` event. Assistant messages in the history the browser sends get the same check, because a visitor can make them up.

After changing the prompt, `chat_knowledge.md` or `looks_like_code()`, run the guardrail check. It sends each case to the real model three times (set `RUNS` to change that) and prints PASS or FAIL for each, covering cases that must be refused and cases that must still be answered:

```bash
.venv/bin/python -W ignore check_chat_guardrails.py 2>/dev/null | grep -E "^=== |RESULT"
```

Test the API from the command line while the app is running:

```bash
curl -s http://127.0.0.1:5000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is a T Level?"}]}'
```

The rate limiter uses `request.remote_addr`. If the site is put behind a reverse proxy, add Werkzeug's `ProxyFix` so it sees the real visitor IP.

## Slack bot (`bot/`)

When a contact form message is saved, `main.py` also posts it to `SLACK_CHANNEL_ID`. The Slack message has four buttons: Mark Handled, Priority, Reply Needed and View JSON. The first three reply in the message's thread; View JSON opens a modal.

When someone registers, updates or removes their interest (on `/interest`, the account page or `/api/interest`), `save_interest()` and `remove_interest()` post a message with `send_interest_to_slack()`: the name and email, plus who they are, school or college, year group and routes, unless it was removed. These messages have the Mark Handled and View JSON buttons.

- Posting needs `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID`.
- The buttons need `SLACK_APP_TOKEN` as well. `python main.py` starts the bot in a background thread using Socket Mode, which connects out to Slack and opens no port.
- If Slack is down, misconfigured or `slack_bolt` is not installed, the message or interest is still saved to the database and the form still works.
- Text from the form is escaped so it can't trigger Slack formatting such as `<!channel>`.

To check the setup without using the form:

```bash
python send_slack_test.py
```

To run only the bot, without the website:

```bash
python -m bot.bot
```

Run both commands from the project folder so the `bot` package can be imported.

## Frontend

The frontend is plain HTML, CSS and JavaScript, with no build step or package manager. Flask serves `frontend/Template/Sources/` at `/Sources/`.

### Shared files on every page

`base.html` loads these, in this order, so pages don't list them.

| File | What it does |
|---|---|
| `css/tokens.css` | Design tokens (colours, fonts) for the light, dark and high-contrast themes. Loaded before every other stylesheet. |
| `css/base.css` | The site-wide keyboard focus ring and the `.visually-hidden` class (hidden on screen, still read by screen readers). |
| `js/site.js` | `TLC.link()` and `TLC.isCurrent()`, the URL helpers the nav bar, footer and chat widget share. |
| `css/topNavBar.css`, `js/topNavBar.js` | Builds the top navigation, search box and sign-in or account link. |
| `css/accessibility.css`, `js/accessibility.js` | Accessibility popup: text size, theme and reading aids, saved in `localStorage` (`tlc-theme` and `tlc-a11y`). |
| `css/footer.css`, `js/footer.js` | Builds the footer and keeps it at the bottom of short pages. |
| `css/chatWidget.css`, `js/chatWidget.js` | The "T buddy" chat button and panel. Uses `/api/chat/stream`, with `/api/chat` as a fallback. Site paths in replies, such as `/t-levels#media`, become links if the page is in `LINKABLE_PAGES`. Any button with `data-open-chat` opens it, and elements with `data-needs-chat` (hidden in the HTML) are shown once it loads. |
| `css/motion.css` | Shared transitions. Movement is turned off when the visitor asks for reduced motion in their system or in the accessibility popup. |

`accessibility.js` loads in `<head>` without `defer`, so saved settings apply before the page is drawn and there is no flash of the wrong theme or text size. Every other script loads with `defer`, so it runs once the page's HTML is ready and doesn't need to wait for `DOMContentLoaded`.

The navigation, footer and chat widget are injected by JavaScript, so you don't add their markup to new pages.

### Page-specific files

| Page | CSS | JS |
|---|---|---|
| Home | `components.css`, `home.css` | |
| T Level | `components.css`, `tlevel.css` | `tlevelTabs.js` (vertical tabs, selected by URL hash such as `#media`) |
| Advice | `components.css`, `advice.css` | `advice.js` (highlights the side nav, runs the Your path year picker) |
| FAQs | `components.css` | |
| Quiz | `components.css`, `quiz.css` | `quiz.js` |
| Contact | `contact.css` | `contact.js` (moves focus to the result after sending) |
| Login | `auth.css` | `auth.js` (switches between sign-in and sign-up, client-side checks) |
| Account | `auth.css`, `account.css` | `auth.js` (opens and closes the change forms in place, client-side checks) |
| Analytics | `analytics.css` | `analytics.js` (sizes the chart bars from `data-length`, since the CSP blocks `style` attributes. The donut charts are server-drawn SVG and need no script) |
| Privacy | `privacy.css` | |
| 404, 500 | `errorPage.css` | `errorPage.js` (404 only: the "Go back" button) |

`components.css` holds the pieces several content pages share: page column, breadcrumb, title, callout, accordion, buttons, route cards and the "Still unsure?" card. `auth.css` holds the form, field, error and success styles shared by the login and account pages; the account page's own layout is in `account.css`.

The Advice page has four sections: `#why-choose`, `#your-path` (a timeline from Year 10 to Year 13 that includes how to apply for a placement), `#where-it-leads` and `#common-questions`. The "Years 12 and 13" stage of the timeline keeps `id="how-to-apply"` so older links still land there. The header search in `topNavBar.js` links to these ids (`SEARCH_INDEX` entries such as `advice#why-choose`), so update it when you rename or remove a section. The home page's "Where are you now?" cards link into the timeline (`advice#step-apply`, `advice#how-to-apply`, `advice#step-finish`), and `advice.js` sets the year picker to match the step a link lands on.

### Styling conventions

- Take colours from `tokens.css`. Check that new styles work in the light, dark and high-contrast themes.
- Focus rings come from `base.css`. Only add a `:focus-visible` rule when a component needs a different ring, for example on a coloured fill.
- Size text in `rem` so the Large and Extra large text settings scale it.
- The font is Amazon Ember, through `var(--font-sans)`, self-hosted from `Sources/fonts/` with `@font-face` rules in `tokens.css` (regular, semibold, bold and their italics). Amazon owns it, so no licence fee or attribution is needed. `accessibility.css` loads Atkinson Hyperlegible for the readable-font option, self-hosted from `Sources/fonts/` so no visitor data goes to Google. The Content Security Policy in `main.py` only allows fonts and styles from the site itself.
- Designs come from Figma. CSS comments name the Figma frame or node a file follows.

## Testing

`smoke_test.py` runs the backend through Flask's test client with normal, boundary and erroneous data: pages, the contact form, sign-up, sign-in and the lockout, register your interest (page and API), account changes, deleting an account, downloads and the chat API's validation. It uses a temporary database and stand-ins for Slack and OpenRouter, so it sends nothing and needs no keys. It prints PASS or FAIL for each case and exits with status 1 if any fail:

```bash
.venv/bin/python -W ignore smoke_test.py
```

GitHub Actions also runs it on every push to `main` and every pull request, on Python 3.9 and 3.13 (`.github/workflows/smoke-tests.yml`). You can start a run by hand from the repo's Actions tab. The workflow doesn't run `check_chat_guardrails.py`, because that calls the real chat model and needs an OpenRouter key, so it uses no secrets.

Run it before committing a backend change, and add cases when you add a form, a rule or a route. It doesn't check layout, so also check by hand:

- Each page you changed at desktop width and at a phone width of about 390px.
- Light, dark and high-contrast themes, and the Large and Extra large text sizes, from the accessibility popup.
- Keyboard use: Tab through the page and make sure focus is visible and nothing is unreachable.
- Forms: sign up, sign in, change your name, email and password on the account page, sign out, and send a contact message. Check that errors show for empty or invalid fields.
- The chat widget, if you have an OpenRouter key. If you changed the chat prompt or `chat_knowledge.md`, run `check_chat_guardrails.py`.

## Going live

Before the site is reachable by anyone else:

- Make sure `SECRET_KEY` stays fixed: either let the app save one to `.env` on first start, or set a long random one yourself, for example from `python -c "import secrets; print(secrets.token_hex(32))"`. Never reuse a value from the repo.
- Leave `FLASK_DEBUG` unset.
- Serve over HTTPS and set `HTTPS=1`.
- Run under a production WSGI server instead of `python main.py`. Note that the Slack bot is only started from `main.py`'s `__main__` block, so a WSGI server needs it started separately (for example with `python -m bot.bot`).
- Rate limits are stored in memory per process. With several worker processes, each one has its own counts. Use a shared store such as Redis for Flask-Limiter if that matters.
- Add `ProxyFix` if a reverse proxy sits in front of the app.
- Back up `site.db`.
