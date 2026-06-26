from flask import Flask, jsonify, request, render_template, make_response
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urlparse
import google.generativeai as genai
import requests
import os
import json

CLEAN_CHAR_LIM = 60000

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

def allows_scraping(url):
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        response = requests.get(robots_url, timeout=5)
        
        # If no robots.txt exists, assume allowed
        if response.status_code == 404:
            return True
        
        lines = response.text.splitlines()
        
        current_agent = None
        allowed = True

        for line in lines:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Split each line into key and value
            if ':' not in line:
                continue

            key, _, value = line.partition(':')
            key = key.strip().lower()
            value = value.strip()

            # Track which user-agent block we're in
            if key == 'user-agent':
                current_agent = value.lower()

            # Only care about rules for * (all bots) or our specific agent
            if current_agent in ('*', 'jumpingspider'):
                if key == 'disallow' and value == '/':
                    # Entire site is disallowed
                    allowed = False
                elif key == 'disallow' and value and parsed.path.startswith(value):
                    # This specific path is disallowed
                    allowed = False
                elif key == 'allow' and value and parsed.path.startswith(value):
                    # Explicitly allowed overrides disallow
                    allowed = True

        return allowed

    except Exception:
        # If anything goes wrong, assume allowed
        return True


def fetch_page(url):
    """Fetch raw HTML from a URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def clean_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove noise tags
    for tag in soup(['script', 'style', 'noscript', 'meta', 'link', 'head']):
        tag.decompose()
    
    # Get visible text with spacing preserved
    lines = []
    for tag in soup.find_all(True):
        text = tag.get_text(strip=True)
        # FIX: Allow single/double digits if they are numbers (like ratings), or any text > 0 chars
        if (text and (len(text) > 0) or (text.isdigit())): 
            classes = ' '.join(tag.get('class', []))
            lines.append(f"[{tag.name}.{classes}] {text[:200]}")

    unique_lines = []
    last_line = None
    for line in lines:
        if line != last_line:
            unique_lines.append(line)
            last_line = line

    return '\n'.join(unique_lines)[:CLEAN_CHAR_LIM]


def extract_with_ai(html, url, fields):
    """
    Send cleaned HTML to Gemini and ask it to extract data directly.
    Returns a list of dicts or None if it fails.
    """
    try:
        cleaned = clean_html(html)
        
        if len(cleaned) == CLEAN_CHAR_LIM:
            print(f'Cleaned content character limit reached or exceeded')
        else:
            print(f"Cleaned content length: {len(cleaned)} characters")
        
        print(f"Estimated items in content: {cleaned.count('[div.')}")

        prompt = f"""You are a data extraction expert. Extract ALL instances of structured data from this webpage HTML.

URL: {url}
Fields to extract: {', '.join(fields)}

Webpage HTML:
{cleaned}

Instructions:
- Find ALL repeated items on the page that contain these fields, not just the first one
- Each item should have all the requested fields
- If a field is missing for an item, use null. Try to avoid using null, and keep searching for a bit until you find it or until you are sure it doesn't exist
- Return ONLY a raw JSON array, no explanation, no markdown, no code fences

Format Example:
[
  {{"field1": "value", "field2": "value"}},
  {{"field1": "value", "field2": "value"}}
]
Return ALL item matches that you find.
"""

        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown fences if Gemini adds them anyway
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1]
            raw = raw.rsplit('```', 1)[0]

        data = json.loads(raw.strip())

        if isinstance(data, list) and len(data) > 0:
            print(data)
            return data
        return None

    except Exception as e:
        print(f"AI extraction failed: {e}")
        return None


def extract_with_selectors(html, container, selectors):
    """
    Fallback: CSS selector approach using BeautifulSoup.
    Used when AI fails or user provides manual selectors.
    """
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
    """Block internal network URLs"""
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


def secure_response(data, status=200):
    """Wrap jsonify response with security headers"""
    resp = make_response(jsonify(data), status)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Content-Security-Policy'] = "default-src 'self' fonts.googleapis.com fonts.gstatic.com; script-src 'self' 'unsafe-inline'"
    return resp


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        data = request.json
        url = data.get('url', '').strip()
        fields = data.get('fields', [])
        container = data.get('container', '')
        selectors = data.get('selectors', {})

        # Validate
        if not url:
            return secure_response({'success': False, 'error': 'URL is required'}, 400)

        if not url.startswith(('http://', 'https://')):
            return secure_response({'success': False, 'error': 'URL must start with http:// or https://'}, 400)

        if not is_url_safe(url):
            return secure_response({'success': False, 'error': 'That URL is not allowed'}, 400)
        
        if not fields and not (container and selectors):
            return secure_response({'success': False, 'error': 'Provide fields for AI or manual selectors'}, 400)

        # Fetch
        try:
            html = fetch_page(url)
        except Exception as e:
            return secure_response({'success': False, 'error': f'Could not fetch page: {str(e)}'}, 400)

        items = None
        method = None

        # Try AI first if fields provided
        if fields:
            items = extract_with_ai(html, url, fields)
            if items is not None:
                method = 'ai'

        # Fall back to selectors
        if items is None and container and selectors:
            items = extract_with_selectors(html, container, selectors)
            method = 'selectors'

        if not items:
            return secure_response({'success': False, 'error': 'No data found — try manual selectors or a different URL'}, 500)

        return secure_response({
            'success': True,
            'count': len(items),
            'data': items,
            'url': url,
            'method': method
        })

    except Exception as e:
        return secure_response({'success': False, 'error': str(e)}, 500)


if __name__ == "__main__":
    app.run(debug=True, port=5000)