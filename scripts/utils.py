import os
import sys
import json
import time
import random
import re
import requests
from datetime import datetime

# --- CONFIGURATION ---
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59" # Residential Properties

# Since we can't call gateway via HTTP easily from here, 
# this script will output ACTIONS for the agent to perform 
# OR we assume the agent runs the logic and calls Notion API directly.

def get_notion_urls():
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    items = {}
    try:
        res = requests.post(url, headers=headers, json={"page_size": 100})
        if res.status_code == 200:
            for page in res.json().get("results", []):
                url_prop = page["properties"].get("Map", {}).get("url")
                if url_prop: items[url_prop] = page["id"]
    except: pass
    return items

def parse_snapshot(snapshot):
    """Extracts property details from a detail page snapshot"""
    details = {}
    # Heuristics
    price_match = re.search(r'(\d+[\.\s]\d+)\s?€', snapshot)
    if price_match: details["price"] = int(re.sub(r'[\.\s]', '', price_match.group(1)))
    
    area_match = re.search(r'(\d+)\s?м²', snapshot)
    if area_match: details["area"] = int(area_match.group(1))
    
    rooms_match = re.search(r'(\d+)\s?комн', snapshot)
    if rooms_match: details["rooms"] = int(rooms_match.group(1))
    
    bath_match = re.search(r'(\d+)\s?сан узел', snapshot)
    if bath_match: details["bathrooms"] = int(bath_match.group(1))
    
    floor_match = re.search(r'(\d+)\s?этаж', snapshot)
    if floor_match: details["floor"] = int(floor_match.group(1))
    
    return details

def add_to_notion(title, url, details):
    notion_url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    properties = {
        "Name": { "title": [ { "text": { "content": title } } ] },
        "Map": { "url": url }
    }
    
    if "price" in details: properties["Price"] = {"number": details["price"]}
    if "area" in details: properties["Area (m²)"] = {"number": details["area"]}
    if "rooms" in details: properties["Bedrooms No."] = {"number": details["rooms"]}
    if "bathrooms" in details: properties["Bathroom No."] = {"number": details["bathrooms"]}
    if "floor" in details: properties["Этаж"] = {"number": details["floor"]}

    res = requests.post(notion_url, headers=headers, json={
        "parent": { "database_id": DB_ID },
        "properties": properties
    })
    return res.status_code == 200

if __name__ == "__main__":
    # This part is just for the agent to use as a library or via exec
    pass
