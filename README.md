# T Level Connect

T Level Connect is a website about T Levels and T Level industry placements at Amazon, built for the Amazon Emerging Talent Programs team. Its audience is students, parents and carers, and teachers or careers advisers.

The site is a small Flask app. It serves HTML pages, stores user accounts and contact form messages in SQLite, runs an AI chat assistant through OpenRouter, and can post contact form messages to a Slack channel.

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

The database file `site.db` is created next to `main.py` the first time the app starts. To reset the data, stop the app and delete `site.db`.

Open the pages through Flask, not by double-clicking the HTML files. The templates contain Jinja tags such as `{{ csrf_token() }}`, and the forms, sign-in state and chat widget all need the server.

## Configuration

Settings are read from environment variables. `main.py` and `bot/bot.py` also load a `.env` file from the project folder. Real environment variables take priority over `.env`. Never commit `.env`; it is already in `.gitignore`.

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes, for any shared or live site | Signs the session cookie. If it is unset, a random key is generated on each start and everyone is signed out when the app restarts. |
| `OPENROUTER_API_KEY` | For the chat widget | OpenRouter API key. Without it, the chat API returns 503 and the rest of the site still works. |
| `OPENROUTER_MODEL` | No | Model ID. Defaults to `nvidia/nemotron-3.5-super-vl:free`. |
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
├── main.py                 Flask app: page routes, accounts, contact form, error pages, database setup
├── chat_api.py             Blueprint for /api/chat and /api/chat/stream (OpenRouter proxy)
├── bot/
│   ├── bot.py              Slack bot: posts contact messages, handles the message buttons
│   └── slack_bot_runner.py Runs only the Slack bot, without the website
├── send_slack_test.py      Sends one fake contact message to Slack to check the setup
├── requirements.txt
├── .env.example            Template for .env
├── site.db                 SQLite database (created on first run, not committed)
└── frontend/Template/      Jinja templates (Flask's template_folder)
    ├── home.html, TLevel.html, advice.html, faqs.html, contact.html, privacy.html
    ├── login.html          Sign-in and sign-up forms on one page
    ├── signin.html         Redirects to login.html (the nav bar links here)
    ├── account.html        Signed-in users only
    ├── analytics.html      Site analytics, for emails listed in ANALYTICS_EMAILS
    ├── quiz.html           Placeholder, no content yet
    ├── 404.html, 500.html
    └── Sources/            Static files (Flask's static_folder, served at /Sources/...)
        ├── css/
        ├── js/
        └── assests/        Images and icons (the folder name is spelled this way in every link)
```

`.agents/` holds Figma specs, plans and screenshots from earlier work. It is ignored by git, so it only exists on machines where it was created.

## Backend

### Routes

Each page answers on its short URL and on its `.html` file name, because the nav bar and footer link to the file names (for example `/faqs` and `/faqs.html`). `url_for()` builds the short URL.

| URL | Methods | Template or response |
|---|---|---|
| `/`, `/home.html` | GET | `home.html` |
| `/t-levels`, `/TLevel.html` | GET | `TLevel.html` |
| `/advice`, `/advice.html` | GET | `advice.html` |
| `/faqs`, `/faqs.html` | GET | `faqs.html` |
| `/privacy`, `/privacy.html` | GET | `privacy.html` |
| `/quiz`, `/quiz.html` | GET | `quiz.html` |
| `/contact`, `/contact.html` | GET, POST | `contact.html`. POST saves the message and posts it to Slack. Limited to 5 POSTs per minute per IP. |
| `/login`, `/login.html`, `/signin.html` | GET, POST | `login.html`, sign-in tab. Limited to 10 POSTs per minute. |
| `/register` | GET, POST | `login.html`, sign-up tab. Limited to 10 POSTs per minute. |
| `/logout` | POST | Clears the session and redirects home. |
| `/account`, `/account.html` | GET | `account.html`. Requires sign-in. |
| `/analytics`, `/analytics.html` | GET | `analytics.html`. Requires sign-in with an email in `ANALYTICS_EMAILS`; anyone else signed in gets a 404. |
| `/accessibility`, `/accessibility.html` | GET | Redirects to `/#accessibility`. The settings are now a popup on every page. |
| `/api/track` | POST | Records an analytics event, `{"kind": "search" \| "view" \| "quiz", "value": "..."}`. JSON only, 30 per minute per IP. Views and quiz results must be one of the five route names; searches are lower-cased and up to 100 characters. |
| `/api/session` | GET | `{"signed_in": bool, "name": ...}`, used by `topNavBar.js`. |
| `/api/chat` | POST | Chat reply as JSON. |
| `/api/chat/stream` | POST | Chat reply as Server-Sent Events. |

### Adding a page

1. Create `frontend/Template/<name>.html`. Copy the `<head>` from an existing page so it loads the shared CSS and JS (see "Frontend").
2. Add a route in `main.py` next to the other public pages, with the `.html` route first and the short URL second:

   ```python
   @app.route("/example.html")
   @app.route("/example")
   def example():
       return render_template("example.html")
   ```

3. To show it in the navigation, add it to the link lists in `Sources/js/topNavBar.js` and, if needed, `Sources/js/footer.js`. `topNavBar.js` also has a list of pages used by the search box.
4. To make a page sign-in only, add `@login_required` under the route decorators.

The 404 handler builds its list of pages from the routes, so a new page is included in "Did you mean...?" suggestions and case-correcting redirects (`/FAQS` goes to `/faqs`) without further work.

### Database

`init_db()` in `main.py` creates these tables if they don't exist:

- `users`: `id`, `name`, `email` (unique, stored in lower case), `password_hash`, `created_at`
- `messages`: `id`, `name`, `email`, `message`, `created_at`
- `analytics_events`: `id`, `kind` (`search`, `view` or `quiz`), `value`, `created_at`. Sent by `topNavBar.js` (searches), `tlevelTabs.js` (each route tab, once per visit) and `quiz.js` (the top match). No user id or IP is stored.

There are no migrations. `CREATE TABLE IF NOT EXISTS` does not change existing tables, so if you change a schema, either alter `site.db` by hand or delete it and let the app recreate it.

To look at the data:

```bash
sqlite3 site.db "SELECT id, name, email, created_at FROM messages ORDER BY id DESC LIMIT 10;"
```

### Accounts and security

- Passwords are hashed with `pbkdf2:sha256`. The Werkzeug default, scrypt, is missing from the Python that ships with macOS.
- Sign-in stores `user_id` in Flask's signed session cookie. `load_user()` loads the user into `g.user` on each request, and templates see it as `current_user`.
- Every POST form needs a CSRF token from Flask-WTF. Add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to any new form. The chat blueprint is exempt because it only accepts JSON.
- The `next` parameter on `/login` is only followed if `is_safe_redirect()` confirms it is a path on this site.
- Form field limits: name 100 characters, email 254, message 2000, password 8 to 128. Requests over 16 KB are rejected, except chat requests, which allow 100 KB.
- Rate limits are kept in memory, so they reset when the app restarts and are not shared between processes.

## AI chat (`chat_api.py`)

The chat widget sends the conversation to the Flask server, which forwards it to OpenRouter with the API key and a fixed system prompt. The key never reaches the browser.

Request body for both endpoints:

```json
{ "messages": [ { "role": "user", "content": "What is a T Level?" } ] }
```

Validation rules: 1 to 20 messages, each with role `user` or `assistant` (visitors cannot send `system` messages), up to 4000 characters each, and the last message must be from the user.

- `/api/chat` returns `{"reply": "..."}` or `{"error": "..."}` with a status code.
- `/api/chat/stream` returns `text/event-stream`. Each event is `data: {"delta": "..."}`, then `data: {"done": true}` at the end, or `data: {"error": "..."}` if something fails part-way. Errors found before streaming starts come back as normal JSON errors.

Settings are constants at the top of the file: `CHAT_SYSTEM_PROMPT`, `CHAT_RATE_LIMIT` (10 requests per 60 seconds per IP, shared by both endpoints), `CHAT_TIMEOUT`, `CHAT_MAX_TOKENS` and `CHAT_REASONING`. The model's reasoning is excluded from responses.

To change what the assistant says or refuses to say, edit `CHAT_SYSTEM_PROMPT`. Many visitors are under 18, so keep the safeguarding rules in it.

Test the API from the command line while the app is running:

```bash
curl -s http://127.0.0.1:5000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is a T Level?"}]}'
```

The rate limiter uses `request.remote_addr`. If the site is put behind a reverse proxy, add Werkzeug's `ProxyFix` so it sees the real visitor IP.

## Slack bot (`bot/`)

When a contact form message is saved, `main.py` also posts it to `SLACK_CHANNEL_ID`. The Slack message has four buttons: Mark Handled, Priority, Reply Needed and View JSON. The first three reply in the message's thread; View JSON opens a modal.

- Posting needs `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID`.
- The buttons need `SLACK_APP_TOKEN` as well. `python main.py` starts the bot in a background thread using Socket Mode, which connects out to Slack and opens no port.
- If Slack is down, misconfigured or `slack_bolt` is not installed, the message is still saved to the database and the form still works.
- Text from the form is escaped so it can't trigger Slack formatting such as `<!channel>`.

To check the setup without using the form:

```bash
python send_slack_test.py
```

To run only the bot, without the website:

```bash
python -m bot.slack_bot_runner
```

Run both commands from the project folder so the `bot` package can be imported.

## Frontend

The frontend is plain HTML, CSS and JavaScript, with no build step or package manager. Flask serves `frontend/Template/Sources/` at `/Sources/`, so pages link to files with relative paths such as `href="Sources/css/home.css"`.

### Shared files on every page

| File | What it does |
|---|---|
| `css/tokens.css` | Design tokens (colours, fonts) from the Figma token file. Load it before every other stylesheet. |
| `css/topNavBar.css`, `js/topNavBar.js` | Builds the top navigation, search box, theme toggle and sign-in or account link. Also defines the light, dark and high-contrast theme variables (`--page-bg`, `--page-text`, `--accent`). |
| `css/accessibility.css`, `js/accessibility.js` | Accessibility popup: text size, theme and reading aids, saved in `localStorage` (`tlc-theme` and `tlc-a11y`). |
| `css/footer.css`, `js/footer.js` | Builds the footer and keeps it at the bottom of short pages. |
| `css/chatWidget.css`, `js/chatWidget.js` | The "T buddy" chat button and panel. Uses `/api/chat/stream`, with `/api/chat` as a fallback. |
| `css/motion.css` | Shared transitions. Movement is turned off when the visitor asks for reduced motion in their system or in the accessibility popup. |

Load `accessibility.js` in `<head>` without `defer`, so saved settings apply before the page is drawn and there is no flash of the wrong theme or text size. Load the other scripts with `defer`. `faqs.html` shows the usual order.

The navigation, footer and chat widget are injected by JavaScript, so you don't add their markup to new pages. Each script works out the site root from its own URL (`document.currentScript`), so links still work whatever URL the page was loaded from.

### Page-specific files

| Page | CSS | JS |
|---|---|---|
| Home | `home.css`, `tlevel.css` (route cards) | |
| T Level | `tlevel.css` | `tlevelTabs.js` (vertical tabs, selected by URL hash such as `#media`) |
| Advice | `tlevel.css`, `advice.css` | `advice.js` (highlights the side nav, opens the chat) |
| FAQs | `tlevel.css`, `advice.css` | `advice.js` |
| Login | `auth.css` | `auth.js` (sign-in and sign-up tabs, client-side checks) |
| Contact, account | `auth.css` | |
| Privacy | `privacy.css` | |

`tlevel.css` holds shared pieces (breadcrumb, title, callout, accordion, buttons, route cards) used by several pages.

### Styling conventions

- Take colours from `tokens.css` and the theme variables. Check that new styles work in the light, dark and high-contrast themes.
- Size text in `rem` so the Large and Extra large text settings scale it.
- The font is Amazon Ember, through `var(--font-sans)`. `accessibility.css` loads Atkinson Hyperlegible for the readable-font option.
- Designs come from Figma. CSS comments name the Figma frame or node a file follows.

## Testing

There is no automated test suite. Before committing, check by hand:

- Each page you changed at desktop width and at a phone width of about 390px.
- Light, dark and high-contrast themes, and the Large and Extra large text sizes, from the accessibility popup.
- Keyboard use: Tab through the page and make sure focus is visible and nothing is unreachable.
- Forms: sign up, sign in, sign out, and send a contact message. Check that errors show for empty or invalid fields.
- The chat widget, if you have an OpenRouter key.

## Going live

Before the site is reachable by anyone else:

- Set a long random `SECRET_KEY`, for example from `python -c "import secrets; print(secrets.token_hex(32))"`.
- Leave `FLASK_DEBUG` unset.
- Serve over HTTPS and set `HTTPS=1`.
- Run under a production WSGI server instead of `python main.py`. Note that the Slack bot is only started from `main.py`'s `__main__` block, so a WSGI server needs it started separately (for example with `python -m bot.slack_bot_runner`).
- Rate limits are stored in memory per process. With several worker processes, each one has its own counts. Use a shared store such as Redis for Flask-Limiter if that matters.
- Add `ProxyFix` if a reverse proxy sits in front of the app.
- Back up `site.db`.
