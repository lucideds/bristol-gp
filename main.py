# =====================================================================
# app.py - the Flask backend for the T-Levels website.
# It serves the HTML pages, stores user accounts and contact
# messages in a SQLite database, and handles signing in and out.
# The chat widget's AI API lives in chat_api.py and is plugged in below (see "AI chat").
# =====================================================================

import difflib     # Finds the closest matching text, used to suggest a page on the 404 page.
import os          # Lets us work with file paths and read environment variables.
import re          # Regular expressions, used to check that an email looks valid.
import secrets     # Makes secure random values (used for a fallback secret key).
import sqlite3     # Python's built-in library for SQLite databases (a database stored in one file).
import time       # Gives the current time, used to work out when a locked account unlocks.
from functools import wraps  # Helper used when writing decorators, keeps the original function's name.
from urllib.parse import urlparse  # Splits a URL into parts so we can check where a redirect goes.

from dotenv import load_dotenv  # Reads settings like SECRET_KEY and OPENROUTER_API_KEY from a .env file.

# Flask tools used in this file:
#   Flask           - the class that creates the web app
#   g               - a temporary storage area that lasts for one request (we keep the database connection and user in it)
#   redirect        - sends the browser to a different URL
#   render_template - loads an HTML file from the "frontend/Template" folder and fills in any {{ }} values
#   request         - holds everything about the incoming request (form data, method, URL)
#   session         - a secure cookie that remembers who is signed in between pages
#   url_for         - builds a URL from a function name, e.g. url_for("home") gives "/"
from flask import Flask, abort, g, redirect, render_template, request, send_from_directory, session, url_for

# Flask-WTF adds CSRF protection: every form must include a secret token that only
# our own pages know, so other websites can't submit our forms on someone's behalf.
from flask_wtf.csrf import CSRFError, CSRFProtect

# Flask-Limiter stops people trying thousands of passwords or spamming the contact form.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Werkzeug comes with Flask. These two functions handle passwords safely:
#   generate_password_hash - scrambles a password so the real one is never stored
#   check_password_hash    - checks a typed password against the scrambled version
from werkzeug.security import check_password_hash, generate_password_hash

# The AI chat API (/api/chat and /api/chat/stream) used by the chat widget.
from chat_api import chat_bp

# The Slack bot (bot/bot.py) posts each contact form message to Slack.
# If slack_bolt isn't installed, the site still works and just skips Slack.
try:
    from bot.bot import is_configured as is_slack_configured, send_to_slack, start_in_background as start_slack_bot
except ImportError:
    print("WARNING: slack_bolt is not installed, so contact messages won't be sent to Slack. "
          "Run: pip install -r requirements.txt")
    def is_slack_configured():
        return False
    def start_slack_bot():
        pass

# The folder this file lives in, so the database is always created next to app.py
# no matter which folder you run the program from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Full path to the database file, e.g. ".../tlevels-site/site.db".
DATABASE = os.path.join(BASE_DIR, "site.db")

# Members-only downloads (the T Level spec PDFs). This folder is deliberately NOT inside
# frontend/Template/Sources, because Flask serves everything in there to anyone. Files in here
# can only be fetched through the /download/<name> route, which checks the visitor is signed in.
DOWNLOADS_DIR = os.path.join(BASE_DIR, "resources", "specs")

# Load settings from the .env file next to this file (if there is one).
# Real environment variables always win over values in .env.
# This runs before any os.environ.get() below, so .env can set them all.
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Debug mode is only switched on if the FLASK_DEBUG environment variable is "1".
# This way it can't accidentally be left on when the site goes live.
DEBUG = os.environ.get("FLASK_DEBUG") == "1"

# Limits on how long each form field can be, so nobody can post huge amounts of text.
MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254          # The longest a real email address can be.
MAX_MESSAGE_LENGTH = 2000
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 8

# Password rules: at least one capital letter, one number and one special character.
# A special character is anything that isn't a letter, a number or a space (e.g. ! ? # @ £).
# auth.js checks the same rules in the browser, so keep the two in step.
PASSWORD_CAPITAL = re.compile(r"[A-Z]")
PASSWORD_NUMBER = re.compile(r"[0-9]")
PASSWORD_SPECIAL = re.compile(r"[^A-Za-z0-9\s]")

# Account lockout: after this many wrong passwords in a row, sign-in for that email is locked
# for LOCKOUT_MINUTES. It's a timed lock (not permanent) because there's no password reset yet,
# and a permanent lock would let anyone lock a real user out for good just by knowing their email.
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_MINUTES = 15

# A simple pattern for an email: some text, an @, some text, a dot, some text, no spaces.
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Create the Flask web application.
#   template_folder - the HTML pages live in frontend/Template
#   static_folder   - the CSS and JavaScript live in frontend/Template/Sources
#   static_url_path - serve them at /Sources/..., which matches the
#                     href="Sources/..." links already used in the pages
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend", "Template"),
    static_folder=os.path.join(BASE_DIR, "frontend", "Template", "Sources"),
    static_url_path="/Sources",
)

# The secret key is used to sign the session cookie so users can't fake being signed in.
# It reads SECRET_KEY from the environment. If it isn't set, a random key is made each
# time the app starts: still secure, but everyone gets signed out when the app restarts.
# Set SECRET_KEY before putting the site online.
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    print("WARNING: SECRET_KEY is not set, using a random key. "
          "Users will be signed out whenever the app restarts.")
    secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = secret_key
# Re-read an HTML page when its file changes, so edits show up without restarting the server.
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Cookie settings:
#   SAMESITE "Lax" - the browser won't send our cookie with forms submitted from other websites.
#   SECURE         - only send the cookie over HTTPS. Turned on by setting HTTPS=1, because
#                    local testing uses plain http:// and the browser would drop the cookie
#                    (so nobody could stay signed in).
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HTTPS") == "1"

# Reject any request bigger than 16 KB. Our forms are tiny, so this only stops abuse.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

# Turn on CSRF protection for every POST form in the app.
csrf = CSRFProtect(app)

# Rate limiter: counts requests per IP address, stored in memory.
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")


# ---------- Security headers ----------
# Extra instructions sent to the browser with every response (pages, CSS/JS files and error pages).
#
# Content-Security-Policy (CSP) - a list of where the page may load things from. Only our own site
#   ('self') is allowed, plus Google Fonts for the accessibility font. Inline <script>, <style> and
#   onclick="" are blocked too, so if someone sneaks a script into a page the browser won't run it.
#   That's why all scripts and styles live in Sources/js and Sources/css.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",                               # Anything not listed below: our site only.
    "script-src 'self'",                                # JavaScript files from Sources/js only.
    "style-src 'self' https://fonts.googleapis.com",    # Our CSS, plus the Google Fonts stylesheet.
    "font-src 'self' https://fonts.gstatic.com",        # Where Google Fonts serves the font files.
    "img-src 'self' data:",                             # Our images (data: covers small inline icons).
    "connect-src 'self'",                               # fetch() may only call our own server (the chat API).
    "object-src 'none'",                                # No plugins like Flash.
    "base-uri 'self'",                                  # Stops a planted <base> tag redirecting relative links.
    "form-action 'self'",                               # Forms can only submit to our site.
    "frame-ancestors 'none'",                           # No other site can show our pages in a frame.
])


@app.after_request                                      # Runs on every response, just before it's sent.
def set_security_headers(response):
    """Adds the security headers to every response."""
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    # Older browsers' version of frame-ancestors 'none': stops clickjacking.
    response.headers["X-Frame-Options"] = "DENY"
    # Trust the Content-Type we send, don't guess (stops a text file being run as a script).
    response.headers["X-Content-Type-Options"] = "nosniff"
    # When a visitor clicks a link to another site, only tell it our domain, not the full URL.
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # HSTS: "always use HTTPS for this site for the next year". Only sent when HTTPS=1 (the same
    # switch as SESSION_COOKIE_SECURE), so local http:// testing isn't affected.
    if os.environ.get("HTTPS") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


# ---------- Database ----------

def get_db():
    """Returns a connection to the database, opening one if this request doesn't have one yet."""
    if "db" not in g:                           # Only open a connection once per request.
        g.db = sqlite3.connect(DATABASE)        # Open (or create) the database file.
        g.db.row_factory = sqlite3.Row          # Lets us read columns by name, e.g. user["email"].
    return g.db                                 # Give the connection back to whoever asked for it.


@app.teardown_appcontext                        # Tells Flask to run this function at the end of every request.
def close_db(exception):
    """Closes the database connection when the request is finished."""
    db = g.pop("db", None)                      # Take the connection out of g (None if there wasn't one).
    if db is not None:                          # If a connection was opened...
        db.close()                              # ...close it to free up the file.


def init_db():
    """Creates the database tables if they don't already exist."""
    db = sqlite3.connect(DATABASE)              # Open the database file directly (no request is running yet).
    db.executescript(                           # Run several SQL commands in one go.
        """
        -- Table that stores user accounts.
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,      -- Unique number for each user, counts up automatically.
            name TEXT NOT NULL,                        -- The user's name (must be filled in).
            email TEXT NOT NULL UNIQUE,                -- Email address; UNIQUE stops two accounts using the same one.
            password_hash TEXT NOT NULL,               -- The scrambled password, never the real one.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- Date and time the account was made, filled in automatically.
        );

        -- Table that stores messages sent from the contact form.
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,      -- Unique number for each message.
            name TEXT NOT NULL,                        -- Sender's name.
            email TEXT NOT NULL,                       -- Sender's email.
            message TEXT NOT NULL,                     -- The message itself.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- When the message was sent.
        );

        -- Failed sign-in attempts, one row per email typed into the sign-in form.
        -- Kept by email (not user id) so an email with no account counts and locks the same way,
        -- which stops attackers using the lockout to find out which emails are registered.
        CREATE TABLE IF NOT EXISTS login_attempts (
            email TEXT PRIMARY KEY,                    -- The email typed in, lower-cased.
            failed_count INTEGER NOT NULL DEFAULT 0,   -- Wrong passwords in a row since the last success or lock.
            locked_until REAL NOT NULL DEFAULT 0       -- Unix time when the lock ends (0 = not locked).
        );
        """
    )
    db.commit()                                 # Save the changes to the file.
    db.close()                                  # Close the connection.


# ---------- Helpers ----------

@app.before_request                             # Runs at the start of every request, before the page function.
def load_user():
    """Looks up the signed-in user once per request and keeps them in g.user.
    If the session points to a user that no longer exists (e.g. the database was reset),
    the session is cleared so the person can sign in again instead of getting stuck."""
    g.user = None                               # Default: nobody is signed in.
    if "user_id" in session:                    # If the session cookie says someone is signed in...
        g.user = get_db().execute(              # ...look up their details in the database.
            "SELECT id, name, email, created_at FROM users WHERE id = ?",  # ? is filled in safely below (stops SQL injection).
            (session["user_id"],),              # The value that replaces the ?.
        ).fetchone()                            # Get the single matching row (or None).
        if g.user is None:                      # The user doesn't exist any more...
            session.clear()                     # ...so forget the old, broken session.


@app.context_processor                          # Runs before every template is rendered.
def inject_user():
    """Makes `current_user` available in every template, so pages can show
    'Log in' or 'Account' depending on whether someone is signed in."""
    return {"current_user": g.get("user")}      # g.get avoids a crash if load_user didn't run (e.g. on some error pages).


def login_required(view):
    """A decorator: put @login_required above a page function to make that page sign-in only.
    Used on the account page; add it to any other page you want to protect."""
    @wraps(view)                                # Keep the original function's name so url_for still works.
    def wrapped(*args, **kwargs):               # This replaces the page function and runs first.
        if g.user is None:                      # If nobody is signed in...
            return redirect(url_for("login", next=request.path))  # ...send them to log in, remembering where they were going.
        return view(*args, **kwargs)            # Otherwise run the real page function as normal.
    return wrapped                              # Hand back the new wrapped function.


def is_safe_redirect(target):
    """Returns True only if `target` is a path on this website (not another site).
    Backslashes are treated as slashes because browsers do the same, so
    tricks like "/\\evil.com" are caught."""
    if not target or not target.startswith("/"):    # Must be a path starting with "/".
        return False
    parts = urlparse(target.replace("\\", "/"))     # Split the URL into scheme, domain, path...
    return not parts.scheme and not parts.netloc    # Safe only if there's no "https:" and no domain.


def is_valid_email(email):
    """Returns True if the email looks like a real address and isn't too long."""
    return len(email) <= MAX_EMAIL_LENGTH and EMAIL_PATTERN.fullmatch(email) is not None


# ---------- Public pages ----------
# Each of these links a URL to an HTML file in the templates folder.
# The nav bar and footer (Sources/*.js) link to the ".html" file names, e.g. "/faqs.html",
# so each page answers on both its file name and its short URL. The short URL is listed
# last (closest to the function) so url_for() builds that one.

@app.route("/home.html")
@app.route("/")                                 # When someone visits the home URL "/"...
def home():
    return render_template("home.html")         # ...show the home page.


@app.route("/accessibility.html")
@app.route("/accessibility")                    # URL: /accessibility (old links and bookmarks)
def accessibility():
    # The settings are now a popup on every page, so open it on the home page.
    return redirect(url_for("home") + "#accessibility")


@app.route("/faqs.html")
@app.route("/faqs")                             # URL: /faqs
def faqs():
    return render_template("faqs.html")         # Show the FAQs page.


@app.route("/TLevel.html")
@app.route("/t-levels")                         # URL: /t-levels
def t_levels():
    return render_template("TLevel.html")       # Show the T-Levels page.


@app.route("/advice.html")
@app.route("/advice")                           # URL: /advice
def advice():
    return render_template("advice.html")       # Show the advice page.


@app.route("/privacy.html")
@app.route("/privacy")                          # URL: /privacy
def privacy():
    return render_template("privacy.html")      # Show the privacy page.


@app.route("/quiz.html")
@app.route("/quiz")                             # URL: /quiz
def quiz():
    return render_template("quiz.html")         # Show the quiz page.


@app.route("/api/session")                      # Used by topNavBar.js to show "Sign in" or "Account".
def api_session():
    """Tells the page's JavaScript whether someone is signed in (and their name)."""
    if g.user is None:
        return {"signed_in": False}             # Flask turns a dict into a JSON response.
    return {"signed_in": True, "name": g.user["name"]}


# ---------- Contact ----------

@app.route("/contact.html", methods=["GET", "POST"])
@app.route("/contact", methods=["GET", "POST"])  # GET = viewing the page, POST = submitting the form.
@limiter.limit("5 per minute", methods=["POST"])  # At most 5 messages a minute from one person (stops spam).
def contact():
    """Shows the contact page, and saves the message to the database when the form is sent."""
    error = None                                # No error message to start with.
    success = False                             # Becomes True once a message is saved.

    if request.method == "POST":                # Only do this when the form has been submitted.
        name = request.form.get("name", "").strip()               # Read the "name" box; strip() removes extra spaces.
        email = request.form.get("email", "").strip().lower()     # Read the "email" box; lower() to match account emails.
        message = request.form.get("message", "").strip()         # Read the "message" box.

        if not name or not email or not message:                  # If any box is empty...
            error = "Please fill in every field."                 # ...set an error to show on the page.
        elif len(name) > MAX_NAME_LENGTH:                         # Name too long?
            error = f"Name must be {MAX_NAME_LENGTH} characters or fewer."
        elif not is_valid_email(email):                           # Email doesn't look real?
            error = "Please enter a valid email address."
        elif len(message) > MAX_MESSAGE_LENGTH:                   # Message too long?
            error = f"Message must be {MAX_MESSAGE_LENGTH} characters or fewer."
        else:                                                     # Otherwise everything is fine, so:
            db = get_db()                                         # Get the database connection.
            db.execute(                                           # Add a new row to the messages table.
                "INSERT INTO messages (name, email, message) VALUES (?, ?, ?)",
                (name, email, message),                           # The values that fill in the three ?s.
            )
            db.commit()                                           # Save it.
            success = True                                        # Tell the page to show the thank-you message.
            if is_slack_configured():                             # Also post it to Slack, if Slack is set up.
                try:
                    send_to_slack({"name": name, "email": email, "message": message})
                except Exception as e:                            # Slack being down mustn't break the form;
                    print("Could not send message to Slack:", e)  # the message is already saved in the database.

    # Show the contact page, passing in error and success so the HTML can display them.
    return render_template("contact.html", error=error, success=success)


# ---------- Accounts ----------

def try_register(form):
    """Creates a user and signs them in. Returns an error message, or None if it worked."""
    name = form.get("name", "").strip()                    # Read the name box.
    email = form.get("email", "").strip().lower()          # Read the email box; lower() so "Bob@X.com" = "bob@x.com".
    password = form.get("password", "")                    # Read the password (not stripped, spaces could be deliberate).
    confirm = form.get("confirm_password", "")             # Read the "confirm password" box.

    if not name or not email or not password:              # Any required box empty?
        return "Please fill in every field."
    if len(name) > MAX_NAME_LENGTH:                        # Name too long?
        return f"Name must be {MAX_NAME_LENGTH} characters or fewer."
    if not is_valid_email(email):                          # Email doesn't look real?
        return "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:                # Password too short?
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:                # Password too long?
        return f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
    if not PASSWORD_CAPITAL.search(password):              # No capital letter?
        return "Password must include a capital letter."
    if not PASSWORD_NUMBER.search(password):               # No number?
        return "Password must include a number."
    if not PASSWORD_SPECIAL.search(password):              # No special character?
        return "Password must include a special character, such as ! ? # or @."
    if password != confirm:                                # The two passwords don't match?
        return "Passwords do not match."

    db = get_db()                                          # Get the database connection.
    try:                                                   # Try to add the user...
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password, method="pbkdf2:sha256")),  # Store the scrambled password, never the real one.
            # pbkdf2 is used because some Pythons (e.g. the one built into macOS) lack scrypt, the default.
        )
        db.commit()                                        # Save the new user.
    except sqlite3.IntegrityError:                         # This error happens if the email is already taken (UNIQUE rule).
        return "An account with that email already exists. Please sign in instead."

    session.clear()                                        # Wipe any old session data.
    session["user_id"] = cur.lastrowid                     # Sign the new user in by saving their id in the session.
    return None                                            # None means "no error, it worked".


def record_failed_login(db, email):
    """Counts one wrong password for this email, locks it on the last attempt,
    and returns the error message showing which attempt this was."""
    # Add 1 to the count (making the row if it's the first try). An old lock that has
    # run out is treated as a fresh start, so the count goes back to 1.
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

    if attempt >= MAX_LOGIN_ATTEMPTS:                      # That was the last attempt: lock the account.
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
    email = form.get("email", "").strip().lower()          # Read the email box.
    password = form.get("password", "")                    # Read the password box.
    if not email or not password:                          # Empty boxes don't count as an attempt.
        return "Incorrect email or password."
    db = get_db()

    # Is this email locked? If so, stop here without even checking the password.
    attempts = db.execute(
        "SELECT failed_count, locked_until FROM login_attempts WHERE email = ?", (email,)
    ).fetchone()
    now = time.time()
    if attempts is not None and attempts["locked_until"] > now:
        minutes_left = int((attempts["locked_until"] - now) // 60) + 1   # Round up, so it never says 0.
        return (f"Too many failed attempts. This account is locked. "
                f"Try again in {minutes_left} minute{'s' if minutes_left != 1 else ''}.")

    user = db.execute(                                     # Look for a user with that email.
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()                                           # The matching user, or None if there isn't one.

    # Fail if there's no such user OR the password doesn't match the stored hash.
    # The same message is used for both, so attackers can't tell which emails are registered.
    if user is None or not check_password_hash(user["password_hash"], password):
        return record_failed_login(db, email)

    db.execute("DELETE FROM login_attempts WHERE email = ?", (email,))  # Success: start counting from 0 again.
    db.commit()
    session.clear()                                        # Wipe any old session data.
    session["user_id"] = user["id"]                        # Sign them in by saving their id in the session.
    return None                                            # No error.


# ---------- Members-only downloads ----------

# Every file that can be downloaded, by the name used in its /download/<name> URL.
# Only names in this list work, so the URL can never be used to read any other file on the server.
DOWNLOADS = {
    "digital-production-design-development-spec": "digital-production-design-development-spec.pdf",
    "digital-support-services-spec": "digital-support-services-spec.pdf",
    "management-administration-spec": "management-administration-spec.pdf",
    "media-broadcast-production-spec": "media-broadcast-production-spec.pdf",
    "accounting-spec": "accounting-spec.pdf",
    "engineering-manufacturing-processing-control-spec": "engineering-manufacturing-processing-control-spec.pdf",
}


@app.route("/download/<name>")                             # URL: e.g. /download/accounting-spec
@limiter.limit("30 per minute")                            # Stops anyone scraping the files in bulk.
def download(name):
    """Sends a members-only file. Visitors who aren't signed in are sent to the sign-in page,
    and come back to the T Levels page afterwards."""
    if g.user is None:                                     # Not signed in? No file.
        return redirect(url_for("login", next=url_for("t_levels")))
    filename = DOWNLOADS.get(name)                         # Look the name up in the list above.
    if filename is None:                                   # Not in the list?
        abort(404)                                         # Show the normal "page not found" page.
    response = send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)  # as_attachment = download, don't open.
    response.headers["Cache-Control"] = "private, no-store"  # Don't let shared caches keep a members-only copy.
    return response


@app.route("/account.html")
@app.route("/account")                                     # URL: /account
@login_required                                            # Not signed in? Go to the sign-in page first.
def account():
    """Shows the signed-in user's details and a sign-out button."""
    return render_template("account.html")                 # The page reads the details from current_user.


# login.html holds both the sign-in and the sign-up form. The sign-in form posts to
# /login and the sign-up form posts to /register; both show login.html again on error.

@app.route("/login.html", methods=["GET", "POST"])
@app.route("/signin.html")                                 # The nav bar's "Sign in" button links here.
@app.route("/login", methods=["GET", "POST"])              # URL: /login
@limiter.limit("10 per minute", methods=["POST"])          # Slows down anyone guessing passwords.
def login():
    """Sign-in page."""
    if g.user is not None:                                 # Already signed in? Nothing to do here.
        return redirect(url_for("account"))
    error = None                                           # No error to start with.
    if request.method == "POST":                           # Form submitted?
        error = try_login(request.form)                    # Try to sign in.
        if error is None:                                  # It worked:
            next_page = request.args.get("next", "")       # Was the user trying to reach another page first?
            if is_safe_redirect(next_page):                # Only follow it if it stays on this site.
                return redirect(next_page)                 # Send them to the page they wanted.
            return redirect(url_for("account"))            # Otherwise go to the account page.
    return render_template("login.html", login_error=error)  # Show the login page (with any error).


@app.route("/register", methods=["GET", "POST"])           # URL: /register
@limiter.limit("10 per minute", methods=["POST"])          # Stops mass account creation.
def register():
    """Sign-up page (the "Sign up" tab of login.html)."""
    if g.user is not None:                                 # Already signed in? Nothing to do here.
        return redirect(url_for("account"))
    error = None                                           # No error to start with.
    if request.method == "POST":                           # Form submitted?
        error = try_register(request.form)                 # Try to create the account.
        if error is None:                                  # It worked:
            return redirect(url_for("account"))            # Go to the account page.
    return render_template("login.html", register_error=error)  # Show the sign-up tab (with any error).


@app.route("/logout", methods=["POST"])                    # URL: /logout. POST only, so other sites can't sign people out with a link.
def logout():
    """Signs the user out."""
    session.clear()                                        # Forget who was signed in.
    return redirect(url_for("home"))                       # Go back to the home page.


# ---------- AI chat ----------
# The chat widget's API (/api/chat and /api/chat/stream) lives in chat_api.py.
# It's exempt from CSRF because it only accepts JSON, which other websites can't send without our permission.

csrf.exempt(chat_bp)
app.register_blueprint(chat_bp)


# ---------- Error pages ----------

def visitable_pages():
    """Every page a visitor could open directly, e.g. ["/", "/advice", "/faqs", ...]."""
    return sorted({
        rule.rule for rule in app.url_map.iter_rules()
        if "GET" in rule.methods                           # ...that can be visited,
        and not rule.arguments                             # ...has no <variables> in the URL,
        and not rule.rule.endswith(".html")                # ...is the clean URL (not the old .html one),
        and not rule.rule.startswith(("/api", "/static", "/Sources"))  # ...and is a page, not data or files.
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


@app.errorhandler(404)                                     # Runs when a page isn't found.
def page_not_found(e):
    # Only capitals wrong (e.g. "/FAQS")? Send them straight to the real page instead of a 404.
    # GET/HEAD only, because redirecting a submitted form would lose what was typed into it.
    correct = same_page_ignoring_case(request.path)
    if correct and request.method in ("GET", "HEAD"):
        query = request.query_string.decode()              # Keep anything after "?", e.g. "?next=/account".
        return redirect(correct + ("?" + query if query else ""), code=301)  # 301 = moved permanently.

    # Otherwise show the 404 page with the 404 status code, plus a "Did you mean...?" link if one is close.
    return render_template("404.html", suggestion=suggest_page(request.path)), 404


@app.errorhandler(500)                                     # Runs when something crashes on the server.
def server_error(e):
    return render_template("500.html"), 500                # Show the 500 page with the 500 status code.


@app.errorhandler(CSRFError)                               # Runs when a form is missing its CSRF token or it has expired.
def csrf_error(e):
    return ("Your form session expired or was invalid. "
            "Please go back, refresh the page and try again."), 400


@app.errorhandler(429)                                     # Runs when someone hits a rate limit.
def too_many_requests(e):
    return "Too many attempts. Please wait a minute and try again.", 429


@app.errorhandler(413)                                     # Runs when a request is bigger than MAX_CONTENT_LENGTH.
def too_large(e):
    return "That form submission was too large.", 413


# ---------- Run ----------

init_db()                                                  # Make sure the database tables exist before anything else.

if __name__ == "__main__":                                 # Only true when you run "python app.py" directly.
    # Start the Slack bot so its buttons work. In debug mode Flask runs this file twice
    # (once to watch for changes, once to serve); only the serving copy starts the bot.
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_slack_bot()
    app.run(debug=DEBUG)                                 # Start the web server. Debug mode is only on if
                                                           # FLASK_DEBUG=1 is set, so it can't be left on by mistake.
