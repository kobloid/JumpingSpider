from flask import Flask, jsonify, request, render_template
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import google.generativeai as genai
import requests
import os
import json

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=api_key)

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.json

    url = data.get('url')
    container = data.get('container')
    selectors = data.get('selectors')

    if not url or not container or not selectors:
        return jsonify({'success': False, 'error': 'Not all elements given'}), 400

    if not url.startswith(('http://', 'https://')):
        return jsonify({'success': False, 'error': 'page may not be secure'}), 400

    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not fetch page: {str(e)}'}), 400

    soup = BeautifulSoup(response.content, 'html.parser')
    containers = soup.select(container)
    items = []

    for c in containers:
        item_data = {}
        for field, selector in selectors.items():
            element = c.select_one(selector)
            item_data[field] = element.get_text(strip=True) if element else None
        items.append(item_data)

    return jsonify({
        'success': True,
        'count': len(items),
        'data': items,
        'url': url
    })


def get_page_structure(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        elements = []
        for tag in soup.find_all(True, limit=100):
            if tag.get('class') or tag.get('id'):
                elements.append(
                    f"- {tag.name} (class: '{' '.join(tag.get('class', []))}', id: '{tag.get('id', '')}'): {tag.get_text(strip=True)[:60]}"
                )

        return '\n'.join(elements[:50])
    except Exception as e:
        return None


@app.route('/analyze-page', methods=['POST'])
def analyze_page():
    try:
        data = request.json
        url = data.get('url', '').strip()
        fields = data.get('fields', [])

        if not url or not fields:
            return jsonify({'success': False, 'error': 'URL and fields are required'}), 400

        if not url.startswith(('http://', 'https://')):
            return jsonify({'success': False, 'error': 'URL must start with http:// or https://'}), 400

        structure = get_page_structure(url)
        if not structure:
            return jsonify({'success': False, 'error': 'Could not fetch page'}), 400

        prompt = f"""You are a web scraping expert. Analyze this HTML structure and return CSS selectors.

URL: {url}

HTML elements on the page:
{structure}

The user wants to extract these fields: {', '.join(fields)}

Return ONLY a JSON object, no explanation, no markdown, just the raw JSON:
{{
  "container": "the selector that wraps each repeated item",
  "selectors": {{
    "field_name": "css selector for that field"
  }}
}}"""

        model = genai.GenerativeModel('gemini-3.5-flash')
        response = model.generate_content(prompt)
        raw = response.text.strip()

        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1]
            raw = raw.rsplit('```', 1)[0]

        suggestions = json.loads(raw.strip())

        return jsonify({'success': True, 'suggestions': suggestions})

    except json.JSONDecodeError:
        return jsonify({'success': False, 'error': 'AI returned invalid JSON', 'raw': raw}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)