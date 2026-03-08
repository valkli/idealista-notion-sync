import os
import requests
import sys
import json
import time
import re
import subprocess

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59"

AGENCY_URL = "https://www.idealista.com/ru/pro/knelitevalencia/venta-viviendas/valencia-provincia/"

def call_gateway(tool, action, params):
    cmd = ["openclaw.cmd", "browser"]
    if "profile" in params:
        cmd.extend(["--browser-profile", params["profile"]])
    
    if action == "open":
        cmd.extend(["open", "--json", params["targetUrl"]])
    elif action == "snapshot":
        cmd.extend(["snapshot", "--json"])
        if "targetId" in params:
            cmd.extend(["--target-id", params["targetId"]])
    elif action == "close":
        cmd.extend(["close", "--json"])
        if "targetId" in params:
            cmd.append(params["targetId"])
            
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        lines = result.stdout.strip().split('\n')
        json_str = ""
        start = False
        for line in lines:
            if line.strip().startswith('{'): start = True
            if start: json_str += line + "\n"
        return json.loads(json_str) if json_str else {}
    except:
        return {}

def get_live_ids():
    print(f"Scraping live URLs from {AGENCY_URL}...")
    res = call_gateway("browser", "open", {"targetUrl": AGENCY_URL, "profile": "openclaw"})
    if "targetId" not in res:
        print("Failed to open browser.")
        return set()
    
    tid = res["targetId"]
    time.sleep(5) 
    
    res_snap = call_gateway("browser", "snapshot", {"targetId": tid, "profile": "openclaw"})
    snap = res_snap.get("snapshot", "")
    
    matches = re.findall(r'/inmueble/(\d+)/', snap)
    live_ids = set(matches)
    
    print(f"Found {len(live_ids)} unique property IDs on the live page.")
    
    call_gateway("browser", "close", {"targetId": tid})
    return live_ids

def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    pages = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if next_cursor: payload["start_cursor"] = next_cursor
        
        try:
            res = requests.post(url, headers=headers, json=payload)
            data = res.json()
            pages.extend(data.get("results", []))
            has_more = data.get("has_more")
            next_cursor = data.get("next_cursor")
        except Exception as e:
            print(f"Error fetching pages: {e}")
            break
            
    return pages

def archive_page(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    try:
        requests.patch(url, headers=headers, json={"archived": True})
        print(f"Archived page {page_id}")
    except Exception as e:
        print(f"Error archiving {page_id}: {e}")

def main():
    live_ids = get_live_ids()
    if not live_ids:
        print("No live IDs found. Aborting.")
        return

    print(f"Live IDs: {live_ids}")

    pages = get_notion_pages()
    print(f"Notion has {len(pages)} pages.")

    archived_count = 0
    kept_count = 0
    
    for page in pages:
        props = page.get("properties", {})
        url_obj = props.get("Map", {}) or {}
        url_prop = url_obj.get("url")
        
        if not url_prop:
            continue
            
        match = re.search(r'/inmueble/(\d+)/', url_prop)
        if match:
            notion_id = match.group(1)
            if notion_id not in live_ids:
                print(f"Archiving old property: {notion_id} (Page {page['id']})")
                archive_page(page['id'])
                archived_count += 1
            else:
                kept_count += 1
        else:
            # Handle URLs that might not match regex (e.g. malformed)
            print(f"Skipping malformed URL: {url_prop}")

    print(f"Cleanup complete. Archived {archived_count}. Kept {kept_count}.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python full_sync_cleanup.py <agency_url>")
        sys.exit(1)
    
    AGENCY_URL = sys.argv[1]
    main()
