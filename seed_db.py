"""Fills site.db with made-up data for local testing: accounts, contact messages, registered
interest and analytics events spread over the last 14 days, so every part of /analytics has
something to show.

    .venv/bin/python seed_db.py           # back up site.db, then add the test data
    .venv/bin/python seed_db.py --reset   # remove the seeded accounts, messages and interest

Seeded accounts and messages use @seed.example.com emails, which is how --reset finds them.
Analytics events have no owner column, so --reset leaves them; restore site.db.bak to undo those.
Every seeded account's password is Passw0rd!
"""
import os
import random
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# Importing main without SECRET_KEY would write a new key into .env.
os.environ.setdefault("SECRET_KEY", "seed")
import main  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

SEED_DOMAIN = "seed.example.com"
PASSWORD = "Passw0rd!"

FIRST_NAMES = ["Amira", "Ben", "Chloe", "Dev", "Ella", "Finn", "Grace", "Harvey", "Isla", "Jay",
               "Kiran", "Lily", "Mason", "Nia", "Oscar", "Priya", "Reece", "Sofia", "Tom", "Zara"]
LAST_NAMES = ["Ahmed", "Brown", "Clarke", "Davies", "Evans", "Hughes", "Khan", "Patel", "Price",
              "Roberts", "Shah", "Taylor", "Walker", "Williams"]
SCHOOLS = ["City of Bristol College", "SGS College", "Bristol Metropolitan Academy",
           "Bristol Technology and Engineering Academy", "Weston College", "Cotham School",
           "Bridgwater and Taunton College", ""]
MESSAGES = [
    "Hi, does the placement have to be in Bristol or can it be remote?",
    "My son is in Year 11 and interested in the Digital T Level. How does he apply?",
    "Are the placements paid? I couldn't find it on the FAQs page.",
    "I'm a careers adviser and would like to share this with our Year 12s. Is there a leaflet?",
    "What hours would I work during the 45 days?",
    "Can I do a placement if I'm studying the Engineering T Level at a college outside Bristol?",
    "Is there an age limit for placements?",
    "The quiz said Media suits me but I'm not sure. Who can I talk to?",
]
SEARCHES = ["digital", "placement", "how to apply", "pay", "engineering", "finance", "media",
            "year 12", "faqs", "contact", "business", "t level", "hours", "remote", "quiz"]
# Weighting so the charts aren't flat.
ROUTE_WEIGHTS = {"digital": 5, "engineering": 3, "business": 2, "finance": 2, "media": 1}


def timestamp(days_ago_max=14):
    moment = datetime.now(timezone.utc) - timedelta(
        days=random.uniform(0, days_ago_max), minutes=random.randint(0, 59))
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def weighted_route():
    return random.choices(list(ROUTE_WEIGHTS), weights=list(ROUTE_WEIGHTS.values()))[0]


def seed(db):
    password_hash = generate_password_hash(PASSWORD, method="pbkdf2:sha256")
    roles = [key for key, _ in main.INTEREST_ROLES]
    years = [key for key, _ in main.YEAR_GROUPS]
    users = 0

    for i in range(30):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        email = f"{name.lower().replace(' ', '.')}{i}@{SEED_DOMAIN}"
        created = timestamp()
        cursor = db.execute(
            "INSERT OR IGNORE INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, password_hash, created),
        )
        if not cursor.rowcount:
            continue
        users += 1
        user_id = cursor.lastrowid

        # About two thirds register interest.
        if random.random() < 0.66:
            role = random.choices(roles, weights=[6, 2, 2, 1])[0]
            year = random.choice(years[:4]) if role == "student" else random.choice(years)
            db.execute(
                "INSERT INTO interests (user_id, role, school, year_group, contact_consent, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 1, ?, ?)",
                (user_id, role, random.choice(SCHOOLS), year, created, created),
            )
            for route in {weighted_route() for _ in range(random.randint(1, 3))}:
                db.execute("INSERT INTO interest_routes (user_id, route) VALUES (?, ?)", (user_id, route))

    for text in MESSAGES:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        db.execute(
            "INSERT INTO messages (name, email, message, created_at) VALUES (?, ?, ?, ?)",
            (name, f"{name.lower().replace(' ', '.')}@{SEED_DOMAIN}", text, timestamp()),
        )

    events = []
    for _ in range(250):
        events.append(("view", weighted_route(), timestamp()))
    for _ in range(60):
        events.append(("quiz", weighted_route(), timestamp()))
    for _ in range(80):
        events.append(("search", random.choice(SEARCHES), timestamp()))
    db.executemany("INSERT INTO analytics_events (kind, value, created_at) VALUES (?, ?, ?)", events)

    return users, len(MESSAGES), len(events)


def reset(db):
    seeded = "SELECT id FROM users WHERE email LIKE ?"
    pattern = f"%@{SEED_DOMAIN}"
    db.execute(f"DELETE FROM interest_routes WHERE user_id IN ({seeded})", (pattern,))
    db.execute(f"DELETE FROM interests WHERE user_id IN ({seeded})", (pattern,))
    users = db.execute("DELETE FROM users WHERE email LIKE ?", (pattern,)).rowcount
    messages = db.execute("DELETE FROM messages WHERE email LIKE ?", (pattern,)).rowcount
    return users, messages


if __name__ == "__main__":
    main.init_db()
    db = sqlite3.connect(main.DATABASE)
    if "--reset" in sys.argv:
        users, messages = reset(db)
        print(f"Removed {users} seeded accounts and {messages} seeded messages.")
    else:
        shutil.copyfile(main.DATABASE, main.DATABASE + ".bak")
        random.seed(42)
        users, messages, events = seed(db)
        print(f"Backed up to {os.path.basename(main.DATABASE)}.bak. Added {users} accounts, "
              f"{messages} messages and {events} analytics events. Password for all: {PASSWORD}")
    db.commit()
    db.close()
