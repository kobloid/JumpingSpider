from flask import Flask, jsonify, request, render_template, make_response
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import google.generativeai as genai
import requests
import os
import json
import sqlite3
from datetime import datetime

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({'success': False, 'error': 'Login required'}), 401

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

DB_PATH = 'scrapes.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scrapes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT NOT NULL,
            data TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            method TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_fields (
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            last_used TEXT NOT NULL,
            use_count INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, name)
        )
    ''')

    conn.commit()
    conn.close()

# Run once when the app starts
init_db()

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['email'])
    return None

MAX_SAVED_SCRAPES = 30


def trim_old_scrapes(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM scrapes
        WHERE user_id = ? AND id NOT IN (
            SELECT id FROM scrapes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        )
    ''', (user_id, user_id, MAX_SAVED_SCRAPES))
    conn.commit()
    conn.close()


def record_used_fields(fields, user_id):
    if not fields or not user_id:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    for f in fields:
        f = f.strip().lower()
        if not f:
            continue
        cursor.execute('''
            INSERT INTO used_fields (user_id, name, last_used, use_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, name) DO UPDATE SET
                last_used = excluded.last_used,
                use_count = use_count + 1
        ''', (user_id, f, now))
    conn.commit()
    conn.close()


def fetch_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def clean_html(html):
    """Strip noise, extract visible text with tag/class context"""
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'meta', 'link', 'head']):
        tag.decompose()

    lines = []
    for tag in soup.find_all(True):
        text = tag.get_text(strip=True)
        if text and len(text) > 2:
            classes = ' '.join(tag.get('class', []))
            lines.append(f"[{tag.name}.{classes}] {text[:200]}")

    seen = set()
    unique_lines = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique_lines.append(line)

    return '\n'.join(unique_lines)[:60000]


def extract_with_ai(html, url, fields):
    try:
        cleaned = clean_html(html)

        prompt = f"""You are a data extraction expert. Extract ALL instances of structured data from this webpage.

URL: {url}
Fields to extract: {', '.join(fields)}

Webpage content:
{cleaned}

Rules:
- Find EVERY repeated item on the page, not just the first one
- The same entity (e.g. same username) may appear multiple times — include every instance as a separate item, do not deduplicate
- Each item should have all the requested fields
- If a field is missing for an item, use null
- Return ONLY a raw JSON array with ALL items, no explanation, no markdown, no code fences

Format:
[
  {{"field1": "value", "field2": "value"}},
  {{"field1": "value", "field2": "value"}}
]

Return ALL items you find, not just one."""

        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        response = model.generate_content(prompt)
        raw = response.text.strip()

        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1]
            raw = raw.rsplit('```', 1)[0]

        data = json.loads(raw.strip())

        if isinstance(data, list) and len(data) > 0:
            return data
        return None

    except Exception as e:
        print(f"AI extraction failed: {e}")
        return None


def extract_with_selectors(html, container, selectors):
    soup = BeautifulSoup(html, 'html.parser')
    containers = soup.select(container)
    items = []

    for c in containers:
        item_data = {}
        for field, selector in selectors.items():
            element = c.select_one(selector)
            item_data[field] = element.get_text(strip=True) if element else None
        items.append(item_data)

    return items


def is_url_safe(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        blocked = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
        if hostname in blocked:
            return False
        if any(hostname.startswith(p) for p in ['192.168.', '10.', '172.']):
            return False
        return True
    except:
        return False


def allows_scraping(url):
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch('*', url)
    except Exception:
        return True


def secure_response(data, status=200):
    resp = make_response(jsonify(data), status)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Content-Security-Policy'] = "default-src 'self' fonts.googleapis.com fonts.gstatic.com; script-src 'self' 'unsafe-inline'"
    return resp


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/history')
def history():
    return render_template('history.html')


@app.route('/scrape', methods=['POST'])
@limiter.limit("10 per minute")
def scrape():
    try:
        data = request.json
        url = data.get('url', '').strip()
        fields = data.get('fields', [])
        container = data.get('container', '')
        selectors = data.get('selectors', {})

        if not url:
            return secure_response({'success': False, 'error': 'URL is required'}, 400)
        if not url.startswith(('http://', 'https://')):
            return secure_response({'success': False, 'error': 'URL must start with http:// or https://'}, 400)
        if not is_url_safe(url):
            return secure_response({'success': False, 'error': 'That URL is not allowed'}, 400)
        if not allows_scraping(url):
            return secure_response({'success': False, 'error': 'This site does not allow scraping (robots.txt)'}, 403)
        if not fields and not (container and selectors):
            return secure_response({'success': False, 'error': 'Provide fields for AI or manual selectors'}, 400)

        try:
            html = fetch_page(url)
        except Exception as e:
            return secure_response({'success': False, 'error': f'Could not fetch page: {str(e)}'}, 400)

        items = None
        method = None

        if fields:
            items = extract_with_ai(html, url, fields)
            if items is not None:
                method = 'ai'

        if items is None and container and selectors:
            items = extract_with_selectors(html, container, selectors)
            method = 'selectors'

        if not items:
            return secure_response({'success': False, 'error': 'No data found — try manual selectors or a different URL'}, 500)

        # Only track field usage and auto-save for logged-in users
        saved_id = None
        if current_user.is_authenticated:
            if fields:
                record_used_fields(fields, current_user.id)

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO scrapes (user_id, url, data, item_count, method, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                    (current_user.id, url, json.dumps(items), len(items), method, datetime.now().isoformat())
                )
                conn.commit()
                saved_id = cursor.lastrowid
                conn.close()
                trim_old_scrapes(current_user.id)
            except Exception as e:
                print(f"Auto-save failed: {e}")

        return secure_response({
            'success': True,
            'count': len(items),
            'data': items,
            'url': url,
            'method': method,
            'saved_id': saved_id
        })

    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)

@app.route('/used-fields', methods=['GET'])
def get_used_fields():
    if not current_user.is_authenticated:
        return secure_response({'success': True, 'fields': []})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT name FROM used_fields WHERE user_id = ? ORDER BY last_used DESC LIMIT 30',
            (current_user.id,)
        )
        rows = cursor.fetchall()
        conn.close()
        names = [row['name'] for row in rows]
        return secure_response({'success': True, 'fields': names})
    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)

@app.route('/save', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def save_scrape():
    try:
        payload = request.json
        url = payload.get('url', '').strip()
        items = payload.get('data', [])
        method = payload.get('method', 'unknown')

        if not url or not items:
            return secure_response({'success': False, 'error': 'No data to save'}, 400)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO scrapes (user_id, url, data, item_count, method, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (current_user.id, url, json.dumps(items), len(items), method, datetime.now().isoformat())
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return secure_response({'success': True, 'id': new_id})
    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)


@app.route('/saved', methods=['GET'])
@login_required
def get_saved_scrapes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, url, item_count, method, created_at FROM scrapes WHERE user_id = ? ORDER BY created_at DESC',
            (current_user.id,)
        )
        rows = cursor.fetchall()
        conn.close()
        scrapes = [dict(row) for row in rows]
        return secure_response({'success': True, 'scrapes': scrapes})
    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)


@app.route('/saved/<int:scrape_id>', methods=['GET'])
@login_required
def get_saved_scrape(scrape_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM scrapes WHERE id = ? AND user_id = ?',
            (scrape_id, current_user.id)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return secure_response({'success': False, 'error': 'Not found'}, 404)

        result = dict(row)
        result['data'] = json.loads(result['data'])
        return secure_response({'success': True, 'scrape': result})
    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)


@app.route('/saved/<int:scrape_id>', methods=['DELETE'])
@login_required
def delete_saved_scrape(scrape_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM scrapes WHERE id = ? AND user_id = ?',
            (scrape_id, current_user.id)
        )
        conn.commit()
        deleted = cursor.rowcount
        conn.close()

        if deleted == 0:
            return secure_response({'success': False, 'error': 'Not found'}, 404)

        return secure_response({'success': True})
    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    # Basic validation
    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password are required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    # Check for existing user
    existing = cur.execute(
        'SELECT id FROM users WHERE username = ? OR email = ?',
        (username, email)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Username or email already taken'}), 409

    # Hash and store
    password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    cur.execute(
        'INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)',
        (username, email, password_hash, datetime.utcnow().isoformat())
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    # Log them in immediately after registering
    user = User(user_id, username, email)
    login_user(user)

    return jsonify({'message': 'Registered successfully', 'username': username}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    conn = get_db_connection()
    row = conn.execute(
        'SELECT id, username, email, password_hash FROM users WHERE username = ?',
        (username,)
    ).fetchone()
    conn.close()

    # Same error message whether username or password is wrong — see note below
    if row is None or not bcrypt.check_password_hash(row['password_hash'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    user = User(row['id'], row['username'], row['email'])
    login_user(user)

    return jsonify({'message': 'Logged in successfully', 'username': row['username']}), 200


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out successfully'}), 200


@app.route('/me', methods=['GET'])
def me():
    if current_user.is_authenticated:
        return jsonify({'authenticated': True, 'username': current_user.username})
    return jsonify({'authenticated': False})


if __name__ == "__main__":
    app.run(debug=False, port=5000)