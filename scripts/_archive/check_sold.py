import os
import sys
import requests
import re
import json
import subprocess
import time

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59"
GATEWAY_URL = "http://127.0.0.1:18789"

sys.stdout.reconfigure(encoding='utf-8')

def get_notion_agency_props(agency_domain):
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    items = {}
    has_more = True
    next_cursor = None
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        res = requests.post(url, headers=headers, json=payload)
        data = res.json()
        for page in data.get("results", []):
            map_url = page["properties"].get("Map", {}).get("url")
            if map_url and agency_domain in map_url:
                name = ""
                title_arr = page["properties"].get("Name", {}).get("title", [])
                if title_arr:
                    name = title_arr[0].get("plain_text", "")
                items[map_url] = {"page_id": page["id"], "name": name}
        has_more = data.get("has_more")
        next_cursor = data.get("next_cursor")
    return items

def get_live_listings(agency_url):
    """Get current active listing URLs from Idealista via browser snapshot"""
    cmd = ["openclaw.cmd", "browser", "--browser-profile", "openclaw", "open", "--json", agency_url]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
    if result.returncode != 0:
        print(f"Error opening browser: {result.stderr}")
        return set(), None
    
    try:
        lines = result.stdout.strip().split('\n')
        json_str = ""
        start_json = False
        for line in lines:
            if line.strip().startswith('{'):
                start_json = True
            if start_json:
                json_str += line + "\n"
        data = json.loads(json_str)
        target_id = data.get("targetId")
    except Exception as e:
        print(f"Error parsing open response: {e}")
        return set(), None

    time.sleep(5)

    # Snapshot
    cmd2 = ["openclaw.cmd", "browser", "--browser-profile", "openclaw", "snapshot", "--json", "--target-id", target_id]
    result2 = subprocess.run(cmd2, capture_output=True, text=True, encoding='utf-8', timeout=60)
    
    live_urls = set()
    if result2.returncode == 0:
        try:
            lines = result2.stdout.strip().split('\n')
            json_str = ""
            start_json = False
            for line in lines:
                if line.strip().startswith('{'):
                    start_json = True
                if start_json:
                    json_str += line + "\n"
            snap_data = json.loads(json_str)
            snap_content = snap_data.get("snapshot", "")
            matches = re.findall(r'/url:\s+(/(?:ru/)?pro/.+?/inmueble/(\d+)/)', snap_content)
            for full_url, item_id in matches:
                live_urls.add(f"https://www.idealista.com{full_url}")
            print(f"Found {len(live_urls)} live listings on Idealista")
        except Exception as e:
            print(f"Error parsing snapshot: {e}")

    # Close browser tab
    cmd3 = ["openclaw.cmd", "browser", "--browser-profile", "openclaw", "close", "--json", target_id]
    subprocess.run(cmd3, capture_output=True, text=True, encoding='utf-8', timeout=30)
    
    return live_urls, target_id

def archive_notion_page(page_id, name):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    res = requests.patch(url, headers=headers, json={"archived": True})
    if res.status_code == 200:
        print(f"Archived (sold): {name}")
        return True
    else:
        print(f"Failed to archive {name}: {res.text}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_sold.py <agency_url>")
        sys.exit(1)
    
    agency_url = sys.argv[1]
    
    # Extract domain slug from URL
    match = re.search(r'/pro/([^/]+)/', agency_url)
    agency_domain = match.group(1) if match else ""
    print(f"Agency domain: {agency_domain}")
    
    # Get Notion properties for this agency
    notion_props = get_notion_agency_props(agency_domain)
    print(f"Notion properties for this agency: {len(notion_props)}")
    
    if not notion_props:
        print("No Notion properties found for this agency, skipping cleanup.")
        sys.exit(0)
    
    # Get live listings
    live_urls, _ = get_live_listings(agency_url)
    
    # Find sold (in Notion but not on Idealista)
    removed = 0
    for notion_url, info in notion_props.items():
        if notion_url not in live_urls:
            print(f"SOLD/REMOVED: {info['name']} -> {notion_url}")
            if archive_notion_page(info["page_id"], info["name"]):
                removed += 1
    
    print(f"\nCleanup complete. Archived {removed} sold properties.")
    # Output for parsing
    print(f"REMOVED_COUNT:{removed}")
