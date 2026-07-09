Here's a prompt you can paste at the start of a new chat:

---

I'm building **JumpingSpider**, an AI-powered web scraper inspired by Thunderbit, as a resume project. I'm a CS freshman with basic Python knowledge targeting SWE/systems engineering roles.

**Tech stack:**
- **Server:** Flask (Python)
- **Scraping:** BeautifulSoup + requests
- **AI extraction:** Gemini API (`gemini-2.0-flash`) — sends cleaned HTML directly to Gemini and asks it to extract structured data, no CSS selectors needed (Thunderbit-style). CSS selector fallback exists if AI fails.
- **Database:** SQLite — `users`, `scrapes`, `used_fields` tables
- **Auth:** flask-bcrypt + flask-login (installed, partially implemented)
- **Rate limiting:** flask-limiter (10/min on /scrape)
- **Security:** XSS escaping, security headers, URL validation, internal network blocking, robots.txt compliance

**Frontend (client):**
- Three-column layout: Recents sidebar (left), results table (center), controls (right)
- Field input uses a chip/dropdown system — fields are added as chips, suggestions come from `/used-fields` (user's past fields from DB)
- Results render as a table with search, image detection, URL detection, expandable cells
- Save options: HTML report, JSONL for ML
- Scrapes auto-save on success (capped at 10 per user), Recents sidebar refreshes automatically

**Current backend routes:**
- `GET /` — serves index.html
- `POST /scrape` — fetches page, runs Gemini extraction, falls back to selectors, auto-saves if logged in
- `GET /saved` — returns saved scrapes list for current user
- `GET /saved/<id>` — returns full scrape data
- `DELETE /saved/<id>` — deletes a scrape
- `GET /used-fields` — returns user's past field names for dropdown
- `POST /register`, `POST /login`, `POST /logout` — not yet built

**Where we are with auth:**
- `flask-bcrypt` and `flask-login` installed
- `app.secret_key`, `Bcrypt`, and `LoginManager` configured
- `User` class with `UserMixin` and `user_loader` defined
- `users` table exists in DB with `id`, `username`, `email`, `password_hash`, `created_at`
- `scrapes` and `used_fields` tables both have `user_id` foreign key
- `record_used_fields(fields, user_id)` updated to be per-user
- **Not yet built:** `/register`, `/login`, `/logout` routes and the login/register frontend page

**Immediate next steps:**
1. Build `/register` and `/login` routes on the server
2. Update `/scrape`, `/saved`, `/used-fields` routes to check `current_user.is_authenticated`
3. Build a login/register page on the client
4. Update the Recents sidebar to show "sign in to save history" when logged out
5. Deploy to Render or Railway with gunicorn

**Key principles:**
- I want to understand concepts alongside implementation, not just receive working code
- Use correct terminology: client/server not frontend/backend
- Scope is tight — keep features simple and explainable
- I need to be able to talk about every decision in an interview