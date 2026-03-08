import os
import sys
import json
import time
import random
import re
import requests
from datetime import datetime, timedelta

# Fix encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIGURATION ---
GATEWAY_URL = "http://127.0.0.1:18789"
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59" # Residential Properties

import subprocess

def call_gateway(tool, action, params):
    if tool != "browser":
        print(f"Tool {tool} not supported via CLI bridge")
        return None

    cmd = ["openclaw.cmd", "browser"]
    
    # Check for profile (e.g. 'openclaw' vs 'chrome')
    # The CLI flag is --browser-profile <name>
    if "profile" in params:
        cmd.extend(["--browser-profile", params["profile"]])
    
    if action == "open":
        cmd.extend(["open", "--json", params["targetUrl"]])
    elif action == "snapshot":
        cmd.extend(["snapshot", "--json"])
        if "targetId" in params:
            cmd.extend(["--target-id", params["targetId"]])
    elif action == "act":
        cmd.extend(["act", "--json"])
        req = {}
        if "kind" in params: req["kind"] = params["kind"]
        if "targetId" in params: req["targetId"] = params["targetId"]
        if "fn" in params: req["fn"] = params["fn"]
        cmd.append(json.dumps(req))
    elif action == "close":
        cmd.extend(["close", "--json"])
        if "targetId" in params:
            cmd.append(params["targetId"])
    else:
        print(f"Action {action} not supported via CLI bridge")
        return None

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
        if result.returncode != 0:
            print(f"CLI Error: {result.stderr}")
            return None
        try:
            # Find JSON block in output
            lines = result.stdout.strip().split('\n')
            json_str = ""
            start_json = False
            for line in lines:
                if line.strip().startswith('{'):
                    start_json = True
                if start_json:
                    json_str += line + "\n"
            
            if json_str:
                return json.loads(json_str)
            else:
                return json.loads(result.stdout) # fallback
        except json.JSONDecodeError:
            # Fallback for non-JSON output if any
            print(f"CLI Output (non-JSON): {result.stdout}")
            return {"output": result.stdout}
    except Exception as e:
        print(f"Error calling CLI: {e}")
        return None

def get_notion_urls():
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
        if next_cursor: payload["start_cursor"] = next_cursor
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200: break
        data = res.json()
        for page in data.get("results", []):
            # Property: Map or Description might contain the original URL
            # For this database, let's assume we use a property called "URL источника" if it exists,
            # or we check the description for the link.
            # Looking at the schema I got, there isn't a dedicated URL property besides 'Map'.
            # I will assume 'Map' stores the Idealista link for now.
            url_prop = page["properties"].get("Map", {}).get("url")
            if url_prop: items[url_prop] = page["id"]
        has_more = data.get("has_more")
        next_cursor = data.get("next_cursor")
    return items

def scrape_property_details(target_id):
    """Extracts detailed info from a single property page"""
    print(f"Extracting details for {target_id}...")
    res = call_gateway("browser", "snapshot", {"targetId": target_id, "profile": "openclaw"})
    if not res or "snapshot" not in res: return {}
    
    snap = res["snapshot"]
    details = {}
    
    # Heuristics for Idealista detail page
    # Title (often the main heading)
    title_match = re.search(r'heading\s+"(.*?)"\s+\[level=1\]', snap)
    if title_match:
        details["title"] = title_match.group(1).strip()
    
    # Price
    price_match = re.search(r'(\d+[\.\s]\d+)\s?€', snap)
    if price_match:
        details["price"] = int(re.sub(r'[\.\s]', '', price_match.group(1)))
    
    # Area
    area_match = re.search(r'(\d+)\s?м²', snap)
    if area_match:
        details["area"] = int(area_match.group(1))
        
    # Rooms
    rooms_match = re.search(r'(\d+)\s?комн', snap)
    if rooms_match:
        details["rooms"] = int(rooms_match.group(1))

    # Bathrooms
    bath_match = re.search(r'(\d+)\s?ванн', snap)
    if bath_match:
        details["bathrooms"] = int(bath_match.group(1))

    return details

def process_agency(agency_url):
    print(f"Processing Agency: {agency_url}")
    notion_urls = get_notion_urls()
    print(f"Notion has {len(notion_urls)} existing URLs.")
    
    # 1. Open Agency Page
    res_open = call_gateway("browser", "open", {"targetUrl": agency_url, "profile": "openclaw"})
    if not res_open or "targetId" not in res_open: return
    main_target_id = res_open["targetId"]
    
    try:
        time.sleep(5)
        
        # 2. Get List of Property Links
        print("Taking agency snapshot...")
        res_snap = call_gateway("browser", "snapshot", {"targetId": main_target_id, "profile": "openclaw"})
        if not res_snap or "snapshot" not in res_snap: return
        
        print(f"Notion has {len(notion_urls)} existing URLs.")
        
        snap_content = res_snap.get("snapshot", "")
        print(f"Snapshot length: {len(snap_content)}")
        
        # IMPROVED REGEX: Capture only URL and ID first. We will get the Title from the detail page.
        # Matches: /url: /pro/agency-name/inmueble/12345/ OR /url: /ru/pro/agency-name/inmueble/12345/
        matches = re.findall(r'/url:\s+(/(?:ru/)?pro/.+?/inmueble/(\d+)/)', snap_content)
        
        print(f"Raw matches found: {len(matches)}")
        if len(matches) > 0:
            print(f"Sample match: {matches[0]}")
        
        unique_props = []
        seen_ids = set()
        for full_url, item_id in matches:
            full_abs_url = f"https://www.idealista.com{full_url}"
            
            # Check against seen_ids (current run) AND notion_urls (history)
            if item_id not in seen_ids and full_abs_url not in notion_urls:
                # We use a placeholder title; real title comes from detail scraping
                unique_props.append({"title": f"Property {item_id}", "url": full_abs_url, "id": item_id})
                seen_ids.add(item_id)

        print(f"Found {len(unique_props)} new properties to process.")
        
        # 3. Process each NEW property (Deep dive)
        for prop in unique_props: # Process all found properties
            print(f"Deep scraping: {prop['url']}")
            # Open property page
            res_prop = call_gateway("browser", "open", {"targetUrl": prop["url"], "profile": "openclaw"})
            if res_prop and "targetId" not in res_prop: continue
            
            time.sleep(random.uniform(3, 8)) # Random delay
            
            # Pass the ID to scrape details
            details = scrape_property_details(res_prop["targetId"])
            
            # If we got a better title from details, update it
            if "title" in details and details["title"]:
                prop["title"] = details["title"]
            
            # Add to Notion
            add_to_notion(prop, details)
            
            # Close property tab to save resources
            call_gateway("browser", "close", {"targetId": res_prop["targetId"]})
            
            time.sleep(random.uniform(5, 15)) # Longer delay between objects

    finally:
        # Close main agency tab at the end
        print("Closing main agency tab...")
        try:
            call_gateway("browser", "close", {"targetId": main_target_id})
        except Exception as e:
            print(f"Error closing tab: {e}")

def add_to_notion(prop, details):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    properties = {
        "Name": { "title": [ { "text": { "content": prop["title"] } } ] },
        "Map": { "url": prop["url"] }
    }
    
    if "price" in details: properties["Price"] = {"number": details["price"]}
    if "area" in details: properties["Area (m²)"] = {"number": details["area"]}
    if "rooms" in details: properties["Bedrooms No."] = {"number": details["rooms"]}
    if "bathrooms" in details: properties["Bathroom No."] = {"number": details["bathrooms"]}

    res = requests.post(url, headers=headers, json={
        "parent": { "database_id": DB_ID },
        "properties": properties
    })
    if res.status_code == 200:
        print(f"Added to Notion: {prop['title']}")
    else:
        print(f"Failed to add: {res.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python deep_sync.py <agency_url>")
        sys.exit(1)
    process_agency(sys.argv[1])
