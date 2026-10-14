# =====================================================================
# app.py - the Flask backend for the T-Levels website.
# It serves the 10 HTML pages, stores user accounts and contact
# messages in a SQLite database, and handles signing in and out.
# =====================================================================

import os          # Lets us work with file paths and read environment variables.
import re          # Regular expressions, used to check that an email looks valid.
import secrets     # Makes secure random values (used for a fallback secret key).
import sqlite3     # Python's built-in library for SQLite databases (a database stored in one file).
from functools import wraps  # Helper used when writing decorators, keeps the original function's name.
from urllib.parse import urlparse  # Splits a URL into parts so we can check where a redirect goes.

# Flask tools used in this file:
#   Flask           - the class that creates the web app
#   g               - a temporary storage area that lasts for one request (we keep the database connection and user in it)
#   redirect        - sends the browser to a different URL
#   render_template - loads an HTML file from the "templates" folder and fills in any {{ }} values
#   request         - holds everything about the incoming request (form data, method, URL)
#   session         - a secure cookie that remembers who is signed in between pages
#   url_for         - builds a URL from a function name, e.g. url_for("home") gives "/"
from flask import Flask, g, redirect, render_template, request, session, url_for

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

# The folder this file lives in, so the database is always created next to app.py
# no matter which folder you run the program from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Full path to the database file, e.g. ".../tlevels-site/site.db".
DATABASE = os.path.join(BASE_DIR, "site.db")

# Debug mode is only switched on if the FLASK_DEBUG environment variable is "1".
# This way it can't accidentally be left on when the site goes live.
DEBUG = os.environ.get("FLASK_DEBUG") == "1"

# Limits on how long each form field can be, so nobody can post huge amounts of text.
MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254          # The longest a real email address can be.
MAX_MESSAGE_LENGTH = 2000
MAX_PASSWORD_LENGTH = 128

# A simple pattern for an email: some text, an @, some text, a dot, some text, no spaces.
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Create the Flask web application. __name__ tells Flask where to find
# the "templates" and "static" folders (next to this file).
app = Flask(__name__)

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

# Cookie settings:
#   SAMESITE "Lax" - the browser won't send our cookie with forms submitted from other websites.
#   SECURE         - only send the cookie over HTTPS. Turned on when not in debug mode,
#                    because local testing usually uses plain http://.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = not DEBUG

# Reject any request bigger than 16 KB. Our forms are tiny, so this only stops abuse.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

# Turn on CSRF protection for every POST form in the app.
csrf = CSRFProtect(app)

# Rate limiter: counts requests per IP address, stored in memory.
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")


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
    (Not used at the moment, because the account page now shows sign in / sign up itself,
    but it's here if you want to protect another page later.)"""
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

@app.route("/")                                 # When someone visits the home URL "/"...
def home():
    return render_template("index.html")        # ...show the home page.


@app.route("/accessibility")                    # URL: /accessibility
def accessibility():
    return render_template("accessibility.html")  # Show the accessibility page.


@app.route("/faqs")                             # URL: /faqs
def faqs():
    return render_template("faqs.html")         # Show the FAQs page.


@app.route("/t-levels")                         # URL: /t-levels
def t_levels():
    return render_template("t-levels.html")     # Show the T-Levels page.


# ---------- Contact ----------

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
    if len(password) < 8:                                  # Password too short?
        return "Password must be at least 8 characters."
    if len(password) > MAX_PASSWORD_LENGTH:                # Password too long?
        return f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
    if password != confirm:                                # The two passwords don't match?
        return "Passwords do not match."

    db = get_db()                                          # Get the database connection.
    try:                                                   # Try to add the user...
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),  # Store the scrambled password, never the real one.
        )
        db.commit()                                        # Save the new user.
    except sqlite3.IntegrityError:                         # This error happens if the email is already taken (UNIQUE rule).
        return "An account with that email already exists. Please sign in instead."

    session.clear()                                        # Wipe any old session data.
    session["user_id"] = cur.lastrowid                     # Sign the new user in by saving their id in the session.
    return None                                            # None means "no error, it worked".


def try_login(form):
    """Signs a user in. Returns an error message, or None if it worked."""
    email = form.get("email", "").strip().lower()          # Read the email box.
    password = form.get("password", "")                    # Read the password box.

    user = get_db().execute(                               # Look for a user with that email.
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()                                           # The matching user, or None if there isn't one.

    # Fail if there's no such user OR the password doesn't match the stored hash.
    # The same message is used for both, so attackers can't tell which emails are registered.
    if user is None or not check_password_hash(user["password_hash"], password):
        return "Incorrect email or password."

    session.clear()                                        # Wipe any old session data.
    session["user_id"] = user["id"]                        # Sign them in by saving their id in the session.
    return None                                            # No error.


@app.route("/account", methods=["GET", "POST"])            # URL: /account (view the page or submit a form).
@limiter.limit("10 per minute", methods=["POST"])          # Slows down anyone guessing passwords.
def account():
    """Signed in: shows account details.
    Not signed in: shows a sign-in form and a sign-up form."""
    login_error = None                                     # Error message for the sign-in form (if any).
    register_error = None                                  # Error message for the sign-up form (if any).

    # Only handle a form if one was submitted AND nobody is signed in yet.
    if request.method == "POST" and g.user is None:
        action = request.form.get("action")                # The hidden field says which form was used.
        if action == "login":                              # The sign-in form was submitted...
            login_error = try_login(request.form)          # ...try to sign in.
        elif action == "register":                         # The sign-up form was submitted...
            register_error = try_register(request.form)    # ...try to create the account.
        else:                                              # The hidden field was missing or changed...
            login_error = "Something went wrong with the form. Please try again."
        if login_error is None and register_error is None: # If neither failed...
            return redirect(url_for("account"))            # ...reload the page, which now shows their details.

    # Show the account page. The HTML decides what to show using {% if current_user %}.
    return render_template(
        "account.html",
        login_error=login_error,                           # Pass any sign-in error to the page.
        register_error=register_error,                     # Pass any sign-up error to the page.
    )


@app.route("/login", methods=["GET", "POST"])              # URL: /login (separate sign-in page).
@limiter.limit("10 per minute", methods=["POST"])          # Slows down anyone guessing passwords.
def login():
    """Separate sign-in page."""
    error = None                                           # No error to start with.
    if request.method == "POST":                           # Form submitted?
        error = try_login(request.form)                    # Try to sign in.
        if error is None:                                  # It worked:
            next_page = request.args.get("next", "")       # Was the user trying to reach another page first?
            if is_safe_redirect(next_page):                # Only follow it if it stays on this site.
                return redirect(next_page)                 # Send them to the page they wanted.
            return redirect(url_for("account"))            # Otherwise go to the account page.
    return render_template("login.html", error=error)      # Show the login page (with any error).


@app.route("/register", methods=["GET", "POST"])           # URL: /register (separate sign-up page).
@limiter.limit("10 per minute", methods=["POST"])          # Stops mass account creation.
def register():
    """Separate sign-up page."""
    error = None                                           # No error to start with.
    if request.method == "POST":                           # Form submitted?
        error = try_register(request.form)                 # Try to create the account.
        if error is None:                                  # It worked:
            return redirect(url_for("account"))            # Go to the account page.
    return render_template("register.html", error=error)   # Show the register page (with any error).


@app.route("/logout", methods=["POST"])                    # URL: /logout. POST only, so other sites can't sign people out with a link.
def logout():
    """Signs the user out."""
    session.clear()                                        # Forget who was signed in.
    return redirect(url_for("home"))                       # Go back to the home page.


# ---------- Error pages ----------

@app.errorhandler(404)                                     # Runs when a page isn't found.
def page_not_found(e):
    return render_template("404.html"), 404                # Show the 404 page with the 404 status code.


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
    app.run(debug=DEBUG)                                   # Start the web server. Debug mode is only on if
                                                           # FLASK_DEBUG=1 is set, so it can't be left on by mistake.
