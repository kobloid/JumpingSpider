# JumpingSpider

An AI-powered web scraper built with Flask and the Gemini API. Instead of writing CSS selectors, you give it a URL and a list of fields — it cleans the page's HTML and asks Gemini to pull out every matching item as structured JSON. A manual CSS-selector mode is available as a fallback or alternative.

## Features

- **AI extraction** — describe the fields you want (e.g. `title`, `price`, `url`) and Gemini extracts every repeated item on the page, no selectors required.
- **Manual selector mode** — supply a container selector plus per-field selectors when you want deterministic, non-AI extraction.
- **Accounts** — register/login with hashed passwords (Flask-Bcrypt) and session auth (Flask-Login).
- **Scrape history** — logged-in users get their successful scrapes auto-saved (most recent 30) and can view, revisit, or delete them.
- **Field suggestions** — the field-name dropdown is powered by each user's own previously used fields.
- **Safety guardrails** — blocks scraping localhost/private-network hosts, honors `robots.txt`, rate-limits requests, caps request body size, and sends standard security headers.

## Tech stack

| Layer | Tools |
|---|---|
| Server | Flask |
| Scraping | `requests` + BeautifulSoup |
| AI extraction | Gemini API (`gemini-3.1-flash-lite`) |
| Auth | Flask-Bcrypt, Flask-Login |
| Rate limiting | Flask-Limiter |
| Database | SQLite (`scrapes.db`) |
| Production server | Gunicorn |

## Project structure

```
JumpingSpider/
├── app.py              # Flask app: routes, scraping, AI extraction, auth
├── requirements.txt
├── templates/
│   ├── index.html      # scraper UI
│   └── history.html    # saved-scrapes UI
└── .gitignore
```

## Setup

1. **Clone and install dependencies**

   ```bash
   git clone https://github.com/kobloid/JumpingSpider.git
   cd JumpingSpider
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**

   Create a `.env` file in the project root:

   ```
   GEMINI_API_KEY=your_gemini_api_key
   SECRET_KEY=a_random_secret_string
   ```

3. **Run it**

   ```bash
   python app.py
   ```

   The app serves on `http://localhost:5000`. The SQLite database (`scrapes.db`) and its tables are created automatically on first run.

   For production, run behind Gunicorn instead of the Flask dev server:

   ```bash
   gunicorn app:app
   ```

## API routes

| Method | Route | Auth required | Description |
|---|---|---|---|
| GET | `/` | No | Serves the scraper UI |
| GET | `/history` | No | Serves the saved-scrapes UI |
| POST | `/scrape` | No | Fetches a URL and extracts data (AI or selectors). Rate-limited to 10/min. Auto-saves the result if logged in. |
| GET | `/used-fields` | No | Returns the current user's previously used field names (empty list if logged out) |
| POST | `/register` | No | Creates an account and logs the user in |
| POST | `/login` | No | Logs a user in |
| POST | `/logout` | Yes | Logs the user out |
| GET | `/me` | No | Returns current auth status/username |
| POST | `/save` | Yes | Manually saves a scrape result. Rate-limited to 20/min. |
| GET | `/saved` | Yes | Lists the current user's saved scrapes |
| GET | `/saved/<id>` | Yes | Returns full data for one saved scrape |
| DELETE | `/saved/<id>` | Yes | Deletes a saved scrape |

## Security notes

- URLs must be `http(s)`, and requests to `localhost`, loopback, and private IP ranges are blocked before any fetch happens.
- `robots.txt` is checked and respected for the target site.
- Passwords must be 8+ characters with an uppercase letter, lowercase letter, digit, and special character, and no spaces.
- Every response includes `X-Content-Type-Options`, `X-Frame-Options`, and a restrictive `Content-Security-Policy` header.
- Request bodies are capped at 1 MB.

## Status / roadmap

Auth, saved history, and field suggestions are implemented end-to-end. Open items:
- Client-side polish for the login/register flow (e.g. inline validation messaging)
- Deployment (Render/Railway) with Gunicorn