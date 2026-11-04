"""Flask backend for the T Level placements at Amazon site.

Serves the pages, stores accounts and contact messages in SQLite, and handles signing in
and out. The chat widget's API lives in chat_api.py.
"""

import difflib
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import urlparse

try:
    import fcntl  # Used to lock .env while writing SECRET_KEY. Not on Windows, where the lock is skipped.
except ImportError:
    fcntl = None

from dotenv import dotenv_values, load_dotenv
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_from_directory,
                   session, url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from chat_api import CHAT_RATE_LIMITED, chat_bp
from extensions import limiter

log = logging.getLogger(__name__)

# bot/bot.py posts each contact message and expression of interest to Slack.
# Without slack_bolt the site still works.
try:
    from bot.bot import (is_configured as is_slack_configured, send_interest_to_slack, send_to_slack,
                         start_in_background as start_slack_bot)
except ImportError:
    log.warning("slack_bolt is not installed, so contact messages and interest won't be sent to Slack. "
                "Run: pip install -r requirements.txt")
    def is_slack_configured():
        return False
    def send_to_slack(payload):
        pass
    def send_interest_to_slack(payload):
        pass
    def start_slack_bot():
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "site.db")

# Members-only spec PDFs. Kept out of frontend/Template/Sources, which Flask serves to anyone;
# these can only be fetched through /download/<name>, which requires sign-in.
DOWNLOADS_DIR = os.path.join(BASE_DIR, "resources", "specs")

# Real environment variables win over .env. Must run before the os.environ.get() calls below.
ENV_FILE = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_FILE)

DEBUG = os.environ.get("FLASK_DEBUG") == "1"
# Turns on the secure cookie and HSTS. Off by default because local testing uses http://,
# where the browser would drop a secure cookie and nobody could stay signed in.
HTTPS = os.environ.get("HTTPS") == "1"

MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254
MAX_MESSAGE_LENGTH = 2000
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 8

# A capital, a number and a special character (anything but a letter, digit or space).
# auth.js checks the same rules, with the same messages, in the browser. Keep the two in step.
PASSWORD_CAPITAL = re.compile(r"[A-Z]")
PASSWORD_NUMBER = re.compile(r"[0-9]")
PASSWORD_SPECIAL = re.compile(r"[^A-Za-z0-9\s]")

# After MAX_LOGIN_ATTEMPTS wrong passwords in a row, sign-in for that email is locked for
# LOCKOUT_MINUTES. The lock is timed because there's no password reset yet, and a permanent
# lock would let anyone lock a real user out for good just by knowing their email.
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_MINUTES = 15

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Analytics: the five T Level routes, in the order the site shows them. Programme views and
# quiz results are only recorded for these names, so the counts can't fill up with junk.
ROUTES = [
    ("digital", "Digital"),
    ("business", "Business"),
    ("media", "Media"),
    ("finance", "Finance"),
    ("engineering", "Engineering"),
]
ROUTE_KEYS = {key for key, _ in ROUTES}
ROUTE_LABELS = dict(ROUTES)
MAX_SEARCH_LENGTH = 100

# Register your interest: the answers people can give, in the order the page shows them.
INTEREST_ROLES = [
    ("student", "A student"),
    ("parent_carer", "A parent or carer"),
    ("teacher_adviser", "A teacher or careers adviser"),
    ("other", "Something else"),
]
ROLE_LABELS = dict(INTEREST_ROLES)
YEAR_GROUPS = [
    ("year_10", "Year 10"),
    ("year_11", "Year 11"),
    ("year_12", "Year 12"),
    ("year_13", "Year 13"),
    ("not_at_school", "Not at school or college"),
]
YEAR_LABELS = dict(YEAR_GROUPS)
MAX_SCHOOL_LENGTH = 100

# Who may open the analytics page: a comma-separated list of account emails in ANALYTICS_EMAILS.
# If it's empty, nobody can (the page shows "not found"), so the stats are never public by accident.
ANALYTICS_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("ANALYTICS_EMAILS", "").split(",")
    if email.strip()
}

# Static files are served at /Sources/... to match the href="Sources/..." links in the pages.
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend", "Template"),
    static_folder=os.path.join(BASE_DIR, "frontend", "Template", "Sources"),
    static_url_path="/Sources",
)

# SECRET_KEY signs the session cookie, so it must stay the same between restarts or everyone
# gets signed out (on EC2 that's every restart or deploy). If it isn't set, one is made once and
# saved to .env, which is git-ignored, so the key never ends up in the repo.
def load_or_create_secret_key():
    secret_key = os.environ.get("SECRET_KEY", "").strip()
    if secret_key:
        return secret_key
    try:
        fd = os.open(ENV_FILE, os.O_RDWR | os.O_CREAT, 0o600)  # Readable by this user only.
        with os.fdopen(fd, "r+", encoding="utf-8") as env_file:
            if fcntl:
                # If several server processes start at once, only one makes a key; the rest reuse it.
                fcntl.flock(env_file, fcntl.LOCK_EX)
            secret_key = (dotenv_values(ENV_FILE).get("SECRET_KEY") or "").strip()
            if not secret_key:
                secret_key = secrets.token_hex(32)
                existing = env_file.read()
                if existing and not existing.endswith("\n"):
                    env_file.write("\n")
                env_file.write(f"SECRET_KEY={secret_key}\n")
                log.warning("SECRET_KEY was not set, so a new one was made and saved to .env.")
    except OSError as e:  # e.g. the folder is read-only.
        log.warning("SECRET_KEY is not set and couldn't be saved to .env (%s). Using a random key, so "
                    "users will be signed out whenever the app restarts. Set SECRET_KEY in .env.", e)
        secret_key = secrets.token_hex(32)
    os.environ["SECRET_KEY"] = secret_key  # So Flask's reloader process uses the same key.
    return secret_key


app.config["SECRET_KEY"] = load_or_create_secret_key()
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = HTTPS

# "Keep me signed in" ticked: the session cookie lasts REMEMBER_DAYS. Not ticked: it is a
# browser-session cookie, but browsers that restore tabs on reopening also restore those,
# so load_user signs the person out after IDLE_MINUTES without a request as well.
REMEMBER_DAYS = 30
IDLE_MINUTES = 30
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=REMEMBER_DAYS)

# The forms are tiny. chat_api.py raises this limit for chat requests.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

csrf = CSRFProtect(app)
limiter.init_app(app)


# ---------- Security headers ----------

# Only our own site may supply scripts, styles, fonts and data. The privacy page promises no
# third parties see a page visit, so keep fonts self-hosted rather than adding Google Fonts here.
# Inline <script>, <style> and onclick="" are blocked, which is why all page behaviour
# lives in Sources/js and all styles in Sources/css.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "font-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Frame-Options"] = "DENY"  # frame-ancestors for older browsers.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if HTTPS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


# ---------- Database ----------

_db_initialised_for = None  # The DATABASE path init_db() last ran for, so it runs once per file.


def get_db():
    """Returns this request's database connection, opening it (and creating the tables) on first use."""
    global _db_initialised_for
    if _db_initialised_for != DATABASE:
        init_db()
        _db_initialised_for = DATABASE
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Creates the tables if they don't exist yet."""
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Failed sign-ins per lower-cased email typed in, whether or not it has an account.
        -- failed_count resets on success or lock; locked_until is a Unix time (0 = not locked).
        CREATE TABLE IF NOT EXISTS login_attempts (
            email TEXT PRIMARY KEY,
            failed_count INTEGER NOT NULL DEFAULT 0,
            locked_until REAL NOT NULL DEFAULT 0
        );

        -- Things visitors do in the browser, shown on the analytics page.
        -- No user id or IP is stored, only what happened.
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,                        -- "search", "view" (a route tab opened) or "quiz" (the quiz's top match).
            value TEXT NOT NULL,                       -- The search text, or the route name, e.g. "digital".
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Register your interest: one row per user, plus one interest_routes row per route chosen.
        -- SQLite only enforces REFERENCES with PRAGMA foreign_keys on, so remove_interest()
        -- deletes from both tables itself.
        CREATE TABLE IF NOT EXISTS interests (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            role TEXT NOT NULL,                        -- A key from INTEREST_ROLES, e.g. "student".
            school TEXT NOT NULL DEFAULT '',
            year_group TEXT NOT NULL,                  -- A key from YEAR_GROUPS, e.g. "year_12".
            contact_consent INTEGER NOT NULL,          -- Always 1: nothing is saved without consent.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS interest_routes (
            user_id INTEGER NOT NULL REFERENCES users(id),
            route TEXT NOT NULL,                       -- A key from ROUTES, e.g. "digital".
            PRIMARY KEY (user_id, route)
        );
        """
    )
    db.commit()
    db.close()


# ---------- Helpers ----------

@app.before_request
def load_user():
    """Puts the signed-in user (or None) in g.user. A session pointing at a user that no longer
    exists (e.g. after a database reset) is cleared, so the person can sign in again."""
    g.user = None
    if "user_id" in session and not session.get("remember"):
        now = time.time()
        if now - session.get("last_seen", 0) > IDLE_MINUTES * 60:
            session.clear()
        else:
            session["last_seen"] = now
    if "user_id" in session:
        g.user = get_db().execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
        if g.user is None:
            session.clear()


@app.context_processor
def inject_user():
    # g.get, because load_user doesn't run before some error pages.
    return {"current_user": g.get("user")}


def start_session(user_id, remember):
    """Signs `user_id` in with a fresh session, so nothing from before sign-in carries over."""
    session.clear()
    session["user_id"] = user_id
    session["remember"] = remember
    session["last_seen"] = time.time()
    session.permanent = remember


def login_required(view):
    """Decorator that sends visitors who aren't signed in to the sign-in page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def is_safe_redirect(target):
    """True only if `target` is a path on this site. Backslashes count as slashes, as they do
    in browsers, so tricks like "/\\evil.com" are caught."""
    if not target or not target.startswith("/"):
        return False
    parts = urlparse(target.replace("\\", "/"))
    return not parts.scheme and not parts.netloc


def redirect_after_sign_in():
    """Sends a user who has just signed in or signed up to the ?next= page, or their account."""
    next_page = request.args.get("next", "")
    return redirect(next_page if is_safe_redirect(next_page) else url_for("account"))


def is_valid_email(email):
    return len(email) <= MAX_EMAIL_LENGTH and EMAIL_PATTERN.fullmatch(email) is not None


# ---------- Form checks ----------
# Each returns the error message to show, or None if the value is fine. The messages match
# the ones auth.js shows in the browser.

def name_error(name):
    if not name:
        return "Enter your name"
    if len(name) > MAX_NAME_LENGTH:
        return f"Name must be {MAX_NAME_LENGTH} characters or fewer"
    return None


def email_error(email):
    if not email:
        return "Enter your email address"
    if not is_valid_email(email):
        return "Enter an email address in the correct format, like name@example.com"
    return None


def password_error(password, confirm):
    if not password:
        return "Enter your password"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer"
    if not PASSWORD_CAPITAL.search(password):
        return "Password must include a capital letter"
    if not PASSWORD_NUMBER.search(password):
        return "Password must include a number"
    if not PASSWORD_SPECIAL.search(password):
        return "Password must include a special character, such as ! ? # or @"
    if not confirm:
        return "Type your password again"
    if password != confirm:
        return "Passwords do not match"
    return None


def current_password_error(user_id, password):
    """Checks the password typed in to confirm a change to an account."""
    if not password:
        return "Enter your current password"
    row = get_db().execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if not check_password_hash(row["password_hash"], password):
        return "Your current password is incorrect"
    return None


def message_error(message):
    if not message:
        return "Enter your message"
    if len(message) > MAX_MESSAGE_LENGTH:
        return f"Message must be {MAX_MESSAGE_LENGTH} characters or fewer"
    return None


# ---------- Public pages ----------

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/accessibility")
def accessibility():
    # Old links. The settings are now a popup on every page.
    return redirect(url_for("home") + "#accessibility")


@app.route("/faqs")
def faqs():
    return render_template("faqs.html")


@app.route("/faq")
def faq_alias():
    # People often type the singular. The page itself stays at /faqs.
    query = request.query_string.decode()
    return redirect(url_for("faqs") + ("?" + query if query else ""), code=301)


@app.route("/t-levels")
def t_levels():
    return render_template("TLevel.html")


@app.route("/advice")
def advice():
    return render_template("advice.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/quiz")
def quiz():
    return render_template("quiz.html")


@app.route("/api/track", methods=["POST"])  # topNavBar.js, tlevelTabs.js and quiz.js send events here.
@limiter.limit("30 per minute")  # Stops anyone flooding the analytics with fake events.
def api_track():
    """Records one visitor event for the analytics page.
    Body: {"kind": "search" | "view" | "quiz", "value": "..."}. Returns 204."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Expected a JSON object."}, 400
    kind = data.get("kind")
    value = data.get("value")
    if not isinstance(value, str):
        return {"error": "value must be text."}, 400

    if kind == "search":
        value = " ".join(value.lower().split())     # "  Digital   JOBS " and "digital jobs" count as one search.
        if not value or len(value) > MAX_SEARCH_LENGTH:
            return {"error": f"Searches must be 1 to {MAX_SEARCH_LENGTH} characters."}, 400
    elif kind in ("view", "quiz"):
        if value not in ROUTE_KEYS:                 # Only the five real routes.
            return {"error": "Unknown route."}, 400
    else:
        return {"error": "Unknown kind."}, 400

    db = get_db()
    db.execute("INSERT INTO analytics_events (kind, value) VALUES (?, ?)", (kind, value))
    db.commit()
    return "", 204


# The pages used to be linked by their file names, e.g. /faqs.html. Those addresses still work
# for old links and bookmarks, by redirecting to the short URL.
OLD_PAGE_URLS = {
    "home": "home", "accessibility": "accessibility", "faqs": "faqs", "faq": "faqs", "tlevel": "t_levels",
    "advice": "advice", "privacy": "privacy", "quiz": "quiz", "contact": "contact",
    "account": "account", "analytics": "analytics", "login": "login", "signin": "login",
    "interest": "interest",
}


@app.route("/<page>.html")
def old_page_url(page):
    endpoint = OLD_PAGE_URLS.get(page.lower())
    if endpoint is None:
        abort(404)
    query = request.query_string.decode()
    return redirect(url_for(endpoint) + ("?" + query if query else ""), code=301)


@app.route("/api/session")
def api_session():
    """Used by topNavBar.js to show "Sign in" or "Account"."""
    if g.user is None:
        return {"signed_in": False}
    return {"signed_in": True, "name": g.user["name"]}


# ---------- Contact ----------

@app.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def contact():
    """Contact page. Each problem is reported against its own field, so the page can list them
    all in the error summary and show each one next to its box."""
    errors = {}
    sent = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        message = request.form.get("message", "").strip()

        for field, error in (("name", name_error(name)), ("email", email_error(email)),
                             ("message", message_error(message))):
            if error:
                errors[field] = error

        if not errors:
            db = get_db()
            db.execute(
                "INSERT INTO messages (name, email, message) VALUES (?, ?, ?)",
                (name, email, message),
            )
            db.commit()
            if is_slack_configured():
                try:
                    send_to_slack({"name": name, "email": email, "message": message})
                except Exception:
                    # The message is already saved, so Slack being down mustn't break the form.
                    log.exception("Could not send message to Slack")
            # Post/Redirect/GET, so refreshing the thank-you page can't send the message again.
            # The GET below pops this, so the confirmation shows only once.
            session["contact_sent"] = {"name": name, "email": email}
            return redirect(url_for("contact"))
    else:
        sent = session.pop("contact_sent", None)

    return render_template("contact.html", errors=errors, sent=sent)


# ---------- Register your interest ----------
# The /interest page (three steps, plain form posts) and /api/interest (JSON) share the checks,
# load_interest(), save_interest() and remove_interest() below, so they can't disagree.

INTEREST_STEPS = [("about", "About you"), ("interests", "Your interests"), ("check", "Check and send")]
INTEREST_STEP_KEYS = [key for key, _ in INTEREST_STEPS]
# The fields each step asks for, in the order the page shows them (also the error summary order).
STEP_FIELDS = {
    "about": ("role", "school"),
    "interests": ("routes", "year_group", "contact_consent"),
}
ALL_INTEREST_FIELDS = STEP_FIELDS["about"] + STEP_FIELDS["interests"]


def role_error(role):
    return None if role in ROLE_LABELS else "Select who you are"


def school_error(school):
    if not isinstance(school, str):
        return "School or college name must be text"
    if len(school) > MAX_SCHOOL_LENGTH:
        return f"School or college name must be {MAX_SCHOOL_LENGTH} characters or fewer"
    return None


def routes_error(routes):
    if not routes or any(route not in ROUTE_KEYS for route in routes):
        return "Select at least one placement route"
    return None


def year_group_error(year_group):
    return None if year_group in YEAR_LABELS else "Select a year group"


def consent_error(consent):
    return None if consent is True else "Tick the box to agree to be contacted"


def interest_errors(interest, fields=ALL_INTEREST_FIELDS):
    """Checks the given fields of an interest. Returns {field: message} for each problem."""
    checks = {
        "role": role_error(interest["role"]),
        "school": school_error(interest["school"]),
        "routes": routes_error(interest["routes"]),
        "year_group": year_group_error(interest["year_group"]),
        "contact_consent": consent_error(interest["contact_consent"]),
    }
    return {field: checks[field] for field in fields if checks[field]}


def tidy_choice(value):
    return value.strip().lower() if isinstance(value, str) else ""


def tidy_routes(values):
    """Lower-cases and de-duplicates the routes and puts them in the site's order. Unknown
    values are kept, so routes_error() rejects them rather than them being silently dropped."""
    chosen = {tidy_choice(value) for value in values}
    return [key for key, _ in ROUTES if key in chosen] + sorted(chosen - ROUTE_KEYS)


def empty_interest():
    return {"role": "", "school": "", "routes": [], "year_group": "", "contact_consent": False}


def interest_from_form(form):
    return {
        "role": tidy_choice(form.get("role")),
        "school": form.get("school", "").strip(),
        "routes": tidy_routes(form.getlist("routes")),
        "year_group": tidy_choice(form.get("year_group")),
        "contact_consent": form.get("contact_consent") == "yes",
    }


def interest_from_json(data):
    school = data.get("school", "")
    routes = data.get("routes")
    return {
        "role": tidy_choice(data.get("role")),
        "school": school.strip() if isinstance(school, str) else school,
        "routes": tidy_routes(routes) if isinstance(routes, list) else [],
        "year_group": tidy_choice(data.get("year_group")),
        "contact_consent": data.get("contact_consent") is True,
    }


def load_interest(user_id):
    """Returns the user's saved interest as a dict, or None if they haven't registered any."""
    db = get_db()
    row = db.execute(
        "SELECT role, school, year_group, contact_consent, created_at, updated_at FROM interests WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    chosen = {r["route"] for r in db.execute("SELECT route FROM interest_routes WHERE user_id = ?", (user_id,))}
    return {
        "role": row["role"],
        "school": row["school"],
        "routes": [key for key, _ in ROUTES if key in chosen],
        "year_group": row["year_group"],
        "contact_consent": bool(row["contact_consent"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def interest_summary(interest):
    """Rows for the Check step and the account page: (label, answer, the step that asks for it)."""
    return [
        ("I am", ROLE_LABELS.get(interest["role"], ""), "about"),
        ("School or college", interest["school"] or "Not given", "about"),
        ("Placement routes", ", ".join(ROUTE_LABELS[r] for r in interest["routes"] if r in ROUTE_LABELS), "interests"),
        ("Year group", YEAR_LABELS.get(interest["year_group"], ""), "interests"),
    ]


def notify_slack_about_interest(user, interest, action):
    """Posts a new, updated or removed interest to the team's Slack channel. The answers are
    already saved, so Slack being down mustn't break the page or the API."""
    if not is_slack_configured():
        return
    payload = {"action": action, "name": user["name"], "email": user["email"]}
    if interest is not None:
        payload.update({
            "role": ROLE_LABELS[interest["role"]],
            "school": interest["school"],
            "year_group": YEAR_LABELS[interest["year_group"]],
            "routes": [ROUTE_LABELS[route] for route in interest["routes"]],
        })
    try:
        send_interest_to_slack(payload)
    except Exception:
        log.exception("Could not send interest to Slack")


def save_interest(user, interest):
    """Saves a checked interest for the user, replacing any earlier one, and tells Slack.
    Returns True if it was new, False if it updated an earlier one."""
    db = get_db()
    is_new = db.execute("SELECT 1 FROM interests WHERE user_id = ?", (user["id"],)).fetchone() is None
    db.execute(
        """
        INSERT INTO interests (user_id, role, school, year_group, contact_consent) VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(user_id) DO UPDATE SET role = excluded.role, school = excluded.school,
            year_group = excluded.year_group, contact_consent = 1, updated_at = CURRENT_TIMESTAMP
        """,
        (user["id"], interest["role"], interest["school"], interest["year_group"]),
    )
    db.execute("DELETE FROM interest_routes WHERE user_id = ?", (user["id"],))
    db.executemany(
        "INSERT INTO interest_routes (user_id, route) VALUES (?, ?)",
        [(user["id"], route) for route in interest["routes"]],
    )
    db.commit()
    session.pop("interest_draft", None)  # The page starts from the saved answers next time.
    notify_slack_about_interest(user, interest, "new" if is_new else "updated")
    return is_new


def remove_interest(user):
    """Deletes the user's interest and tells Slack. Returns True if there was one to delete."""
    db = get_db()
    removed = db.execute("DELETE FROM interests WHERE user_id = ?", (user["id"],)).rowcount > 0
    db.execute("DELETE FROM interest_routes WHERE user_id = ?", (user["id"],))
    db.commit()
    session.pop("interest_draft", None)
    if removed:
        notify_slack_about_interest(user, None, "removed")
    return removed


def first_incomplete_step(interest):
    for step in ("about", "interests"):
        if interest_errors(interest, STEP_FIELDS[step]):
            return step
    return "check"


def interest_draft():
    """The answers given so far, kept in the session between steps. Starts from the saved
    interest, if any, except consent, which is asked for again each time the answers are sent."""
    draft = session.get("interest_draft")
    if draft is None:
        draft = load_interest(g.user["id"]) or empty_interest()
        draft = {field: draft[field] for field in ALL_INTEREST_FIELDS}
        draft["contact_consent"] = False
    return draft


def interest_step_url(step):
    return url_for("interest", step=step)


def render_interest(step, draft=None, errors=None, **context):
    """Shows interest.html at a step (None when signed out or after sending)."""
    return render_template(
        "interest.html",
        step=step,
        step_index=INTEREST_STEP_KEYS.index(step) if step else None,
        step_label=dict(INTEREST_STEPS)[step] if step else None,
        steps=INTEREST_STEPS,
        roles=INTEREST_ROLES,
        routes=ROUTES,
        year_groups=YEAR_GROUPS,
        draft=draft or empty_interest(),
        errors=errors or {},
        summary=interest_summary(draft) if step == "check" else [],
        **context,
    )


@app.route("/interest", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def interest():
    """Register your interest, in three steps: About you, Your interests, Check and send.
    Each step is a plain form post, so the page works without JavaScript. Visitors who aren't
    signed in are asked to sign in or create an account first."""
    if g.user is None:
        return render_interest(None)

    has_saved = load_interest(g.user["id"]) is not None

    if request.method == "GET":
        sent = session.pop("interest_sent", None)
        if sent:
            return render_interest(None, sent=sent)
        draft = interest_draft()
        step = request.args.get("step")
        if step not in INTEREST_STEP_KEYS:
            step = "about"
        # No skipping ahead: e.g. ?step=check before the routes are chosen opens that step instead.
        furthest = first_incomplete_step(draft)
        if INTEREST_STEP_KEYS.index(step) > INTEREST_STEP_KEYS.index(furthest):
            return redirect(interest_step_url(furthest))
        return render_interest(step, draft, has_saved=has_saved)

    step = request.form.get("step")
    if step not in INTEREST_STEP_KEYS:
        abort(400)
    going_back = request.form.get("go") == "back"
    draft = interest_draft()

    if step in STEP_FIELDS:
        # Back keeps this step's answers without checking them, so nothing ticked is lost.
        answers = interest_from_form(request.form)
        for field in STEP_FIELDS[step]:
            draft[field] = answers[field]
        session["interest_draft"] = draft
        if going_back:
            return redirect(interest_step_url("about"))
        errors = interest_errors(draft, STEP_FIELDS[step])
        if errors:
            return render_interest(step, draft, errors, has_saved=has_saved)
        return redirect(interest_step_url(INTEREST_STEP_KEYS[INTEREST_STEP_KEYS.index(step) + 1]))

    if going_back:
        return redirect(interest_step_url("interests"))
    # Everything is checked again before saving, in case the session's draft is incomplete.
    errors = interest_errors(draft)
    if errors:
        furthest = first_incomplete_step(draft)
        step_errors = {field: errors[field] for field in STEP_FIELDS[furthest] if field in errors}
        return render_interest(furthest, draft, step_errors, has_saved=has_saved)
    is_new = save_interest(g.user, draft)
    # Post/Redirect/GET, so refreshing the thank-you page can't send the answers again.
    session["interest_sent"] = "new" if is_new else "updated"
    return redirect(url_for("interest"))


def api_login_required(view):
    """Like login_required, but answers 401 JSON, since a script can't follow a redirect to a sign-in page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return {"error": "Please sign in"}, 401
        return view(*args, **kwargs)
    return wrapped


@app.route("/api/interest", methods=["GET", "POST", "DELETE"])
@limiter.limit("10 per minute", methods=["POST", "DELETE"])
@api_login_required
def api_interest():
    """GET: {"interest": {...} or null}.
    POST {"role", "school" (optional), "year_group", "routes": [...], "contact_consent": true}:
    saves it, 201 if new or 200 if it replaced an earlier one; 400 {"errors": {field: message}}.
    DELETE: removes it, 204.
    POST and DELETE need the X-CSRFToken header (Flask-WTF checks it)."""
    if request.method == "GET":
        return {"interest": load_interest(g.user["id"])}

    if request.method == "DELETE":
        remove_interest(g.user)
        return "", 204

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Expected a JSON object."}, 400
    answers = interest_from_json(data)
    errors = interest_errors(answers)
    if errors:
        return {"errors": errors}, 400
    is_new = save_interest(g.user, answers)
    return {"interest": load_interest(g.user["id"])}, 201 if is_new else 200


# ---------- Accounts ----------

def try_register(form):
    """Creates a user and signs them in. Returns an error message, or None if it worked."""
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")  # Not stripped: spaces could be deliberate.
    confirm = form.get("confirm_password", "")

    error = name_error(name) or email_error(email) or password_error(password, confirm)
    if error:
        return error

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            # pbkdf2, because some Pythons (e.g. the one built into macOS) lack scrypt, the default.
            (name, email, generate_password_hash(password, method="pbkdf2:sha256")),
        )
    except sqlite3.IntegrityError:  # The email is already taken.
        return "An account with that email already exists. Please sign in instead."
    # Failed sign-ins are counted for any email typed in, so someone who tried to sign in before
    # making an account would otherwise find their new account locked.
    db.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
    db.commit()

    # The sign-up form has no "Keep me signed in" box, so it acts as if it was left unticked.
    start_session(cur.lastrowid, remember=False)
    return None


def record_failed_login(db, email):
    """Counts one wrong password for this email, locks it on the last attempt,
    and returns the error message showing which attempt this was."""
    # Clear out locks that have run out, so the table doesn't keep growing. Clearing this
    # email's old lock also makes this attempt count as the first one again.
    db.execute("DELETE FROM login_attempts WHERE locked_until > 0 AND locked_until <= ?", (time.time(),))
    db.execute(
        """
        INSERT INTO login_attempts (email, failed_count, locked_until) VALUES (?, 1, 0)
        ON CONFLICT(email) DO UPDATE SET failed_count = failed_count + 1
        """,
        (email,),
    )
    attempt = db.execute(
        "SELECT failed_count FROM login_attempts WHERE email = ?", (email,)
    ).fetchone()["failed_count"]

    if attempt >= MAX_LOGIN_ATTEMPTS:
        db.execute(
            "UPDATE login_attempts SET locked_until = ? WHERE email = ?",
            (time.time() + LOCKOUT_MINUTES * 60, email),
        )
        db.commit()
        return (f"Incorrect email or password (attempt {MAX_LOGIN_ATTEMPTS} out of {MAX_LOGIN_ATTEMPTS}). "
                f"This account is now locked for {LOCKOUT_MINUTES} minutes.")
    db.commit()
    return f"Incorrect email or password (attempt {attempt} out of {MAX_LOGIN_ATTEMPTS})."


def try_login(form):
    """Signs a user in. Returns an error message, or None if it worked."""
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    # Empty boxes, or an email too long to be real, don't count as an attempt.
    if not email or not password or len(email) > MAX_EMAIL_LENGTH:
        return "Incorrect email or password."
    db = get_db()

    # A locked email is refused without checking the password.
    attempts = db.execute(
        "SELECT failed_count, locked_until FROM login_attempts WHERE email = ?", (email,)
    ).fetchone()
    now = time.time()
    if attempts is not None and attempts["locked_until"] > now:
        minutes_left = int((attempts["locked_until"] - now) // 60) + 1  # Round up, so it never says 0.
        return (f"Too many failed attempts. This account is locked. "
                f"Try again in {minutes_left} minute{'s' if minutes_left != 1 else ''}.")

    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        return record_failed_login(db, email)

    db.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
    db.commit()
    start_session(user["id"], remember=form.get("remember") == "1")
    return None


# ---------- Members-only downloads ----------

# Only names in this list can be downloaded, so /download/<name> can't read any other file.
DOWNLOADS = {
    "digital-production-design-development-spec": "digital-production-design-development-spec.pdf",
    "digital-support-services-spec": "digital-support-services-spec.pdf",
    "management-administration-spec": "management-administration-spec.pdf",
    "media-broadcast-production-spec": "media-broadcast-production-spec.pdf",
    "accounting-spec": "accounting-spec.pdf",
    "engineering-manufacturing-processing-control-spec": "engineering-manufacturing-processing-control-spec.pdf",
}


@app.route("/download/<name>")
@limiter.limit("30 per minute")  # Stops anyone scraping the files in bulk.
def download(name):
    """Sends a spec PDF to signed-in users. Others are sent to sign in, then back to the T Levels page."""
    if g.user is None:
        return redirect(url_for("login", next=url_for("t_levels")))
    filename = DOWNLOADS.get(name)
    if filename is None:
        abort(404)
    response = send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)
    response.headers["Cache-Control"] = "private, no-store"  # No shared-cache copies of members-only files.
    return response


def try_change_name(form):
    """Saves a new name for the signed-in user. Returns an error message, or None if it worked."""
    name = form.get("name", "").strip()
    error = name_error(name)
    if error:
        return error
    db = get_db()
    db.execute("UPDATE users SET name = ? WHERE id = ?", (name, g.user["id"]))
    db.commit()
    return None


def try_change_email(form):
    """Saves a new email for the signed-in user. Returns an error message, or None if it worked."""
    email = form.get("email", "").strip().lower()
    # The email is what people sign in with, so changing it needs the current password, in case
    # someone else is using a computer that was left signed in.
    error = email_error(email) or current_password_error(g.user["id"], form.get("current_password", ""))
    if error:
        return error
    db = get_db()
    try:
        db.execute("UPDATE users SET email = ? WHERE id = ?", (email, g.user["id"]))
        # Clear any lock on the new email, or the user couldn't sign in with it (see try_register).
        db.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
        db.commit()
    except sqlite3.IntegrityError:  # Another account already has this email.
        return "An account with that email already exists."
    return None


def try_change_password(form):
    """Sets a new password for the signed-in user. Returns an error message, or None if it worked."""
    error = (current_password_error(g.user["id"], form.get("current_password", ""))
             or password_error(form.get("new_password", ""), form.get("confirm_password", "")))
    if error:
        return error

    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(form["new_password"], method="pbkdf2:sha256"), g.user["id"]),
    )
    db.commit()
    # A fresh session after a password change, as after signing in, keeping "Keep me signed in".
    start_session(g.user["id"], remember=bool(session.get("remember")))
    return None


# The account page shows the details, each with a pencil that opens a form to change just that one.
# The pencil links to /account?edit=<form>, so it works without JavaScript; auth.js opens it in place.
def try_remove_interest(form):
    """Deletes the user's registered interest. The confirmation is the form itself:
    "Remove" only opens it, and nothing is deleted until "Yes, remove it" is pressed."""
    remove_interest(g.user)
    return None


def try_delete_account(form):
    """Deletes the signed-in user's account and everything saved against it, then signs them out.
    Asks for the current password, like the email and password forms, so someone using a
    computer left signed in can't delete another person's account."""
    error = current_password_error(g.user["id"], form.get("current_password", ""))
    if error:
        return error
    # Through remove_interest, so the team hears on Slack to stop contacting this person.
    remove_interest(g.user)
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE email = ?", (g.user["email"],))
    db.execute("DELETE FROM users WHERE id = ?", (g.user["id"],))
    db.commit()
    session.clear()
    return None


ACCOUNT_FORMS = {
    "name": (try_change_name, "Your name has been changed."),
    "email": (try_change_email, "Your email has been changed."),
    "password": (try_change_password, "Your password has been changed."),
    "remove-interest": (try_remove_interest, "Your interest has been removed."),
    "delete": (try_delete_account, "Your account has been deleted."),
}


def render_account(**context):
    saved = load_interest(g.user["id"])
    return render_template("account.html", interest=saved,
                           interest_rows=interest_summary(saved) if saved else [], **context)


@app.route("/account")
@login_required
def account():
    edit = request.args.get("edit")
    return render_account(open_form=edit if edit in ACCOUNT_FORMS else None)


# Each form shows account.html again on error, with that form still open, and redirects back to
# /account with a message when it works, so a refresh doesn't resend it.
# Rate-limited like sign-in, because the email and password forms check the current password.
@app.route("/account/<form_name>", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def update_account(form_name):
    if form_name not in ACCOUNT_FORMS:
        abort(404)
    try_change, success_message = ACCOUNT_FORMS[form_name]
    error = try_change(request.form)
    if error:
        return render_account(open_form=form_name, form_error=error)
    flash(success_message)
    # A deleted account has no account page left, so its message is shown on the sign-in page.
    return redirect(url_for("login" if form_name == "delete" else "account"))


def can_see_analytics(user):
    """True if this signed-in user's email is listed in ANALYTICS_EMAILS."""
    return user is not None and user["email"] in ANALYTICS_EMAILS


@app.context_processor
def inject_analytics_access():
    """Lets templates show the analytics link only to people who can open it."""
    return {"can_see_analytics": can_see_analytics(g.get("user"))}


def count_by_route(db, kind):
    """Counts the events of one kind for each route, including routes with none.
    Returns e.g. [{"key": "digital", "name": "Digital", "count": 4}, ...] in the site's route order."""
    rows = db.execute(
        "SELECT value, COUNT(*) AS n FROM analytics_events WHERE kind = ? GROUP BY value", (kind,)
    ).fetchall()
    counts = {row["value"]: row["n"] for row in rows}
    return [{"key": key, "name": name, "count": counts.get(key, 0)} for key, name in ROUTES]


@app.route("/analytics")
@login_required
def analytics():
    """Site analytics for the team: enquiries, accounts, searches, programme views and quiz results."""
    if not can_see_analytics(g.user):
        abort(404)  # Act as if the page doesn't exist.
    db = get_db()

    def count(sql, *args):
        return db.execute(sql, args).fetchone()[0]

    def count_events(kind, since=None):
        if since is None:
            return count("SELECT COUNT(*) FROM analytics_events WHERE kind = ?", kind)
        return count("SELECT COUNT(*) FROM analytics_events WHERE kind = ? AND created_at >= datetime('now', ?)",
                     kind, since)

    week = "-7 days"  # SQLite's way of saying "7 days ago".
    totals = {
        "enquiries": count("SELECT COUNT(*) FROM messages"),
        "accounts": count("SELECT COUNT(*) FROM users"),
        "searches": count_events("search"),
        "quizzes": count_events("quiz"),
    }
    this_week = [
        ("Enquiries", count("SELECT COUNT(*) FROM messages WHERE created_at >= datetime('now', ?)", week)),
        ("New accounts", count("SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', ?)", week)),
        ("Searches", count_events("search", week)),
        ("Programme views", count_events("view", week)),
        ("Quizzes completed", count_events("quiz", week)),
    ]
    searches = db.execute(
        "SELECT value, COUNT(*) AS n FROM analytics_events WHERE kind = 'search' "
        "GROUP BY value ORDER BY n DESC, value LIMIT 10"
    ).fetchall()

    return render_template(
        "analytics.html",
        totals=totals,
        this_week=this_week,
        searches=searches,
        views=count_by_route(db, "view"),
        quiz_results=count_by_route(db, "quiz"),
    )


# login.html holds both the sign-in and the sign-up form. Sign-in posts to /login and
# sign-up to /register; both show login.html again on error, keeping any ?next= page.

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if g.user is not None:
        return redirect(url_for("account"))
    error = None
    if request.method == "POST":
        error = try_login(request.form)
        if error is None:
            return redirect_after_sign_in()
    return render_template("login.html", login_error=error)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def register():
    if g.user is not None:
        return redirect(url_for("account"))
    error = None
    if request.method == "POST":
        error = try_register(request.form)
        if error is None:
            return redirect_after_sign_in()
    return render_template("login.html", register_error=error)


@app.route("/logout", methods=["POST"])  # POST only, so other sites can't sign people out with a link.
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------- AI chat ----------
# Exempt from CSRF because it only accepts JSON, which other websites can't send without our permission.

csrf.exempt(chat_bp)
app.register_blueprint(chat_bp)
csrf.exempt(api_track)  # JSON only too, for the same reason.


# ---------- Error pages ----------

def visitable_pages():
    """Every page a visitor could open directly by its short URL, e.g. ["/", "/advice", "/faqs", ...]."""
    return sorted({
        rule.rule for rule in app.url_map.iter_rules()
        if "GET" in rule.methods
        and not rule.arguments
        and not rule.rule.startswith(("/api", "/static", "/Sources"))
        and rule.rule != "/analytics"  # Team-only, so don't suggest it on the 404 page.
    })


def tidy_path(path):
    """Lower-cases a path and drops a trailing "/" or ".html", e.g. "/FAQS.html/" gives "/faqs"."""
    return path.lower().rstrip("/").removesuffix(".html") or "/"


def same_page_ignoring_case(path):
    """Returns the real page if `path` only differs by capitals, e.g. "/FAQS" gives "/faqs"."""
    typed = tidy_path(path)
    for page in visitable_pages():
        if page.lower() == typed and page != path:
            return page
    return None


def suggest_page(path):
    """Returns the real page closest to a mistyped `path` (e.g. "/faq" gives "/faqs"),
    or None if nothing is close enough."""
    match = difflib.get_close_matches(tidy_path(path), visitable_pages(), n=1, cutoff=0.6)
    return match[0] if match and match[0] != path else None


@app.errorhandler(404)
def page_not_found(e):
    # Only the capitals are wrong (e.g. "/FAQS")? Redirect to the real page. GET/HEAD only,
    # because redirecting a submitted form would lose what was typed into it.
    correct = same_page_ignoring_case(request.path)
    if correct and request.method in ("GET", "HEAD"):
        query = request.query_string.decode()
        return redirect(correct + ("?" + query if query else ""), code=301)

    return render_template("404.html", suggestion=suggest_page(request.path)), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


@app.errorhandler(CSRFError)
def csrf_error(e):
    if request.path.startswith("/api/"):
        return {"error": "Missing or invalid X-CSRFToken header."}, 400
    return ("Your form session expired or was invalid. "
            "Please go back, refresh the page and try again."), 400


@app.errorhandler(429)
def too_many_requests(e):
    if not request.path.startswith("/api/"):
        return "Too many attempts. Please wait a minute and try again.", 429
    # The chat widget reads {"error": ...} from the API, so it gets JSON and a Retry-After.
    response = jsonify({"error": CHAT_RATE_LIMITED})
    response.status_code = 429
    current = limiter.current_limit
    if current is not None:
        response.headers["Retry-After"] = str(max(1, int(current.reset_at - time.time()) + 1))
    return response


@app.errorhandler(413)
def too_large(e):
    return "That form submission was too large.", 413


# ---------- Run ----------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    # In debug mode Flask runs this file twice (a file watcher and the server); only the server starts the bot.
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_slack_bot()
    app.run(debug=DEBUG)
