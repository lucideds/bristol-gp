# Verification: Mobile-responsive scaling

## Setup

Served the site locally from the `Template` directory on a localhost-only bind:

```
cd /Users/kakonecz/Documents/GitHub/bristol-gp/frontend/Template
python3 -m http.server 8000 --bind 127.0.0.1
```

Headless browser used: the system-installed Google Chrome
(`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`), run with
`--headless=new --disable-gpu --no-sandbox`. No new dependency was installed
(Playwright/`npx playwright` and a standalone `chromium`/`chromium-browser`
binary were checked first and are not available in this environment; Chrome
was already installed, so it was used instead of adding a package).

Verification scripts were written as temporary HTML harness files
(`_scroll_check_tmp.html`, `_nav_check_tmp.html`, `_desktop_check_tmp.html`,
`_footer_check_tmp.html`) placed temporarily inside `Template/` so they could
load the real pages same-origin via `<iframe>` and read `contentDocument`/
`contentWindow` (cross-origin rules block this from a `file://` parent). Each
harness ran page(s) in an iframe at a fixed width, read the values below via
JS, and wrote the result into `document.title`, which was captured with
`--dump-dom`. **All four harness files were deleted after use** — they are
not part of the committed change.

## 1. No horizontal scroll at 375px (requirement 2)

Checked `document.documentElement.scrollWidth <= window.innerWidth` for all 13
pages (`home`, `advice`, `TLevel`, `accessibility`, `account`, `contact`,
`faqs`, `login`, `privacy`, `quiz`, `signin`, `404`, `500`) at a 375px iframe
width. Result for every page: `scrollWidth: 375, innerWidth: 375, overflow:
false`. No page overflows horizontally at 375px.

Repeated the same check at 768px for all 13 pages: every page returned
`scrollWidth: 768, innerWidth: 768, overflow: false`.

## 2. Viewport meta tag (requirement 1)

Grepped all 13 HTML pages for `viewport`; every page already had
`<meta name="viewport" content="width=device-width, initial-scale=1.0">` in
`<head>` before this change (confirmed, no edit needed).

## 3. Hamburger menu — accessible and keyboard-operable (requirement 3)

Loaded `home.html` in an iframe at 375px and drove the new `.nav-toggle`
button programmatically:

- `toggle.tagName` → `BUTTON` (a real, natively focusable/keyboard-operable element).
- `aria-expanded` starts `"false"`; `aria-controls` is `"nav-collapsible"`, which
  matches the panel's `id="nav-collapsible"`.
- Panel starts closed (`.nav-collapsible--open` absent, computed `display` ends
  up `none` via the base `.nav-collapsible { display: none }` rule at this width).
- `toggle.click()` → `aria-expanded` becomes `"true"`, panel gets
  `.nav-collapsible--open`, computed `display` becomes `flex`.
- Dispatching a `keydown` with `key: "Escape"` on `document` → `aria-expanded`
  reverts to `"false"`, panel class removed (menu closes on Escape).
- Re-opened the menu, then clicked a `.nav-link` inside the panel (listener
  bound with `preventDefault` in the test only, to inspect state instead of
  letting the iframe navigate away) → panel class removed, i.e. following a
  link closes the menu.

All of the above were also visually confirmed via screenshot
(`home.html` at 375px): hamburger icon visible top-right next to the brand,
links/search/sign-in hidden until toggled.

## 4. Desktop (>= 1024px) unchanged (requirement 8)

Loaded `home.html` in an iframe at 1280px and read computed styles:

- `.nav-toggle` → `display: none` (hamburger invisible on desktop).
- `.nav-top` → `display: grid`, `grid-template-columns: 449.328px 333.344px
  449.328px` (the original `1fr auto 1fr` grid, untouched).
- `.nav-collapsible` → `display: block` (not force-hidden; its children render
  inline as before since no `max-width: 768px` rule applies).
- `.nav-links` → `flex-direction: row` (links still in a row).
- `.chat-toggle` → `right: 20px; bottom: 20px` (original fixed position,
  untouched; the new 480px-only override does not apply at 1280px).
- `scrollWidth === innerWidth === 1280` (no overflow).

Screenshots taken at 1280px (`home.html`) and 768px (`home.html`) and 375px
(`home.html`, `login.html`) confirm visually: at 1280px the nav shows
"Home / T Level / Advice / FAQ / Contact", the search box, and the orange
"Sign in" button inline with no hamburger — identical in layout to the
pre-change markup. At 768px and 375px the hamburger button replaces that row
and the links/search/sign-in collapse into the toggled panel.

## 5. Footer / chat widget no-collision check (requirement 5, plan step 4)

Per the plan, no code change was expected in `footer.css`/`auth.css` unless a
collision was found. Measured bounding rectangles at 375px on `login.html`
(has both footer and chat widget):

- Footer "Privacy" link rect: `left 161.5, right 213.5, top 864, bottom 884`.
- Chat toggle button rect: `left 263.1, right 363, top 845, bottom 888`.
- Computed overlap: `false`.

No collision, so `footer.css` and `auth.css` were left unchanged, as the plan
anticipated.

## 6. Auth pages / quiz single-column on mobile (requirement 6)

Screenshot of `login.html` at 375px shows the `.auth-card` filling the width
with even side margins, the Sign in/Sign up tab switch, and the email/password
fields stacked full-width in a single column — already provided by
`auth.css`'s existing `width: 100%; max-width: 360px` and the full-width
`.auth-field input` rule, no change needed. `quiz.html` and `account.html`
have empty `<body>` content currently (no form markup yet to adjust); their
viewport meta tag and the new defensive CSS (`input, textarea, select,
button { max-width: 100% }` in `topNavBar.css`, not loaded on these two pages
since neither includes `topNavBar.css`/`.js`) stand ready for when content is
added. This matches the plan's documented finding that `account.html` and
`quiz.html` are stub pages with no markup to make responsive today.

## 7. Chat widget mobile fit (requirement 5)

`chatWidget.css` already capped the panel at `max-width: calc(100vw - 40px)`
before this change. Added an `@media (max-width: 480px)` rule making the panel
a near-full-width sheet (`left: 10px; right: 10px; width: auto;`) and nudging
the toggle button's padding/position. Verified no overlap with the footer (see
#5) and no horizontal overflow (see #1, which includes pages with the chat
widget).

## What was NOT changed

- `footer.css`, `auth.css`: no edit — the plan's conditional step 4 check found
  no collision, confirmed empirically above.
- No HTML file was edited — the viewport meta tag was already present on every
  page, and no visible page content exists yet to adjust (all pages besides
  `login.html`/`signin.html` have empty bodies populated only by the shared
  JS components).

## Cleanup

- All temporary verification harness HTML files were deleted from `Template/`
  after use.
- The local server was stopped after verification:
  `lsof -ti :8000 | xargs kill`, then confirmed `curl` to
  `http://127.0.0.1:8000/home.html` no longer connects.
