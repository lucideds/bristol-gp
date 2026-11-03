# Pippin: Algorithm designs

Last updated 3 November 2026. Owners: Shea Palin and Leeam.

This is Brief Task 1, Activity B. It sets out five of the more complex problems on the site as pseudocode. Designs 1, 2, 3 and 5 match the code as it is now (main.py, chat_api.py, extensions.py, bot/bot.py and topNavBar.js). Design 4 is partly built: the members-only spec downloads work, and the fuller resources design is still the plan.

Pseudocode conventions: <- means assignment, and blocks close with END IF, END FOR and so on. RETURN ends the algorithm. RESPOND sends an HTTP status and body back to the browser. Text in quotes is the message the user sees.

## 1. Register and login validation

Problem: create accounts and sign people in safely. Bad input is rejected with a clear message, passwords are never stored as plain text, a failed sign-in doesn't reveal which emails are registered, repeated wrong passwords lock that email for a while, and users are only sent back to pages on this site. Inputs: the form fields and CSRF token. Outputs: a signed-in session and a redirect, or the form again with one error.

    CONSTANTS MAX_NAME <- 100, MAX_EMAIL <- 254, MIN_PW <- 8, MAX_PW <- 128,
              MAX_ATTEMPTS <- 3, LOCK_MINUTES <- 15

    FUNCTION Register(form, nextPage)
        IF CSRF token missing or invalid THEN
            RESPOND 400 "Your form session expired or was invalid. Please go back, refresh the page and try again."
        END IF
        IF more than 10 attempts from this IP in the last minute THEN
            RESPOND 429 "Too many attempts. Please wait a minute and try again."
        END IF
        name <- TRIM(form.name)
        email <- LOWERCASE(TRIM(form.email))
        password <- form.password            // not trimmed, spaces may be deliberate
        IF name = "" THEN RETURN "Enter your name"
        IF LENGTH(name) > MAX_NAME THEN RETURN "Name must be 100 characters or fewer"
        IF email = "" THEN RETURN "Enter your email address"
        IF LENGTH(email) > MAX_EMAIL OR email does not match "text@text.text" (no spaces) THEN
            RETURN "Enter an email address in the correct format, like name@example.com"
        END IF
        IF password = "" THEN RETURN "Enter your password"
        IF LENGTH(password) < MIN_PW THEN RETURN "Password must be at least 8 characters"
        IF LENGTH(password) > MAX_PW THEN RETURN "Password must be 128 characters or fewer"
        IF password has no capital letter THEN RETURN "Password must include a capital letter"
        IF password has no number THEN RETURN "Password must include a number"
        IF password has no special character THEN
            RETURN "Password must include a special character, such as ! ? # or @"
        END IF
        IF form.confirm_password = "" THEN RETURN "Type your password again"
        IF password <> form.confirm_password THEN RETURN "Passwords do not match"
        hash <- PBKDF2_SHA256(password)      // salted, never store the real password
        TRY
            userId <- INSERT INTO users (name, email, hash)
        CATCH unique-email error
            RETURN "An account with that email already exists. Please sign in instead."
        END TRY
        CLEAR session                        // stops an old session being reused
        session.user_id <- userId
        GoToNextOrAccount(nextPage)
    END FUNCTION

    FUNCTION Login(form, nextPage)
        (same CSRF and rate-limit checks as Register)
        email <- LOWERCASE(TRIM(form.email))
        password <- form.password
        IF email = "" OR password = "" OR LENGTH(email) > MAX_EMAIL THEN
            RETURN "Incorrect email or password."         // doesn't count as an attempt
        END IF
        attempts <- SELECT FROM login_attempts WHERE email = email
        IF attempts <> NULL AND attempts.locked_until > now THEN
            minutesLeft <- whole minutes left on the lock, rounded up
            RETURN "Too many failed attempts. This account is locked. Try again in minutesLeft minutes."
        END IF                               // the password isn't even checked while locked
        user <- SELECT * FROM users WHERE email = email
        IF user = NULL OR NOT CheckHash(user.hash, password) THEN
            RETURN RecordFailedLogin(email)
        END IF
        DELETE FROM login_attempts WHERE email = email    // a good sign-in resets the count
        CLEAR session
        session.user_id <- user.id
        GoToNextOrAccount(nextPage)
    END FUNCTION

    FUNCTION RecordFailedLogin(email)
        DELETE FROM login_attempts WHERE the lock has run out   // so the table doesn't keep growing
        attempt <- this email's failed count + 1 (saved, starting at 1 if there's no row)
        IF attempt >= MAX_ATTEMPTS THEN
            SET this email's locked_until <- now + LOCK_MINUTES
            RETURN "Incorrect email or password (attempt 3 out of 3). This account is now locked for 15 minutes."
        END IF
        RETURN "Incorrect email or password (attempt " + attempt + " out of 3)."
    END FUNCTION

    FUNCTION GoToNextOrAccount(nextPage)
        IF IsSafeRedirect(nextPage) THEN REDIRECT to nextPage ELSE REDIRECT to /account
    END FUNCTION

    FUNCTION IsSafeRedirect(target)
        IF target = "" OR target does not start with "/" THEN RETURN FALSE
        target <- REPLACE "\" WITH "/" IN target       // browsers treat them the same
        parts <- PARSE_URL(target)
        RETURN parts.scheme = "" AND parts.domain = ""  // a path on this site only
    END FUNCTION

Attempts are counted by the email typed in, not by account, so an email with no account counts and locks exactly like a real one. That way the messages never show which emails are registered. The lock is timed rather than permanent because there is no password reset yet, and a permanent lock would let anyone lock a real user out just by knowing their email.

Test data: "Bob@X.com " gets stored as "bob@x.com". A 7-character password gets "Password must be at least 8 characters". Registering the same email twice gives the "already exists" message. A wrong password and an unknown email give the same message. Three wrong passwords give attempt 1, attempt 2, then the locked message, and a 4th try with the right password is still refused until the 15 minutes are up. A next value of "//evil.com" or "/\evil.com" goes to /account instead.

## 2. Chatbot request flow

Problem: pass a visitor's conversation to the AI model (OpenRouter) and stream the reply back, keeping the API key secret, stopping overload and misuse, stopping visitors overriding the assistant's instructions, and never showing the model's hidden reasoning. Inputs: JSON {messages: [{role, content}, ...]}. Outputs: a stream of {delta}, then {done} or {error}. A reply that turns into code gets {replace: CODE_REFUSAL} then {done}.

    CONSTANTS LIMIT <- 10 per minute, MAX_BODY <- 100 KB, MAX_MSGS <- 20,
              MAX_CHARS <- 4000, MAX_STREAM_SECONDS <- 120

    FUNCTION ChatStream(request)
        // 1. Rate limit (Flask-Limiter, per IP address, one count shared with /api/chat)
        IF this IP has already made LIMIT chat requests this minute THEN
            RESPOND 429 "You're sending messages too quickly. Please wait a moment and try again." + Retry-After
        END IF

        // 2. Size and shape
        IF request.size > MAX_BODY THEN RESPOND 413 "Your message is too long."
        messages <- PARSE_JSON(request.body)
        IF messages is not a list of 1 to MAX_MSGS items THEN RESPOND 400
        clean <- empty list
        FOR EACH m IN messages
            IF m.role NOT IN ("user", "assistant") THEN RESPOND 400   // no "system" messages
            text <- TRIM(m.content)
            IF text = "" OR LENGTH(text) > MAX_CHARS THEN RESPOND 400
            IF m.role = "assistant" AND LooksLikeCode(text) THEN text <- CODE_REFUSAL
                                            // the browser sends the history, so it may be made up
            APPEND {role: m.role, content: text} TO clean               // extra fields dropped
        END FOR
        IF LAST(clean).role <> "user" THEN RESPOND 400

        // 3. Call the model
        IF API key not set THEN RESPOND 503 "The chat assistant is not available: API key not configured."
        body <- {model, [RULES + <reference_information>site facts</reference_information> + REMINDER] + clean,
                 max_tokens 4096, temperature 0.2,
                 reasoning {effort low, exclude}, stream TRUE}
        TRY
            upstream <- POST body TO OpenRouter (connect timeout 5 s, read timeout 90 s)
        CATCH timeout: RESPOND 504 "The assistant took too long to reply."
        CATCH connection error: RESPOND 502 "Couldn't reach the assistant service."
        END TRY
        IF upstream.status = 429 THEN RESPOND 503 "The assistant is busy right now."
        IF upstream.status is not 2xx THEN RESPOND 502 "The assistant is temporarily unavailable."
                                            // details go to the server log only

        // 4. Relay the stream
        START event stream to browser
        started <- FALSE, finished <- FALSE, reply <- "", deadline <- now + MAX_STREAM_SECONDS
        TRY
            FOR EACH line IN upstream (decoded as UTF-8)
                IF now > deadline THEN SEND {error: "took too long"}; STOP
                IF line is blank or a comment THEN CONTINUE
                IF line = "data: [DONE]" THEN finished <- TRUE; EXIT FOR
                chunk <- PARSE_JSON(line) (if this fails, CONTINUE)
                IF chunk has error THEN SEND {error: "temporarily unavailable"}; STOP
                text <- chunk.choices[0].delta.content    // reasoning is never read
                IF text <> "" THEN
                    IF NOT started THEN text <- TRIM_START(text)
                    IF text <> "" THEN
                        started <- TRUE
                        reply <- reply + text
                        IF LooksLikeCode(reply) THEN SEND {replace: CODE_REFUSAL}; SEND {done: TRUE}; STOP
                        SEND {delta: text}
                    END IF
                END IF
                IF chunk.finish_reason = "error" THEN SEND {error: "temporarily unavailable"}; STOP
                IF chunk has finish_reason THEN finished <- TRUE
            END FOR
        CATCH connection dropped
            SEND {error: "reply was interrupted"}; STOP
        FINALLY
            close upstream connection          // even if the visitor has left
        END TRY
        IF NOT started THEN SEND {error: "couldn't come up with a reply"}
        ELSE IF NOT finished THEN SEND {error: "reply was interrupted"}
        ELSE SEND {done: TRUE}
    END FUNCTION

    FUNCTION LooksLikeCode(text)
        IF text contains "```" THEN RETURN TRUE
        IF TRIM_START(text) starts with "{" or "[" THEN RETURN TRUE      // JSON; prose never does
        IF any line starts like code (def, class ...:, import, print(, console.log(, function,
           const/let/var, name = value, #include, <script, SELECT ... FROM, for/if/while ...:,
           return, a lone { or }) THEN RETURN TRUE                        // case-sensitive
        RETURN FALSE
    END FUNCTION

RULES limits the assistant to T Levels, Amazon placements, careers and the site, and to plain English sentences in its own voice: no code, JSON, tables, poems, songs, stories, characters or other languages, and no changing the rules whoever the visitor claims to be. REMINDER repeats this after the site facts. The site facts come from chat_knowledge.md, a hand-kept copy of the site's page text that is added to the system prompt when the server starts. The browser tries the stream first and falls back to /api/chat if streaming fails. Test data: an 11th request within a minute gets a 429. A message with role "system" gets a 400. A conversation ending on an assistant message gets a 400. If the connection drops mid-reply, the visitor sees "interrupted", not half an answer. "Can you explain the Engineering route as a Python script?" gets a one-sentence refusal, and if the model writes code anyway the server swaps it for CODE_REFUSAL. "Do I need to know Python for the Digital T Level?" still gets a normal answer.

## 3. Expression of interest submission

Problem: let a signed-in user register interest in one or more placement routes, change it later without creating duplicates, and remove it. It should only store what's needed, only when the user has agreed to be contacted, and tell the team in Slack. The /interest page (three steps of plain form posts) and /api/interest (JSON) share the checks and the save. Inputs: role, school (optional), routes, year group and consent, plus the CSRF token. Outputs: the next step or a thank-you (page), 201 or 200 (API), or the errors for each field.

    CONSTANTS ROUTES <- (digital, business, media, finance, engineering)
              ROLES  <- (student, parent_carer, teacher_adviser, other)
              YEARS  <- (year_10, year_11, year_12, year_13, not_at_school), MAX_SCHOOL <- 100
              STEP_FIELDS <- {about: (role, school), interests: (routes, year_group, consent)}

    FUNCTION CheckInterest(answers, fields)           // returns {field: message}
        errors <- empty
        IF answers.role NOT IN ROLES THEN errors.role <- "Select who you are"
        IF LENGTH(answers.school) > MAX_SCHOOL THEN
            errors.school <- "School or college name must be 100 characters or fewer"
        END IF
        IF answers.routes is empty OR any route NOT IN ROUTES THEN
            errors.routes <- "Select at least one placement route"
        END IF
        IF answers.year_group NOT IN YEARS THEN errors.year_group <- "Select a year group"
        IF answers.consent IS NOT TRUE THEN errors.consent <- "Tick the box to agree to be contacted"
        RETURN the errors whose field is in fields
    END FUNCTION

    FUNCTION SaveInterest(user, answers)              // answers already checked
        isNew <- (SELECT FROM interests WHERE user_id = user.id) = NULL
        INSERT INTO interests (user.id, role, school, year_group, consent TRUE)
            or, if the user already has a row, UPDATE it and set updated_at <- now
        DELETE FROM interest_routes WHERE user_id = user.id
        FOR EACH route IN answers.routes: INSERT INTO interest_routes (user.id, route)
        COMMIT
        TRY SEND to Slack ("new" or "updated", name, email, answers as labels)
        CATCH: LOG it                                 // the answers are already saved
        RETURN isNew
    END FUNCTION

    FUNCTION InterestPage(form)                       // POST /interest
        IF session has no user THEN SHOW "Sign in to register your interest"
        IF CSRF token missing or invalid THEN RESPOND 400
        IF more than 10 posts from this IP in the last minute THEN RESPOND 429
        draft <- session.draft OR the saved answers (with consent cleared) OR empty
        IF form.step IN (about, interests) THEN
            COPY that step's fields from form INTO draft (trimmed, lower-cased, routes de-duplicated)
            SAVE draft in session
            IF form.go = "back" THEN REDIRECT to the step before    // no checks, nothing lost
            errors <- CheckInterest(draft, STEP_FIELDS[form.step])
            IF errors THEN SHOW the step again with the error summary and each error by its field
            REDIRECT to the next step
        END IF
        IF form.go = "back" THEN REDIRECT to the interests step
        errors <- CheckInterest(draft, every field)    // the session draft could be incomplete
        IF errors THEN SHOW the first step with errors
        isNew <- SaveInterest(user, draft)
        REMOVE draft from session
        REDIRECT to /interest, which shows "Interest registered" or "Details updated" once
    END FUNCTION

    FUNCTION InterestApi(request)                     // POST /api/interest
        IF session has no user THEN RESPOND 401 {error: "Please sign in"}  // JSON, not a redirect
        IF X-CSRFToken header missing or invalid THEN RESPOND 400
        IF more than 10 requests from this IP in the last minute THEN RESPOND 429
        data <- PARSE_JSON(request.body)
        IF data is not an object THEN RESPOND 400 {error: "Expected a JSON object."}
        answers <- data (trimmed, lower-cased, routes de-duplicated; consent must be exactly true)
        errors <- CheckInterest(answers, every field)
        IF errors THEN RESPOND 400 {errors}
        IF SaveInterest(user, answers) THEN RESPOND 201 {interest} ELSE RESPOND 200 {interest}
    END FUNCTION

    FUNCTION RemoveInterest(user)       // DELETE /api/interest, or "Yes, remove it" on the account page
        removed <- DELETE FROM interests WHERE user_id = user.id
        DELETE FROM interest_routes WHERE user_id = user.id
        COMMIT
        IF removed THEN TRY SEND to Slack ("removed", name, email)
    END FUNCTION

interests has user_id as its primary key and interest_routes has (user_id, route), so a user can never have two interests or the same route twice, even if two requests arrive at the same moment. A step can't be skipped: asking for ?step=check before the routes are chosen opens the first unfinished step instead. Consent is cleared when saved answers are loaded, so it's asked for again every time. On the account page, Remove only opens a confirmation, and nothing is deleted until "Yes, remove it" is pressed. Test data: a role of "Student " is accepted as "student". A route of "law" gets "Select at least one placement route". Sending twice gives 201 then 200, and there's still one interests row. Changing the routes from Digital and Media to Finance leaves one interest_routes row. A request with no session gets a 401. Slack failing still saves the answers.

## 4. Gated download access check (partly built)

Problem: serve resources like course specifications, CV templates and placement guides. Public files are open to everyone, but members-only files need the user to be signed in. Nobody should be able to use the download link to read other files on the server.

### Built: course specification downloads

The T Levels page has a course specification PDF for each route, and they are all members-only. Inputs: a file name in the URL, plus the session. Outputs: the file, a redirect to sign in, or 404 or 429.

    FUNCTION DownloadSpec(name, request)       // GET /download/<name>
        IF more than 30 downloads from this IP in the last minute THEN RESPOND 429
        IF session has no user THEN
            REDIRECT to /login?next=/t-levels    // back to the T Levels page after signing in
        END IF
        filename <- DOWNLOADS[name]            // a fixed list in main.py
        IF filename = NULL THEN RESPOND 404
        RESPOND 200 with resources/specs/filename (Content-Disposition: attachment,
                                                   Cache-Control: private, no-store)
    END FUNCTION

The PDFs are kept in resources/specs, outside the folder Flask serves to anyone, so this route is the only way to get them. The URL can only pick a name from the DOWNLOADS list, never a path. Signed-out visitors see a greyed-out "Log in to download" button on the T Levels page. Test data: a signed-out visitor is sent to sign in, then back to the T Levels page. A signed-in visitor gets the PDF. A name of "../main.py" or one not in the list gets a 404.

### Planned: the full resources design

When there are public files and more types of resource, the fixed list becomes a resources table. Inputs: a resource id in the URL, plus the session. Outputs: the file, or 401, 404 or 429.

    FUNCTION DownloadResource(id, request)
        IF more than 30 downloads from this IP in the last minute THEN RESPOND 429
        IF id is not a whole number THEN RESPOND 404
        resource <- SELECT FROM resources WHERE id = id
        IF resource = NULL THEN RESPOND 404 {error: "Resource not found"}
        IF resource.members_only AND session has no user THEN
            RESPOND 401 {error: "Please sign in to download this"}
        END IF
        // The file name comes from the database, never from the URL
        path <- JOIN(RESOURCES_FOLDER, resource.filename)
        IF path is outside RESOURCES_FOLDER OR file does not exist THEN
            LOG "missing resource file", id
            RESPOND 404 {error: "Resource not found"}
        END IF
        RESPOND 200 with file (Content-Type from resource.file_type,
                              Content-Disposition: attachment,
                              Cache-Control: private if members_only)
    END FUNCTION

The sign-in check comes after the 404 check, so a 401 does give away that the id exists. That's fine, because the resource list already shows every title. Members-only files are marked Cache-Control: private so a shared cache can't pass them to someone who isn't signed in. Test data: a public file with no session gets a 200. A members-only file with no session gets a 401, and with a session gets a 200. An id of 9999 gets a 404. An id of "../main.py" gets a 404.

## 5. Site search

Problem: the nav bar's search box should take any words the user types, suggest matching pages and sections as they type, and go straight to the most relevant one. It has to cope with capitals, plurals, partial words and filler words, and give a helpful message if nothing matches. Inputs: the query text. Outputs: a list of up to 8 suggestions, then a jump to the chosen or best entry in SEARCH_INDEX (title, path, keywords), or a message.

    CONSTANTS MAX_SUGGESTIONS <- 8

    FUNCTION Normalise(text)
        RETURN LOWERCASE(text) with punctuation replaced by spaces and repeated spaces removed
    END FUNCTION

    FUNCTION Words(text)
        RETURN words of Normalise(text) that are not stop words ("the", "a", "how"...)
    END FUNCTION

    FUNCTION ScoreEntry(entry, query)
        q <- Normalise(query)
        IF q = "" THEN RETURN 0
        IF Normalise(entry.title) = q THEN RETURN 1000            // exact title wins
        short <- entry.title without a "FAQ: " style label
        titleWords <- Words(short), keywordWords <- Words(entry.keywords)
        score <- 0
        IF q appears inside Normalise(short) THEN score <- score + 50
        IF q has several words AND q appears as a phrase in keywords THEN score <- score + 40
        FOR EACH w IN Words(query)
            IF w IN titleWords THEN score <- score + 10
            ELSE IF w IN keywordWords THEN score <- score + 6
            ELSE IF LENGTH(w) >= 3 AND some k IN titleWords + keywordWords
                    (k starts with w OR (LENGTH(k) >= 4 AND w starts with k)) THEN
                score <- score + 3                                  // "eng", "placements"
            END IF
        END FOR
        IF score > 0 AND entry.path has no "#section" THEN score <- score + 1  // page beats its section
        RETURN score
    END FUNCTION

    FUNCTION FindMatches(query)
        RETURN every entry with ScoreEntry(entry, query) > 0,
               highest score first (a tie keeps the SEARCH_INDEX order)
    END FUNCTION

    FUNCTION ShowSuggestions(query)              // on every key typed, and when the box gets focus
        IF TRIM(query) = "" THEN HIDE the list; RETURN
        suggestions <- first MAX_SUGGESTIONS of FindMatches(query)
        IF suggestions is empty THEN HIDE the list; RETURN
        SHOW suggestions under the box, with the typed text in bold in each title
    END FUNCTION                                 // arrow keys move the highlight, Escape closes it

    FUNCTION Search(query, highlighted)          // Enter, the search button, or a suggestion clicked
        query <- TRIM(query)
        IF highlighted <> NULL THEN Go(highlighted, query); RETURN
        IF query = "" THEN SHOW 'Type a word to search, for example "digital" or "apply".'; RETURN
        best <- FIRST(FindMatches(query))
        IF best = NULL THEN
            RECORD search query for the analytics page
            SHOW 'No results for "query". Try "T Levels", "placement" or "contact".'
            RETURN
        END IF
        Go(best, query)
    END FUNCTION

    FUNCTION Go(entry, query)
        RECORD search query for the analytics page   // what was typed, not the title chosen
        CLEAR search box and HIDE the list
        IF entry opens the accessibility menu THEN OPEN menu
        ELSE IF entry is the section already on screen THEN SCROLL to it
        ELSE GO TO entry.path
    END FUNCTION

Each search checks every entry once, so it takes time in proportion to the size of the index. With 34 entries that's instant, and it runs in the browser without contacting the server, apart from recording the search. The recorded text is lower-cased and cut to 100 characters, and no user id or IP address is stored with it. Test data: "FAQ" goes to the FAQ page itself, not one of its sections. "eng" goes to the Engineering route. "coding" finds Digital through its keywords. "xyzzy" shows the no-results message. An empty box shows the hint.
