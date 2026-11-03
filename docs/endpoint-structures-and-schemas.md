# Pippin: Endpoint structures and schemas

Last updated 3 November 2026

This is a quick guide to the routes on the site's backend, so anyone building against it knows what to send and what they'll get back. Most of it is already built. The resources routes at the end aren't yet, so treat those as the plan for now.

## Before you start

There are two types of route. The /api ones take and return JSON. The rest (contact, interest, login, register, logout, account, analytics and downloads) are normal pages and HTML forms, so they send back a page or a redirect rather than JSON.

Signing in or registering gives you a session cookie, and that's how the site knows who you are. There aren't any API keys for users.

Any POST to a form route needs a CSRF token. You'll find it in the hidden csrf_token field on the page the form is on. Send it back as a form field or in an X-CSRFToken header. Without it you get a 400. The chat routes and /api/track don't need one, because they only accept JSON.

Form posts are capped at 16 KB and chat requests at 100 KB. Rate limits are per IP address. If you go over one on a form route you get a 429 and have to wait a minute. On an /api route the 429 comes back as JSON with a Retry-After header.

Every page has a short URL, such as /faqs or /t-levels. The old file-name addresses, such as /faqs.html or /signin.html, redirect to them with a 301, so old links still work.

## Chat

### POST /api/chat

This sends the conversation to the AI assistant and returns its reply. You don't need to be signed in.

The server doesn't remember anything between requests, so send the whole conversation each time:

    {"messages": [{"role": "user", "content": "What is a T Level?"}]}

You can send between 1 and 20 messages. Each role has to be "user" or "assistant", each message needs some text (4000 characters max), and the last one has to be from the user.

If it works you get {"reply": "..."}. If it doesn't you get {"error": "..."}. That'll be a 400 for a bad request, a 413 if it's too big, or a 429 if you're sending too fast (the Retry-After header tells you how long to wait). A 502, 503 or 504 means the AI side is down, busy, too slow, or the server doesn't have its key set up.

The limit is 10 requests a minute, shared with the streaming route.

### POST /api/chat/stream

This is the same as /api/chat, except the reply comes back bit by bit as it's written, using Server-Sent Events. Each line looks like this:

    data: {"delta": "some text"}

Just keep adding each delta onto the reply. If the reply turns into code, the server sends {"replace": "..."} instead: throw away the text so far and show this (a short refusal), then {"done": true} follows. The stream ends with {"done": true}, or {"error": "..."} if something went wrong partway through. Anything that goes wrong before it starts comes back as the same JSON errors as /api/chat.

## Session and analytics

### GET /api/session

This tells you whether someone's signed in. The nav bar uses it to decide between "Sign in" and "Account". You'll get back {"signed_in": false} or {"signed_in": true, "name": "Alex"}.

### POST /api/track

This records one thing a visitor did, for the analytics page. The site's own scripts call it: the search box sends each search, the T Levels page sends each route tab opened, and the quiz sends its top match. You don't need to be signed in.

    {"kind": "search", "value": "digital jobs"}

kind has to be "search", "view" or "quiz". For a search, value is the text typed in. It's lower-cased with extra spaces removed, and has to be 1 to 100 characters. For a view or a quiz, value has to be one of the five routes: digital, business, media, finance or engineering.

It returns 204 with no body, or a 400 with {"error": "..."} if kind or value isn't allowed. No user id or IP address is stored with the event. The limit is 30 a minute.

### GET /analytics

This is the team's analytics page: enquiries, accounts, searches, route views and quiz results, in total and for the last 7 days. You have to be signed in with an email listed in the ANALYTICS_EMAILS setting. Anyone else who's signed in gets a 404, as if the page didn't exist, and anyone signed out is sent to /login first.

## Contact

### POST /contact

This sends a message to the team. It's saved to the database and posted to Slack too, if Slack is set up. You don't need to be signed in.

Send name, email, message and csrf_token, all required. Name can be up to 100 characters, email has to look like a real address, and the message can be up to 2000 characters.

If it works you're redirected back to /contact, which shows a thank-you once, so refreshing the page can't send the message again. If not, you get the contact page back with an error next to each field that needs fixing. The only exceptions are a missing token (400) or going over the limit of 5 a minute (429).

## Accounts

### POST /register

This creates an account and signs you straight in. Send name, email, password, confirm_password and csrf_token.

Name can be up to 100 characters. The email has to be valid and not already used. The password needs to be 8 to 128 characters, include a capital letter, a number and a special character (anything that isn't a letter, number or space), and match confirm_password.

If it works you're sent to /account, or back to the ?next= page if it's on this site. If not, the page reloads with the error. The limit is 10 a minute.

### POST /login

This signs you in. Send email, password and csrf_token. If it works you're sent to /account, or back to the ?next= page if it's on this site. If it doesn't, you'll see "Incorrect email or password (attempt x out of 3)." That message is the same whichever one is wrong, so it doesn't give away which emails have accounts. After the 3rd wrong attempt that email is locked for 15 minutes, and every sign-in for it is refused (even with the right password) until the lock ends. The limit is 10 a minute.

If you're already signed in, both login and register just send you to /account.

### POST /logout

This signs you out and takes you back to the home page. It needs the csrf_token and only works as a POST.

### GET /account

This shows your name, email and password, each with a "Change" link, the date you joined, your registered interest (with a Remove link), and a link to the analytics page if your email is allowed to see it. If you're not signed in it sends you to /login first, then back here afterwards.

Add ?edit=name, ?edit=email or ?edit=password to open that change form, or ?edit=remove-interest to open the "Remove your interest" confirmation. That's what the "Change" and "Remove" links point to, so they work without JavaScript.

### POST /account/name, /account/email and /account/password

These change one account detail each. You have to be signed in, and every form needs the csrf_token.

- /account/name: send name, up to 100 characters.
- /account/email: send email and current_password. The new email has to be valid and not used by another account.
- /account/password: send current_password, new_password and confirm_password. The new password follows the same rules as when registering. You stay signed in, with a fresh session.

The email and password forms ask for the current password in case someone else is using a computer that was left signed in. If it works you're redirected to /account with a message such as "Your name has been changed." If not, the account page comes back with that form still open and the error, for example "Your current password is incorrect". Any other form name gets a 404. The limit is 10 a minute.

## Downloads

### GET /download/<name>

This downloads one of the T Level course specification PDFs, which are members-only. The name has to be one of the six in the DOWNLOADS list in main.py, for example digital-support-services-spec. Any other name gets a 404, so the URL can't be used to read other files.

If you're signed in you get the PDF as an attachment, marked Cache-Control: private, no-store. If you're not, you're sent to /login and then back to the T Levels page. The limit is 30 a minute.

## Interest

Signed-in users can register interest in one or more placement routes, so the Emerging Talent Programs team can contact them. Each user has at most one interest. Sending it again replaces the earlier answers. Saving, updating or removing it also posts a message to the team's Slack channel. If Slack is down, the answers are still saved.

The answers are:

- role: student, parent_carer, teacher_adviser or other.
- school: optional, up to 100 characters.
- routes: one or more of digital, business, media, finance and engineering.
- year_group: year_10, year_11, year_12, year_13 or not_at_school.
- contact_consent: must be true. Nothing is saved without it.

### GET and POST /interest

This is the Register your interest page, in three steps: About you (role and school), Your interests (routes, year group and consent), then Check and send. ?step=about, ?step=interests or ?step=check picks the step. You can't skip ahead: asking for a later step before the earlier ones are filled in sends you to the first unfinished one. If you're not signed in, you get a page with links to sign in or create an account, and you come back here afterwards.

Each step posts a form with step and go (continue, back or send). Continue checks only that step's answers and keeps them in the session. If something's wrong you get the page back with the errors; otherwise you're redirected to the next step. Back keeps the answers without checking them. Send checks everything again, saves it and redirects to /interest, which shows "Interest registered" or "Details updated" once. The limit is 10 POSTs a minute.

The error messages are "Select who you are", "School or college name must be 100 characters or fewer", "Select at least one placement route", "Select a year group" and "Tick the box to agree to be contacted".

### GET, POST and DELETE /api/interest

The same thing as JSON. GET returns {"interest": null}, or your saved answers plus created_at and updated_at. POST takes {"role", "school", "year_group", "routes": [...], "contact_consent": true}. It returns 201 if it's new and 200 if it replaced your earlier answers, either way with {"interest": {...}}. If anything's wrong you get a 400 with {"errors": {field: message}}, using the messages above. DELETE removes your interest and returns 204, even if there was nothing to remove. POST and DELETE are limited to 10 a minute.

You have to be signed in for all of these, or you'll get a 401 {"error": "Please sign in"}. POST and DELETE also need the X-CSRFToken header, or you'll get a 400.

### Removing interest from the account page

The account page has a "Your interests" section. Its Remove link goes to /account?edit=remove-interest, which opens a confirmation. "Yes, remove it" posts to /account/remove-interest, which deletes the answers and redirects to /account with "Your interest has been removed."

## Resources (planned)

This isn't built yet either. It would replace the fixed list behind /download/<name> once there are more downloads, like CV templates and placement guides, and some of them are public.

GET /api/resources lists everything with a title, description, file type, size and whether it's members only. You can filter it with ?route= and call it 60 times a minute. GET /api/resources/<id>/download gets the file itself, 30 times a minute. Members-only files need you to be signed in (401 if not), and an id that doesn't exist gives a 404.
