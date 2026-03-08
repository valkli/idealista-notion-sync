import os
import requests
import sys

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59" # Residential Properties

def get_all_pages():
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    all_pages = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if next_cursor: payload["start_cursor"] = next_cursor
        
        try:
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code != 200:
                print(f"Error fetching pages: {res.text}")
                break
            
            data = res.json()
            all_pages.extend(data.get("results", []))
            has_more = data.get("has_more")
            next_cursor = data.get("next_cursor")
        except Exception as e:
            print(f"Exception: {e}")
            break
            
    return all_pages

def archive_page(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    try:
        res = requests.patch(url, headers=headers, json={"archived": True})
        if res.status_code == 200:
            print(f"Archived page {page_id}")
            return True
        else:
            print(f"Failed to archive {page_id}: {res.text}")
            return False
    except Exception as e:
        print(f"Exception archiving {page_id}: {e}")
        return False

def main():
    print("Fetching all pages...")
    pages = get_all_pages()
    print(f"Found {len(pages)} total pages.")
    
    # Map URL -> List of Pages
    url_map = {}
    
    for page in pages:
        props = page.get("properties", {})
        # Assuming URL is stored in "Map" property which is a URL type
        # Based on previous scripts: "Map": { "url": prop["url"] }
        url_prop = props.get("Map", {}).get("url")
        
        if url_prop:
            if url_prop not in url_map:
                url_map[url_prop] = []
            url_map[url_prop].append(page)
    
    duplicates_removed = 0
    
    for url, page_list in url_map.items():
        if len(page_list) > 1:
            print(f"Found {len(page_list)} copies for {url}")
            # Keep the one created most recently (or oldest? Let's keep oldest to preserve history if any)
            # Actually, let's keep the NEWEST one as it might have more up-to-date scraped info
            # Sort by created_time desc
            page_list.sort(key=lambda x: x["created_time"], reverse=True)
            
            # Keep the first one (newest), archive the rest
            to_archive = page_list[1:]
            
            for p in to_archive:
                if archive_page(p["id"]):
                    duplicates_removed += 1
    
    print(f"Deduplication complete. Archived {duplicates_removed} duplicate pages.")

if __name__ == "__main__":
    main()
