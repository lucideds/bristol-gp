"""Flask backend for the T Level Connect site.

Serves the pages, stores accounts and contact messages in SQLite, and handles signing in
and out. The chat widget's API lives in chat_api.py.
"""

import difflib
import os
import re
import secrets
import sqlite3
import time
from functools import wraps
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, abort, g, redirect, render_template, request, send_from_directory, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from chat_api import chat_bp

# bot/bot.py posts each contact message to Slack. Without slack_bolt the site still works.
try:
    from bot.bot import is_configured as is_slack_configured, send_to_slack, start_in_background as start_slack_bot
except ImportError:
    print("WARNING: slack_bolt is not installed, so contact messages won't be sent to Slack. "
          "Run: pip install -r requirements.txt")
    def is_slack_configured():
        return False
    def start_slack_bot():
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "site.db")

# Members-only spec PDFs. Kept out of frontend/Template/Sources, which Flask serves to anyone;
# these can only be fetched through /download/<name>, which requires sign-in.
DOWNLOADS_DIR = os.path.join(BASE_DIR, "resources", "specs")

# Real environment variables win over .env. Must run before the os.environ.get() calls below.
load_dotenv(os.path.join(BASE_DIR, ".env"))

DEBUG = os.environ.get("FLASK_DEBUG") == "1"

MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254
MAX_MESSAGE_LENGTH = 2000
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 8

# A capital, a number and a special character (anything but a letter, digit or space).
# auth.js checks the same rules in the browser, so keep the two in step.
PASSWORD_CAPITAL = re.compile(r"[A-Z]")
PASSWORD_NUMBER = re.compile(r"[0-9]")
PASSWORD_SPECIAL = re.compile(r"[^A-Za-z0-9\s]")

# After MAX_LOGIN_ATTEMPTS wrong passwords in a row, sign-in for that email is locked for
# LOCKOUT_MINUTES. The lock is timed because there's no password reset yet, and a permanent
# lock would let anyone lock a real user out for good just by knowing their email.
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_MINUTES = 15

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Static files are served at /Sources/... to match the href="Sources/..." links in the pages.
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend", "Template"),
    static_folder=os.path.join(BASE_DIR, "frontend", "Template", "Sources"),
    static_url_path="/Sources",
)

# Without SECRET_KEY a random key is used, which signs everyone out whenever the app restarts.
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    print("WARNING: SECRET_KEY is not set, using a random key. "
          "Users will be signed out whenever the app restarts.")
    secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = secret_key
app.config["TEMPLATES_AUTO_RELOAD"] = True

# SECURE is opt-in (HTTPS=1) because local testing uses http://, where the browser would drop the cookie.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HTTPS") == "1"

# The forms are tiny. chat_api.py raises this limit for chat requests.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")


# ---------- Security headers ----------

# Only our own site may supply scripts, styles and data, plus Google Fonts for the accessibility
# font. Inline <script>, <style> and onclick="" are blocked, which is why all page behaviour
# lives in Sources/js and all styles in Sources/css.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
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
    # Same switch as SESSION_COOKIE_SECURE, so local http:// testing isn't affected.
    if os.environ.get("HTTPS") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


# ---------- Database ----------

def get_db():
    """Returns this request's database connection, opening it on first use."""
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


def is_valid_email(email):
    return len(email) <= MAX_EMAIL_LENGTH and EMAIL_PATTERN.fullmatch(email) is not None


# ---------- Public pages ----------
# The nav bar and footer link to the ".html" file names, so each page answers on both its file
# name and its short URL. The short URL is listed last so url_for() builds that one.

@app.route("/home.html")
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/accessibility.html")
@app.route("/accessibility")
def accessibility():
    # Old links. The settings are now a popup on every page.
    return redirect(url_for("home") + "#accessibility")


@app.route("/faqs.html")
@app.route("/faqs")
def faqs():
    return render_template("faqs.html")


@app.route("/TLevel.html")
@app.route("/t-levels")
def t_levels():
    return render_template("TLevel.html")


@app.route("/advice.html")
@app.route("/advice")
def advice():
    return render_template("advice.html")


@app.route("/privacy.html")
@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/quiz.html")
@app.route("/quiz")
def quiz():
    return render_template("quiz.html")


@app.route("/api/session")
def api_session():
    """Used by topNavBar.js to show "Sign in" or "Account"."""
    if g.user is None:
        return {"signed_in": False}
    return {"signed_in": True, "name": g.user["name"]}


# ---------- Contact ----------

@app.route("/contact.html", methods=["GET", "POST"])
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

        if not name:
            errors["name"] = "Enter your name"
        elif len(name) > MAX_NAME_LENGTH:
            errors["name"] = f"Name must be {MAX_NAME_LENGTH} characters or fewer"

        if not email:
            errors["email"] = "Enter your email address"
        elif not is_valid_email(email):
            errors["email"] = "Enter an email address in the correct format, like name@example.com"

        if not message:
            errors["message"] = "Enter your message"
        elif len(message) > MAX_MESSAGE_LENGTH:
            errors["message"] = f"Message must be {MAX_MESSAGE_LENGTH} characters or fewer"

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
                except Exception as e:
                    # The message is already saved, so Slack being down mustn't break the form.
                    print("Could not send message to Slack:", e)
            # Post/Redirect/GET, so refreshing the thank-you page can't send the message again.
            # The GET below pops this, so the confirmation shows only once.
            session["contact_sent"] = {"name": name, "email": email}
            return redirect(url_for("contact"))
    else:
        sent = session.pop("contact_sent", None)

    return render_template("contact.html", errors=errors, sent=sent)


# ---------- Accounts ----------

def try_register(form):
    """Creates a user and signs them in. Returns an error message, or None if it worked."""
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")  # Not stripped: spaces could be deliberate.
    confirm = form.get("confirm_password", "")

    if not name or not email or not password:
        return "Please fill in every field."
    if len(name) > MAX_NAME_LENGTH:
        return f"Name must be {MAX_NAME_LENGTH} characters or fewer."
    if not is_valid_email(email):
        return "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
    if not PASSWORD_CAPITAL.search(password):
        return "Password must include a capital letter."
    if not PASSWORD_NUMBER.search(password):
        return "Password must include a number."
    if not PASSWORD_SPECIAL.search(password):
        return "Password must include a special character, such as ! ? # or @."
    if password != confirm:
        return "Passwords do not match."

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            # pbkdf2, because some Pythons (e.g. the one built into macOS) lack scrypt, the default.
            (name, email, generate_password_hash(password, method="pbkdf2:sha256")),
        )
        db.commit()
    except sqlite3.IntegrityError:  # The email is already taken.
        return "An account with that email already exists. Please sign in instead."

    session.clear()
    session["user_id"] = cur.lastrowid
    return None


def record_failed_login(db, email):
    """Counts one wrong password for this email, locks it on the last attempt,
    and returns the error message showing which attempt this was."""
    # An old lock that has run out counts as a fresh start, so the count goes back to 1.
    db.execute(
        """
        INSERT INTO login_attempts (email, failed_count, locked_until) VALUES (?, 1, 0)
        ON CONFLICT(email) DO UPDATE SET
            failed_count = CASE WHEN locked_until > 0 THEN 1 ELSE failed_count + 1 END,
            locked_until = 0
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
    if not email or not password:  # Empty boxes don't count as an attempt.
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
    session.clear()
    session["user_id"] = user["id"]
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


@app.route("/account.html")
@app.route("/account")
@login_required
def account():
    return render_template("account.html")


# login.html holds both the sign-in and the sign-up form. Sign-in posts to /login and
# sign-up to /register; both show login.html again on error.

@app.route("/login.html", methods=["GET", "POST"])
@app.route("/signin.html")  # The nav bar's "Sign in" button links here.
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if g.user is not None:
        return redirect(url_for("account"))
    error = None
    if request.method == "POST":
        error = try_login(request.form)
        if error is None:
            next_page = request.args.get("next", "")
            if is_safe_redirect(next_page):
                return redirect(next_page)
            return redirect(url_for("account"))
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
            return redirect(url_for("account"))
    return render_template("login.html", register_error=error)


@app.route("/logout", methods=["POST"])  # POST only, so other sites can't sign people out with a link.
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------- AI chat ----------
# Exempt from CSRF because it only accepts JSON, which other websites can't send without our permission.

csrf.exempt(chat_bp)
app.register_blueprint(chat_bp)


# ---------- Error pages ----------

def visitable_pages():
    """Every page a visitor could open directly by its short URL, e.g. ["/", "/advice", "/faqs", ...]."""
    return sorted({
        rule.rule for rule in app.url_map.iter_rules()
        if "GET" in rule.methods
        and not rule.arguments
        and not rule.rule.endswith(".html")
        and not rule.rule.startswith(("/api", "/static", "/Sources"))
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
    return ("Your form session expired or was invalid. "
            "Please go back, refresh the page and try again."), 400


@app.errorhandler(429)
def too_many_requests(e):
    return "Too many attempts. Please wait a minute and try again.", 429


@app.errorhandler(413)
def too_large(e):
    return "That form submission was too large.", 413


# ---------- Run ----------

init_db()

if __name__ == "__main__":
    # In debug mode Flask runs this file twice (a file watcher and the server); only the server starts the bot.
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_slack_bot()
    app.run(debug=DEBUG)
