# Data Requirements

This document lists every piece of data T Level placements at Amazon collects, stores or passes on, as the site is built. For each one it gives the type, how it is checked, why we need it, who can see it, how long it is kept and how it is deleted. The tables themselves are in [SQL Schema](https://pippin.amazon.dev/docs/YBfDIemlaMLqvt), and the visitor-facing version of this is the site's Privacy page (`/privacy`).

We collect only what a feature needs. Names, email addresses and interest answers are the only personal data the site asks for. Everything else is either anonymous or kept in the visitor's own browser.

## Where data is kept

- **Our database** (`site.db`, SQLite, on the AWS server): accounts, contact messages, registered interest, wrong-password records and site statistics.
- **The team's Slack channel**: a copy of each contact message, and of each new, updated or removed interest.
- **The visitor's browser**: the `session` cookie and the accessibility settings.
- **Not kept anywhere**: chat messages. They are passed to OpenRouter and NVIDIA to get a reply, and nobody stores them.

All limits below are checked in `main.py` before anything is saved, because SQLite doesn't enforce text lengths. The sign-up, sign-in, account and contact forms repeat the same checks in the browser (`auth.js`) with the same messages. Every form needs a CSRF token, and requests over 16 KB are refused.

## Accounts (`users` table)

| Field | Type | Validation | Why we need it |
|-|-|-|-|
| `id` | Integer, primary key | Set by the database | Links the account to its interest and keeps the user signed in |
| `name` | Text | Required, up to 100 characters, spaces trimmed | Shown on the account page, and sent to the team with registered interest so they know who to contact |
| `email` | Text, unique | Required, up to 254 characters, must look like `name@example.com`, stored in lower case, only one account per email | What the user signs in with, and how the team contacts them |
| `password_hash` | Text | Password must be 8 to 128 characters with a capital letter, a number and a special character, typed twice. Only the hash is stored (`pbkdf2:sha256`) | Checks the password at sign-in without storing the password itself |
| `created_at` | Timestamp (UTC) | Set by the database | Counts new accounts on the analytics page |

- **Who can see it**: the user, on their account page. The team, in Slack, sees the name and email of anyone who registers, updates or removes interest. People listed in `ANALYTICS_EMAILS` see only the number of accounts. Anyone with access to the server can read the database. Nobody can see a password, because only its hash is stored.
- **How long it's kept**: until the user deletes the account.
- **How it's deleted**: the user selects "Delete" under Your details on the account page and types their current password. The account, its interest and any wrong-password record for its email are removed straight away (`try_delete_account()`). The user can also change their name, email or password there; changing the email or password needs the current password.

## Contact messages (`messages` table)

| Field | Type | Validation | Why we need it |
|-|-|-|-|
| `id` | Integer, primary key | Set by the database | Identifies the message |
| `name` | Text | Required, up to 100 characters, spaces trimmed | So the team knows who wrote |
| `email` | Text | Required, up to 254 characters, valid format, stored in lower case | So the team can reply |
| `message` | Text | Required, up to 2000 characters, spaces trimmed | The question itself |
| `created_at` | Timestamp (UTC) | Set by the database | Counts enquiries on the analytics page |

- **Who can see it**: the team, in the Slack channel, where each message is posted with Mark Handled, Priority, Reply Needed and View JSON buttons. Anyone with access to the server. People listed in `ANALYTICS_EMAILS` see only the number of messages.
- **How long it's kept**: there is no time limit. Messages are kept so the team has a record of what was asked. They aren't linked to an account, so deleting an account doesn't remove them.
- **How it's deleted**: the sender asks through the contact form, and someone with server access deletes the row by hand. The Slack copy stays until the team deletes it in Slack.
- The contact form is limited to 5 messages a minute per IP address.

## Registered interest (`interests` and `interest_routes` tables)

Only signed-in users can register interest, so the name and email come from their account. Each user has at most one set of answers; sending again replaces them.

| Field | Type | Validation | Why we need it |
|-|-|-|-|
| `interests.user_id` | Integer, primary key, refers to `users.id` | The signed-in user | Links the answers to the account |
| `role` | Text | Required, one of `student`, `parent_carer`, `teacher_adviser`, `other` | The team talks to students, parents and teachers differently |
| `school` | Text | Optional, up to 100 characters, spaces trimmed | Lets the team see which schools and colleges are interested |
| `year_group` | Text | Required, one of `year_10`, `year_11`, `year_12`, `year_13`, `not_at_school` | Placements happen in Years 12 and 13, so this shows when the person could take one |
| `contact_consent` | Integer | Must be ticked (never pre-ticked); always stored as 1 | Our lawful basis for contacting them. Nothing is saved without it |
| `created_at`, `updated_at` | Timestamp (UTC) | Set by the database | Shows when the answers were first given and last changed |
| `interest_routes.user_id` | Integer, refers to `users.id` | The signed-in user | Links each route to the account |
| `interest_routes.route` | Text | At least one, each one of `digital`, `business`, `media`, `finance`, `engineering` | Which T Level placement routes they want to hear about |

- **Who can see it**: the user, on their account page and on the Check step. The team, in the Slack channel, with the user's name and email. Anyone with access to the server.
- **How long it's kept**: until the user removes it or deletes their account.
- **How it's deleted**: "Remove your interest" on the account page, then "Yes, remove it" (`remove_interest()` deletes from both tables). Deleting the account does the same. Either way the team gets a Slack message saying the interest was removed, so they know to stop contacting the person. Earlier Slack messages stay in the channel until the team deletes them.
- While the user is filling in the three steps, the answers so far are kept in their `session` cookie (`interest_draft`), not the database. They are cleared when the answers are saved or removed.

## Wrong-password records (`login_attempts` table)

| Field | Type | Validation | Why we need it |
|-|-|-|-|
| `email` | Text, primary key | The email typed into the sign-in form, lower-cased, up to 254 characters | Counts wrong passwords per email, whether or not it has an account |
| `failed_count` | Integer | 1 to 3 | After 3 wrong passwords in a row, sign-in for that email is locked |
| `locked_until` | Number (Unix time) | 0 when not locked, otherwise 15 minutes after the 3rd wrong password | When the lock ends |

- **Why**: stops someone guessing passwords. The lock is timed rather than permanent, so nobody can lock a real user out for good just by knowing their email.
- **Who can see it**: nobody through the site. The person signing in is told which attempt this was, or how many minutes are left on a lock. Anyone with access to the server.
- **How long it's kept**: until the email signs in successfully, an account is created or changed to use that email, or the account is deleted. A record whose lock has run out is deleted on the next wrong password by anyone.
- Sign-in and sign-up are also limited to 10 attempts a minute per IP address.

## Site statistics (`analytics_events` table)

| Field | Type | Validation | Why we need it |
|-|-|-|-|
| `id` | Integer, primary key | Set by the database | Identifies the event |
| `kind` | Text | One of `search`, `view` (a route tab opened on the T Levels page, once per visit) or `quiz` (the quiz's top match) | Says what happened |
| `value` | Text | For `search`, 1 to 100 characters, lower-cased with extra spaces removed. For `view` and `quiz`, one of the five route names | What was searched for, or which route |
| `created_at` | Timestamp (UTC) | Set by the database | Shows totals for the last 7 days |

- **Why**: shows the team which routes interest visitors and what they look for, so the content can be improved.
- **Who can see it**: signed-in users whose email is in `ANALYTICS_EMAILS`, on `/analytics`, as totals and the 10 most common searches. Everyone else gets a 404.
- **What it doesn't contain**: no user id, IP address, cookie or account. A search could contain personal details if a visitor types them into the search box.
- **How long it's kept**: indefinitely, because it holds no personal details.
- `/api/track` accepts 30 events a minute per IP address, so the counts can't be flooded.

## The `session` cookie

- **What it holds**: the signed-in `user_id`, whether "Keep me signed in" was ticked, the time of the last request, the interest answers in progress, and one-off confirmations after sending the contact form or interest. It is signed with `SECRET_KEY`, so it can't be changed in the browser, and it is `SameSite=Lax` (and `Secure` over HTTPS).
- **Why**: keeps the user signed in and protects forms against cross-site requests. It is strictly necessary, so the site doesn't ask for cookie consent.
- **How long it's kept**: until the browser is closed, or 30 days with "Keep me signed in". Without it, the user is also signed out after 30 minutes without a request. Signing out clears it.

## Accessibility settings (browser local storage)

- **What**: text size, theme and reading aids, under `tlc-theme` and `tlc-a11y`.
- **Why**: so the visitor's settings apply on every page and next visit.
- **Who can see it**: only the visitor's browser. It is never sent to us.
- **How it's deleted**: the reset button in the accessibility menu, or clearing the browser's site data.

## Chat messages (not stored)

- **What**: up to 20 messages per request, each up to 4000 characters, with role `user` or `assistant`.
- **Where it goes**: our server adds the instructions and site information and sends the conversation to OpenRouter, which passes it to NVIDIA's model. The production model uses zero data retention, so neither keeps the messages or uses them for training. The API key stays on the server.
- **Who can see it**: nobody keeps it. The conversation is in the visitor's page only, and is cleared when they reload or leave.
- The widget asks visitors not to share personal details. It is limited to 10 requests a minute per IP address.

## Site content

T Level and placement information (route descriptions, advice, FAQs, the quiz) is written into the page templates in `frontend/Template/`, not stored in the database. The T Level specification PDFs are in `resources/specs/` and can only be downloaded by signed-in users, through `/download/<name>`. The chat assistant answers from `chat_knowledge.md`, a hand-kept copy of the page text.

## Feedback data

Feedback from user testing (ratings, comments and suggestions) is collected outside the site, in testing sessions and anonymous Microsoft Forms surveys, as set out in the [Feedback Plan](https://pippin.amazon.dev/docs/ocx3dYZynKgXHL). The site has no feedback form and stores no feedback.

## Data security and protection

We follow UK GDPR and the Data Protection Act 2018:

- **Data minimisation**: only the fields above are collected. The school is optional, and statistics carry no personal details.
- **Lawful basis**: accounts and contact messages are needed to provide what the user asked for. Registered interest is only stored with the user's consent, which they can withdraw by removing it.
- **Users' rights**: users can see, change and delete their own data on the account page. Anything else is handled through the contact form.
- **Protection**: passwords are hashed, every query uses `?` placeholders against SQL injection, forms have CSRF tokens, sign-in has a lockout and rate limits, the analytics page is limited to named accounts, and the Content Security Policy only allows scripts, styles and fonts from the site itself.
- **Third parties**: Slack (contact messages and interest), OpenRouter and NVIDIA (chat, not kept) and AWS (hosting). Nobody else receives data.
