import requests
from bs4 import BeautifulSoup
import json
import time

SENTINAL = 'STOPEU'

def scrape_website(url, selectors, container_selector=None):
    """
    Scrape a website and extract data using CSS selectors
    
    Args:
        url: The webpage URL to scrape
        selectors: Dictionary of {field_name: css_selector}
        container_selector: If provided, scrapes multiple items (e.g., 'div.quote')
    
    Returns:
        Dictionary of scraped data or list of items
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # If container selector provided, scrape multiple items
        if container_selector:
            containers = soup.select(container_selector)
            items = []
            for container in containers:
                item_data = {}
                for field, selector in selectors.items():
                    element = container.select_one(selector)
                    if element:
                        item_data[field] = element.get_text(strip=True)
                    else:
                        item_data[field] = None
                items.append(item_data)
            return {'url': url, 'items': items, 'count': len(items)}
        else:
            # Single item mode
            data = {'url': url}
            for field, selector in selectors.items():
                element = soup.select_one(selector)
                if element:
                    data[field] = element.get_text(strip=True)
                else:
                    data[field] = None
            return data
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None


def scrape_all_items(url, selectors, container_selector):
    """
    Scrape ALL items from a single webpage
    
    Args:
        url: The webpage URL to scrape
        selectors: Dictionary of {field_name: css_selector}
        container_selector: Selector that wraps each item (e.g., 'div.quote')
    
    Returns:
        List of all items found on the page
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all containers
        containers = soup.select(container_selector)
        items = []
        
        # Extract data from each container
        for container in containers:
            item_data = {}
            for field, selector in selectors.items():
                element = container.select_one(selector)
                if element:
                    item_data[field] = element.get_text(strip=True)
                else:
                    item_data[field] = None
            items.append(item_data)
        
        if len(items) > 0:
            print(f"Found {len(items)} items on {url}")
            return items
        else:
            print(f"No data was found on {url}. Maybe input error?")
            return False
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []


def scrape_multiple(urls, selectors, container_selector=None, delay=1):
    """Scrape multiple URLs"""
    results = []
    for i, url in enumerate(urls, 1):
        print(f"Scraping {i}/{len(urls)}: {url}")
        data = scrape_website(url, selectors, container_selector)
        if data:
            results.append(data)
        time.sleep(delay)
    return results


def save_results(url, data, filename):
    """Save results to a file"""
    output = {
        'source_url': url,
        'data': data
    }

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"Saved to {filename}")
    except Exception as e:
        print(f'Error saving {filename}: {e}')
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                if 'null' in line:
                    line = ''
    except FileNotFoundError:
        print('Error: The file was not found.')
    except Exception as e:
        print(f'An error occured: {e}')
    

def add_selectors(selectors_dict):
    '''
    Adds selectors to the dictionary of selectors
    '''
    while True:
        s1 = input('Selector Key ')
        if s1 == 'q':
            break
        s2 = input('Selector Value ')
        if s2 == 'q':
            break
        selectors_dict[s1] = s2
    
    for key in selectors_dict:
            if key == '' or key == None:
                del selectors_dict[key]
    
    return selectors_dict


def single_url():
    url = input('URL to scrape ')
    selectors = {}
    selectors = add_selectors(selectors)
            
    container = input('Please enter container ')
    scraped = scrape_all_items(url, selectors, container)

    if scraped is not None:
        filename = input('Name of save file> ')
        save_results(url, scraped, filename)


#initial CLI version
"""
if __name__ == '__main__':
    print(f"{'=' * 28}\nThis web scraper is so good\n{'=' * 28}")
    print('\n**This is still a work in progress,\n  There may be unexpected errors**')
    print()

    uinput = ''
    while uinput != SENTINAL:
        uinput = input("Do you want to scrape multiple URL's? ")

        if uinput == 'n':
            single_url()  
            exit

        elif uinput == 'y':
            urls = []
            i = 0
            while True:
                i += 1
                url_input = input(f'URL #{i} ')
                
                if url_input == 'q':
                    break
                else:
                    urls.append(url_input)
            
            if len(urls) > 1:
                selectors = {}
                selectors = add_selectors(selectors)

                container = input('Please enter container ')
                scraped = scrape_multiple(urls, selectors, delay=1)

                if scraped is not None:
                    filename = input('Name of save file> ')
                    save_results(urls, scraped, filename)
            elif len(urls) == 1:
                single_url()
            else:
                print('Please enter more than 1 URL')
                break
        else:
            print('(y or n)')
"""


'''
# ============= OTHER EXAMPLES =============

# Example 1: Scrape a single page
print("Example 1: Single page")
selectors = {
    'title': 'h1',
    'description': 'p'
}
result = scrape_website('https://example.com', selectors)
print(json.dumps(result, indent=2))

# Example 2: Scrape multiple pages
print("\nExample 2: Multiple pages")
urls = [
    'https://example.com/page1',
    'https://example.com/page2'
]
results = scrape_multiple(urls, selectors, delay=1)
save_results(results, 'scraped_data.json')

# Example 3: Scrape quotes.toscrape.com (MULTIPLE quotes per page)
print("\nExample 3: Quotes website")
quote_selectors = {
    'quote': 'span.text',
    'author': 'small.author',
    'tags': 'a.tag'
}
quote_urls = [
    'http://quotes.toscrape.com/page/1/',
    'http://quotes.toscrape.com/page/2/'
]
# Use container_selector to get ALL quotes on each page
quotes = scrape_multiple(quote_urls, quote_selectors, container_selector='div.quote', delay=1)
save_results(quotes, 'quotes.json')
print(f"Total quotes scraped: {sum(q['count'] for q in quotes)}")
'''