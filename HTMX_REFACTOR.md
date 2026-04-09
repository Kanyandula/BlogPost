# HTMX Integration Refactor — NyasaBlog

Tracking document for migrating NyasaBlog from a traditional server-rendered Django app to a reactive HTMX-powered experience.

**Base branch**: `master`
**Started**: 2026-04-08

---

## Phase Sequence

| Phase | Branch | Description | Status |
|-------|--------|-------------|--------|
| 0 | `htmx/phase-0-foundation` | Foundation + Toast + Auth Guard + CSRF | Done |
| 1 | `htmx/phase-1-likes-bookmarks` | Likes & Bookmarks (validates setup) | Done |
| 2 | `htmx/phase-2-newsletter` | Newsletter Subscribe | Done |
| 3 | `htmx/phase-3-comments` | Comments (submit, delete, OOB count) | Done |
| 4 | `htmx/phase-4-pagination` | Pagination / Infinite Scroll | Pending |
| 5 | `htmx/phase-5-category-filter` | Category Filtering (explicit ?partial=) | Pending |
| 6 | `htmx/phase-6-live-search` | Live Search (header dropdown + page) | Pending |
| 7 | `htmx/phase-7-forms` | Form Submissions (login, register, contact, account) | Pending |
| 8 | `htmx/phase-8-cleanup` | Cleanup (remove dead JS, add indicators) | Pending |

---

## Key Architectural Decisions

1. **HX-Trigger for toasts** — not OOB HTML appended to every response. Single global JS listener.
2. **`@htmx_login_required` decorator** — returns 401 + `HX-Reswap: none` + toast for unauthenticated HTMX requests. Prevents login page HTML from being swapped into a button target.
3. **Explicit `?partial=` query param** — for differentiating partial responses (e.g., pagination vs. category filtering). More resilient than `request.htmx.target`.
4. **Progressive enhancement** — partials are `{% include %}`d in parent templates, so the site works without JS.
5. **JSON API preserved** — views branch on `request.htmx`; DRF API and future mobile clients unaffected.
6. **CKEditor forms stay traditional** — CKEditor DOM state doesn't survive HTMX swaps.
7. **No `hx-boost`** — too much risk for admin, CKEditor, third-party pages. Per-element HTMX is sufficient.

---

## Phase 0: Foundation

### Changes
- `requirements.txt` — add `django-htmx`
- `mysite/settings.py` — add `django_htmx` to `INSTALLED_APPS`, add `HtmxMiddleware`
- `templates/base.html` — add HTMX script, CSRF config, toast container, global error handler
- `templates/snippets/base_css.html` — add htmx-indicator + toast animation CSS
- `blog/utils.py` — `trigger_toast()` helper, `@htmx_login_required` decorator
- Create `partials/` directories

### Verification
- [ ] HTMX loads on every page (check Network tab)
- [ ] `request.htmx` is available in views (add a print statement)
- [ ] CSRF token is sent with HTMX POST requests
- [ ] Toast fires from browser console: `document.body.dispatchEvent(new CustomEvent('showToast', {detail: {message: 'Test', type: 'success'}}))`

---

## Phase 1: Likes & Bookmarks

### Changes
- `blog/templates/blog/partials/like_button.html` — new partial
- `blog/templates/blog/partials/bookmark_button.html` — new partial
- `blog/views.py` — modify `toggle_like_view`, `toggle_bookmark_view` to return partials for HTMX
- `blog/templates/blog/detail_blog.html` — replace inline buttons with `{% include %}`, delete `toggleLike`/`toggleBookmark` JS
- `blog/templates/blog/bookmarks.html` — replace inline `fetch()` with `hx-post`

### Verification
- [ ] Like toggles without page reload, count updates, toast shows
- [ ] Bookmark toggles without page reload, toast shows
- [ ] Bookmark removal on bookmarks page removes the card with transition
- [ ] Unauthenticated user sees toast "Please log in" instead of broken swap
- [ ] JSON API still works (`curl -X POST`)

---

## Phase 2: Newsletter Subscribe

### Changes
- `personal/views.py` — modify `subscribe_view` for HTMX
- Multiple templates — replace `submitNewsletter()` with `hx-post` forms
- `templates/base.html` — delete `submitNewsletter` function

### Verification
- [ ] Subscribe works without page reload
- [ ] Duplicate email shows "already subscribed" message
- [ ] Empty email shows error

---

## Phase 3: Comments

### Changes
- `blog/templates/blog/partials/comment_item.html` — new
- `blog/templates/blog/partials/comment_form.html` — new
- `blog/templates/blog/partials/reply_item.html` — new
- `blog/urls.py` — add `comment_create` URL
- `blog/views.py` — add `htmx_create_comment_view`, modify `delete_comment_view`
- `blog/templates/blog/detail_blog.html` — HTMX comment form + list

### Verification
- [ ] Comment submits without reload, appears at top of list, form resets
- [ ] Reply submits without reload, appears under parent
- [ ] Comment delete removes element, shows confirm dialog
- [ ] Comment count updates via OOB swap
- [ ] Unauthenticated user gets toast, not broken swap

---

## Phase 4: Pagination / Infinite Scroll

### Changes
- `personal/templates/personal/partials/post_grid.html` — new
- `personal/views.py` — modify `home_screen_view`
- `personal/templates/personal/home.html` — use `{% include %}`, remove pagination block

### Verification
- [ ] Scrolling to bottom loads more posts
- [ ] Last page doesn't show loading sentinel
- [ ] Initial page load still works without JS

---

## Phase 5: Category Filtering

### Changes
- `personal/templates/personal/partials/home_content.html` — new
- `personal/templates/personal/home.html` — HTMX category pills with `hx-vals`
- `personal/views.py` — differentiate via `?partial=` param

### Verification
- [ ] Clicking a category filters posts without reload
- [ ] URL updates via `hx-push-url`
- [ ] Back button works correctly
- [ ] Direct URL access still renders full page

---

## Phase 6: Live Search

### Changes
- `personal/templates/personal/partials/search_dropdown.html` — new
- `templates/snippets/header.html` — HTMX search input
- `personal/views.py` — modify `search_view` for dropdown partial

### Verification
- [ ] Typing in header search shows dropdown after 300ms
- [ ] Results update as you type
- [ ] Clicking a result navigates to the post
- [ ] "View all results" links to full search page

---

## Phase 7: Form Submissions

### Changes
- `account/templates/account/partials/login_form.html` — new
- `account/templates/account/partials/register_form.html` — new
- `personal/templates/personal/partials/contact_success.html` — new
- `account/views.py` — modify login, register, account views
- `personal/views.py` — modify contact view
- Template files — add `hx-post` attributes

### Verification
- [ ] Login errors show inline without reload
- [ ] Successful login redirects via `HX-Redirect`
- [ ] Registration errors show inline
- [ ] Contact form shows success message without reload
- [ ] Account settings saves with file upload

---

## Phase 8: Cleanup

### Changes
- Remove all dead inline JS
- Add `hx-indicator` spinners to all HTMX forms
- Final review of all templates for missed opportunities

### Verification
- [ ] No inline `fetch()` calls remain (except theme toggle)
- [ ] Loading indicators visible during slow requests
- [ ] All pages functional with and without JS
