import os
import sys
import json
import requests
from datetime import datetime

# --- CONFIGURATION ---
GATEWAY_URL = "http://localhost:18789"
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"

def call_gateway(tool, action, params):
    """Calls OpenClaw Gateway tool API"""
    url = f"{GATEWAY_URL}/tool/{tool}/{action}"
    try:
        response = requests.post(url, json=params, timeout=60)
        return response.json()
    except Exception as e:
        print(f"Error calling gateway: {e}")
        return None

def get_notion_items(db_id):
    """Fetches existing items from Notion database"""
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    items = {}
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor
            
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            print(f"Error fetching Notion: {res.text}")
            break
            
        data = res.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            # Use 'URL источника' as unique key
            url_prop = props.get("URL источника", {}).get("url")
            if url_prop:
                items[url_prop] = page["id"]
        
        has_more = data.get("has_more")
        next_cursor = data.get("next_cursor")
        
    return items

def scrape_idealista(url):
    """Uses OpenClaw Browser to scrape Idealista page"""
    print(f"Opening browser for: {url}")
    # 1. Open page
    res_open = call_gateway("browser", "open", {"targetUrl": url, "profile": "openclaw"})
    if not res_open or "targetId" not in res_open:
        print("Failed to open browser.")
        return []
    
    target_id = res_open["targetId"]
    
    # 2. Wait a bit for JS
    import time
    time.sleep(5)
    
    # 3. Take snapshot
    res_snap = call_gateway("browser", "snapshot", {"targetId": target_id, "profile": "openclaw"})
    if not res_snap or "snapshot" not in res_snap:
        print("Failed to take snapshot.")
        return []
    
    # Simple parsing logic based on AXTree structure
    # In a real skill, this should be more robust
    snapshot = res_snap["snapshot"]
    listings = []
    
    # We look for "article" or links with /inmueble/
    # This is a simplified heuristic
    import re
    
    # Finding IDs and Titles
    # AXTree usually has 'link "Text" [ref=...] { /url: ... }'
    # We'll use regex to find inmueble URLs
    matches = re.findall(r'link\s+"(.*?)"\s+.*?/url:\s+(/.*?/inmueble/(\d+)/)', snapshot)
    
    unique_ids = set()
    for title, full_url, item_id in matches:
        if item_id in unique_ids: continue
        unique_ids.add(item_id)
        
        listings.append({
            "id": item_id,
            "title": title,
            "url": f"https://www.idealista.com{full_url}",
            "price": 0 # TODO: extract price from AXTree
        })
        
    print(f"Found {len(listings)} listings.")
    return listings

def sync(target_url, db_id):
    notion_items = get_notion_items(db_id)
    web_items = scrape_idealista(target_url)
    
    # 1. Add new
    for item in web_items:
        if item["url"] not in notion_items:
            print(f"Adding new listing: {item['title']}")
            add_to_notion(db_id, item)
        else:
            print(f"Existing: {item['title']}")
            
    # 2. Archive removed (Optional logic)
    # web_urls = [i["url"] for i in web_items]
    # for url, page_id in notion_items.items():
    #     if url not in web_urls:
    #         print(f"Archiving: {url}")
    #         # update_notion_status(page_id, "Archive")

def add_to_notion(db_id, item):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    payload = {
        "parent": { "database_id": db_id },
        "properties": {
            "Полное имя": { "title": [ { "text": { "content": item["title"] } } ] },
            "URL источника": { "url": item["url"] },
            "Где": { "multi_select": [ { "name": "Валенсия" } ] },
            "Источник": { "select": { "name": "Таргет" } }
        }
    }
    
    res = requests.post(url, headers=headers, json=payload)
    if res.status_code != 200:
        print(f"Error adding to Notion: {res.text}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sync.py <url> <db_id>")
        sys.exit(1)
    sync(sys.argv[1], sys.argv[2])
