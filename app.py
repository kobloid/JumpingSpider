from flask import Flask, render_template, request, jsonify
from my_scraper import scrape_all_items

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    """Handle scraping requests"""
    try:
        data = request.json
        url = data.get('url')
        container = data.get('container')
        selectors_list = data.get('selectors', [])
        
        if not url or not container:
            return jsonify({
                'success': False,
                'error': 'URL and container are required'
            }), 400
        
        # Convert selectors list to dict
        selectors = {}
        for sel in selectors_list:
            key = sel.get('key')
            value = sel.get('value')
            attribute = sel.get('attribute')
            
            if key and value:
                if attribute:
                    selectors[key] = (value, attribute)
                else:
                    selectors[key] = value
        
        if not selectors:
            return jsonify({
                'success': False,
                'error': 'At least one selector is required'
            }), 400
        
        # Scrape the data
        items = scrape_all_items(url, selectors, container)
        
        return jsonify({
            'success': True,
            'count': len(items),
            'data': items,
            'url': url
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)