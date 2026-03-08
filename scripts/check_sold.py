import os, requests, sys
sys.stdout.reconfigure(encoding='utf-8')

NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
NOTION_VERSION = '2022-06-28'
DB_ID = '21512f74-2f9e-8153-bdda-c3df73a32f59'

headers = {
    'Authorization': f'Bearer {NOTION_API_KEY}',
    'Notion-Version': NOTION_VERSION,
    'Content-Type': 'application/json'
}

agency_keyword = sys.argv[1] if len(sys.argv) > 1 else 'best-broker-real'
active_urls_file = sys.argv[2] if len(sys.argv) > 2 else None

# Get all properties from Notion
url = f'https://api.notion.com/v1/databases/{DB_ID}/query'
all_pages = []
has_more = True
next_cursor = None

while has_more:
    payload = {'page_size': 100}
    if next_cursor:
        payload['start_cursor'] = next_cursor
    res = requests.post(url, headers=headers, json=payload)
    data = res.json()
    all_pages.extend(data.get('results', []))
    has_more = data.get('has_more')
    next_cursor = data.get('next_cursor')

# Filter for this agency
agency_pages = []
for page in all_pages:
    map_url = page['properties'].get('Map', {}).get('url', '')
    if map_url and agency_keyword in map_url:
        name = ''
        title_prop = page['properties'].get('Name', {}).get('title', [])
        if title_prop:
            name = title_prop[0].get('text', {}).get('content', '')
        agency_pages.append({'id': page['id'], 'url': map_url, 'name': name})

print(f'Total Notion pages: {len(all_pages)}')
print(f'{agency_keyword} pages: {len(agency_pages)}')
for p in agency_pages:
    print(f'  PAGE: {p["name"]} | {p["url"]}')
