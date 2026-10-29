# Pippin: Endpoint structures and schemas

Last updated 23 October 2026

This is a quick guide to the routes on the site's backend, so anyone building against it knows what to send and what they'll get back. Most of it is already built. The interest and resources routes at the end aren't yet, so treat those as the plan for now.

## Before you start

There are two types of route. The /api ones take and return JSON. The rest (contact, login, register, logout and account) are normal HTML forms, so they send back a page or a redirect rather than JSON.

Signing in or registering gives you a session cookie, and that's how the site knows who you are. There aren't any API keys for users.

Any POST to a form route needs a CSRF token. You'll find it in the hidden csrf_token field on the page the form is on. Send it back as a form field or in an X-CSRFToken header. Without it you get a 400. The chat routes don't need one.

Form posts are capped at 16 KB and chat requests at 100 KB. Rate limits are per IP address, and if you go over one on a form route you get a 429 and have to wait a minute.

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

Just keep adding each delta onto the reply. The stream ends with {"done": true}, or {"error": "..."} if something went wrong partway through. Anything that goes wrong before it starts comes back as the same JSON errors as /api/chat.

## Session

### GET /api/session

This tells you whether someone's signed in. The nav bar uses it to decide between "Sign in" and "Account". You'll get back {"signed_in": false} or {"signed_in": true, "name": "Alex"}.

## Contact

### POST /contact

This sends a message to the team. It's saved to the database and posted to Slack too, if Slack is set up. You don't need to be signed in.

Send name, email, message and csrf_token, all required. Name can be up to 100 characters, email has to look like a real address, and the message can be up to 2000 characters.

You get the contact page back with either a thank-you or the error message. The only exceptions are a missing token (400) or going over the limit of 5 a minute (429).

## Accounts

### POST /register

This creates an account and signs you straight in. Send name, email, password, confirm_password and csrf_token.

Name can be up to 100 characters. The email has to be valid and not already used. The password needs to be 8 to 128 characters, include a capital letter, a number and a special character (anything that isn't a letter, number or space), and match confirm_password.

If it works you're sent to /account. If not, the page reloads with the error. The limit is 10 a minute.

### POST /login

This signs you in. Send email, password and csrf_token. If it works you're sent to /account, or back to the ?next= page if it's on this site. If it doesn't, you'll see "Incorrect email or password (attempt x out of 3)." That message is the same whichever one is wrong, so it doesn't give away which emails have accounts. After the 3rd wrong attempt that email is locked for 15 minutes, and every sign-in for it is refused (even with the right password) until the lock ends. The limit is 10 a minute.

If you're already signed in, both login and register just send you to /account.

### POST /logout

This signs you out and takes you back to the home page. It needs the csrf_token and only works as a POST.

### GET /account

This shows your name, email and the date you joined. If you're not signed in it sends you to /login first, then back here afterwards.

## Interest (planned)

This part isn't built yet. The idea is to let signed-in users pick which placement areas they want to hear about: digital, business, media, finance or engineering.

GET /api/interest lists what you've signed up for. POST /api/interest adds or updates one. Send route, role (student, parent_carer, teacher_adviser or other), an optional school name of up to 100 characters, and contact_consent set to true. It returns 201 if it's new and 200 if you've updated an existing one, with a limit of 10 a minute. DELETE /api/interest/<route> removes one and returns 204.

You have to be signed in for all of these, or you'll get a 401. POST and DELETE also need the X-CSRFToken header.

## Resources (planned)

This isn't built yet either. It's for downloads like CV templates and placement guides.

GET /api/resources lists everything with a title, description, file type, size and whether it's members only. You can filter it with ?route= and call it 60 times a minute. GET /api/resources/<id>/download gets the file itself, 30 times a minute. Members-only files need you to be signed in (401 if not), and an id that doesn't exist gives a 404.
