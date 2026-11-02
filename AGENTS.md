# AGENTS.md

A Flask + SQLite site about Amazon T Level placements, built by a six-person T Level team for Amazon Emerging Talent Programs. Read `README.md` first for setup, routes, layout, the database, the chat API, the Slack bot and styling conventions. This file only covers what the README doesn't.

## Project tracking

### Asana
- Board: https://app.asana.com/1/8442528107068/project/1219390264017816/list/1219389953023184
- Project GID `1219390264017816`, workspace GID `8442528107068`.
- Sections follow the brief: Setup, Task 1: Research, Proposal & Design, Task 2: Frontend / Backend / Hosting / Evidence, Task 3: Feedback & Evaluation, Task 4: AI, Final Presentation, Stretch.
- Custom fields: "Link" (text, usually a Pippin, Canva or GitHub URL) and "Progress" (Completed, Needs review, In progress, Not started, Blocked). Progress is set by hand and often disagrees with the completed tick, so check both.
- Take deliverable owners from task assignees, not from the Pippin "Role allocations" doc. They often differ.
- Some graded deliverables (proposal, KPIs and acceptance criteria, ethical impact assessment, accessibility audit, Amazon Principles) live in Canva and are only findable through the task's Link field.
- MCP: load `enterprise-asana-mcp::*` with `tool_load`. `GetTasksFromProject` with `opt_fields=name,assignee.name,completed,memberships.section.name,custom_fields.name,custom_fields.display_value` returns the whole board in one call. New tasks land in the first section, so move them with `AddTaskToSection`, one at a time (parallel `insert_after` calls fail). "Run mwinit" errors are usually transient; retry once.

### Pippin
- Root folder: https://pippin.amazon.dev/architect/crevBtFyH1TD (ID `crevBtFyH1TD`). The root holds folders only:

| Folder | ID | Holds |
|---|---|---|
| Project & Admin | `Uyrr9Ur0qlHA` | Digital Brief, Role allocations, Website Requirements, Architecture, Feedback Plan, Mentor Feedback, Final Presentation Plans |
| Frontend | `mM8yvH7hekmJ` | Frontend needs, Accessibility needs, Site Copy (all site wording), Frontend Development Log, Design Proposal subfolder |
| Backend | `s1i8WvBCZGr1` | SQL Schema, Endpoint structures & schemas, Data Requirements |
| Cloud | `pqYlzixy4wXx` | AWS hosting docs, cloud security risks, architecture diagram |
| AI | `Oj5fospWECec` | AI Chatbot Design, AI Feasibility Assessment |
| Security & Privacy | `3o6W34Ci1aAX` | Application Security, Privacy Page Content, Asset Log |
| Testing & QA | `cC51OKDWrrnR` | Test Strategy, Iterative Testing Document |

- MCP: load `pippin-mcp::*` with `tool_load`. Single-doc tools accept a Pippin URL directly. `pippin_sync_project_to_local` with `recursive: true` is the quickest way to read or back up every doc.
- There is no rollback or delete tool. Back up a doc before `pippin_update_artifact`. `string_replace` edits can flatten soft line breaks elsewhere in the same doc, so re-read the doc after editing.
- Ask before editing another member's doc; leave a comment (`pippin_post_artifact_comment`) when unsure.

### Deadlines
- Final presentation: 6 Nov 2026, 15 minutes plus 15 minutes Q&A. Every member presents and every graded deliverable must be linked.
- The brief (Digital Brief in Project & Admin) lists the graded deliverables per task. Judge progress against it, not against the board alone.

## Team

| Person | Areas | Asana user GID |
|---|---|---|
| Leeam Tindle | Database lead, backend, security, DevOps | `1219389515259070` |
| Shea Palin | Backend lead, endpoints, algorithm designs, technical demo | `1219407343668820` |
| Ajay Hearn | QA, AWS hosting, cloud docs | `1219403890373347` |
| Kacper Koneczny | Frontend lead, research notes, non-technical demo | `1219403706936684` |
| Harnoor Singh | UI/UX, AI, security and legal, assets log, iterative testing | `1219408879557269` |
| Munashe | PM, proposal, docs, feedback, evaluation, presentation | `1219409767803298` |

Team decisions: Slack integration is required (notification on contact submissions). The community page, translation and RDS are stretch goals.

## Gotchas

- Importing `main` without `SECRET_KEY` in the environment generates a key and appends it to the real `.env`. Scripts and tests must set `SECRET_KEY` before `import main`.
- `chat_knowledge.md` is a hand-kept copy of the site's page text that the chat assistant answers from. It does not sync. Update the matching section when you change page wording, password rules, `MAX_LOGIN_ATTEMPTS`/`LOCKOUT_MINUTES` in `main.py`, or quiz text in `Sources/js/quiz.js`. Its whole content is sent to the model, so put nothing private in it.
- The Content Security Policy blocks inline `<script>`, `<style>` and `onclick=""`. Page behaviour goes in `Sources/js/<page>.js`, listed in the template's `page_js`.
- Form error messages exist twice, in `main.py` (`*_error()` functions) and `auth.js`. Change both. `auth.js` serves both the login and account pages, so a new field needs an entry in its `rules` map keyed by the input id.
- The account page has one form per detail. Each row's "Change" link goes to `/account?edit=<form>` (the `edit_link` macro) and posts to `/account/<form>`; a new editable detail needs a `try_change_*` function and an `ACCOUNT_FORMS` entry in `main.py`, plus a matching `.account-row` in `account.html`. The Downloads and Accessibility sections were removed on purpose; don't re-add them.
- Header search entries in `topNavBar.js` (`SEARCH_INDEX`) point at section ids such as `advice#your-path`. Renaming or removing a section id means updating them, and `chat_knowledge.md`.
- Page CSS uses `--color-*` tokens from `tokens.css`, never raw hex. Check light, dark and high-contrast themes. (`analytics.css` still has one raw border colour.)
- Pages arriving from other branches as standalone HTML (own `<head>`, `.html` links) must be converted to extend `base.html` and use short URLs. Old `.html` addresses go in `OLD_PAGE_URLS`, not new routes.
- `docs/*.md` (and their .docx/.pdf copies) are partly out of date: old error messages, the old hand-written chat limiter, `init_db` at startup, the old random `SECRET_KEY`. Check against the code before quoting them.
- `Tlevel.db` is an old leftover. The app uses `site.db`. Both are gitignored.
- In browser automation, the injected nav bar has its own submit button (search). Scope form selectors to `main`.
- The `.venv` is Python 3.9. Keep code 3.9-compatible (no `match`, no `X | Y` type hints evaluated at runtime).

## Verifying changes

There is no test suite. Use the Flask test client:

```bash
.venv/bin/python -W ignore - <<'EOF' 2>/dev/null
import os, tempfile
os.environ["SECRET_KEY"] = "test"
os.environ["ANALYTICS_EMAILS"] = "test@example.com"
import main
main.DATABASE = os.path.join(tempfile.mkdtemp(), "t.db")
main.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
main.limiter.enabled = False
c = main.app.test_client()
for p in ["/", "/t-levels", "/advice", "/faqs", "/quiz", "/contact", "/privacy", "/login"]:
    print(p, c.get(p).status_code)
r = c.post("/register", data={"name": "Test User", "email": "test@example.com",
           "password": "Passw0rd!", "confirm_password": "Passw0rd!"})
print("register", r.status_code, r.headers.get("Location"))  # 302 /account
print("analytics", c.get("/analytics").status_code)          # 200
print("edit", c.get("/account?edit=email").status_code)      # 200
r = c.post("/account/password", data={"current_password": "Passw0rd!",
           "new_password": "Newpass1!", "confirm_password": "Newpass1!"})
print("password", r.status_code, r.headers.get("Location"))  # 302 /account
EOF
```

- A valid contact POST writes to the DB and calls Slack. Stub `main.is_slack_configured` and `main.send_to_slack` in tests.
- Live chat check (uses the OpenRouter key in `.env`): `.venv/bin/python -W ignore -c "import main; c=main.app.test_client(); print(c.post('/api/chat', json={'messages':[{'role':'user','content':'What is a T Level?'}]}).get_json())" 2>/dev/null`
- Don't take screenshots to check layout or themes. Run the functional checks, then tell the user which pages, states and themes to look at in the browser.

## Conventions

- Comments explain why (security reasons, design decisions, gotchas). Don't add comments that restate the code.
- Sign-up keeps "An account with that email already exists". Don't add account-enumeration protections.
- `main` is the only long-lived branch. Never force-push; push a new branch instead.
- Designs: Figma file `MvIsqWaGxhlMdu5pPDhNXH`, plus the team's design system export (outside the repo). When restyling a page to the export, write a page-scoped `Sources/css/<page>.css` on the site's own tokens. Don't import the export's `bundle.css` or `tokens.css`, and keep the site's injected header and footer.
