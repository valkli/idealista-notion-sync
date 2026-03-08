"""
cleanup_sold.py — Archives Notion properties that are no longer listed on Idealista.
Usage: python cleanup_sold.py <agency_url>
"""
import os, sys, json, re, time, subprocess, requests

sys.stdout.reconfigure(encoding='utf-8')

GATEWAY_URL = "http://127.0.0.1:18789"
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59"

def call_gateway(tool, action, params):
    if tool != "browser":
        return None
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
    else:
        return None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
        if result.returncode != 0:
            print(f"CLI Error: {result.stderr}")
            return None
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
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Error calling CLI: {e}")
        return None

def get_notion_agency_properties(agency_keyword):
    """Returns {url: page_id} for all Notion pages where URL contains agency_keyword"""
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
        if res.status_code != 200:
            print(f"Notion query error: {res.status_code} {res.text}")
            break
        data = res.json()
        for page in data.get("results", []):
            url_prop = page["properties"].get("Map", {}).get("url")
            if url_prop and agency_keyword in url_prop:
                items[url_prop] = page["id"]
        has_more = data.get("has_more")
        next_cursor = data.get("next_cursor")
    return items

def get_all_pages_from_idealista(agency_url):
    """Opens the agency page and all paginated pages; collects all listing URLs"""
    active_urls = set()
    
    # Open main agency page
    res_open = call_gateway("browser", "open", {"targetUrl": agency_url, "profile": "openclaw"})
    if not res_open or "targetId" not in res_open:
        print("Could not open browser for agency page")
        return active_urls
    
    target_id = res_open["targetId"]
    time.sleep(5)
    
    page_num = 1
    while True:
        print(f"  Scraping page {page_num}...")
        res_snap = call_gateway("browser", "snapshot", {"targetId": target_id, "profile": "openclaw"})
        if not res_snap or "snapshot" not in res_snap:
            break
        
        snap = res_snap["snapshot"]
        matches = re.findall(r'/url:\s+(/(?:ru/)?pro/.+?/inmueble/(\d+)/)', snap)
        for full_url, item_id in matches:
            active_urls.add(f"https://www.idealista.com{full_url}")
        
        # Check if there's a "next page" link
        next_match = re.search(r'/url:\s+(/' + '(?:ru/)?pro/.+?/venta-viviendas/.+?/pagina-(\d+)/)', snap)
        if next_match:
            next_page_num = int(next_match.group(2))
            if next_page_num > page_num:
                next_url = f"https://www.idealista.com{next_match.group(1)}"
                print(f"  Going to page {next_page_num}: {next_url}")
                # Navigate via evaluate/act to next page
                res_nav = call_gateway("browser", "open", {"targetUrl": next_url, "profile": "openclaw"})
                if res_nav and "targetId" in res_nav:
                    # Close old tab if different
                    if res_nav["targetId"] != target_id:
                        call_gateway("browser", "close", {"targetId": target_id})
                        target_id = res_nav["targetId"]
                time.sleep(5)
                page_num = next_page_num
            else:
                break
        else:
            break
    
    call_gateway("browser", "close", {"targetId": target_id})
    return active_urls

def archive_notion_page(page_id, url):
    api_url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    res = requests.patch(api_url, headers=headers, json={"archived": True})
    if res.status_code == 200:
        print(f"  Archived: {url}")
        return True
    else:
        print(f"  Failed to archive {url}: {res.text}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python cleanup_sold.py <agency_url>")
        sys.exit(1)
    
    agency_url = sys.argv[1]
    
    # Extract agency keyword from URL (e.g. "best-broker-real")
    m = re.search(r'/pro/([^/]+)/', agency_url)
    if not m:
        print("Could not extract agency keyword from URL")
        sys.exit(1)
    agency_keyword = m.group(1)
    print(f"Agency keyword: {agency_keyword}")
    
    # Step 1: Get Notion properties for this agency
    print("Querying Notion for agency properties...")
    notion_props = get_notion_agency_properties(agency_keyword)
    print(f"Found {len(notion_props)} properties in Notion for this agency")
    
    if not notion_props:
        print("No properties in Notion for this agency — nothing to clean up")
        print(f"REMOVED_COUNT=0")
        return
    
    # Step 2: Get active listings from Idealista
    print("Collecting active listings from Idealista...")
    active_urls = get_all_pages_from_idealista(agency_url)
    print(f"Found {len(active_urls)} active listings on Idealista")
    
    # Step 3: Find sold properties (in Notion but not on Idealista)
    sold = {url: pid for url, pid in notion_props.items() if url not in active_urls}
    print(f"Found {len(sold)} sold/removed properties to archive")
    
    # Step 4: Archive sold properties
    removed_count = 0
    for url, page_id in sold.items():
        if archive_notion_page(page_id, url):
            removed_count += 1
        time.sleep(0.3)
    
    print(f"REMOVED_COUNT={removed_count}")

if __name__ == "__main__":
    main()
