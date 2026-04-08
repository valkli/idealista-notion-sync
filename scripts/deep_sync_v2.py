"""
deep_sync_v2.py — полный синк Idealista → Notion
Извлекает все данные: цена, площадь, адрес, описание, фото, характеристики
Также умеет заполнять пустые страницы (--fill-empty)

Usage:
  python deep_sync_v2.py <agency_url>           # sync new listings
  python deep_sync_v2.py --fill-empty           # fill empty pages in Notion
  python deep_sync_v2.py <agency_url> --fill-empty  # both
"""

import os
import sys
import json
import time
import random
import re
import subprocess
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
NOTION_API_KEY = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_KEY")
NOTION_VERSION = "2022-06-28"
DB_ID = "21512f74-2f9e-8153-bdda-c3df73a32f59"  # Residential Properties

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

# --- JavaScript extractor for Idealista property page ---
EXTRACTOR_JS = r"""
(function() {
  const data = {};

  // 1. Title
  const h1 = document.querySelector('h1.main-info__title-main, h1[class*="title-main"], h1');
  data.title = h1 ? h1.textContent.trim() : document.title.split('|')[0].trim();

  // 2. Address
  const addrEl = document.querySelector('.main-info__title-minor, [class*="subtitle"], span[class*="location"]');
  data.address = addrEl ? addrEl.textContent.trim() : '';

  // 3. Price
  const priceEl = document.querySelector('.info-data-price span, [class*="price-container"] span, h3[class*="price"] span');
  if (priceEl) {
    data.price = parseInt(priceEl.textContent.replace(/[^\d]/g, '')) || 0;
  }
  // Fallback: meta og:price
  if (!data.price) {
    const og = document.querySelector('meta[property="og:description"]');
    if (og) {
      const m = og.content.match(/\b([\d.]+)\s*€/);
      if (m) data.price = parseInt(m[1].replace(/\./g, ''));
    }
  }

  // 4. Features (area, rooms, bathrooms, floor, terrace, pool, garage)
  data.features = {};
  document.querySelectorAll('.info-features span, li[class*="feature"]').forEach(el => {
    const t = el.textContent.trim();
    let m;
    if ((m = t.match(/^([\d,]+)\s*m²/))) data.features.area = parseInt(m[1].replace(',', ''));
    else if ((m = t.match(/^(\d+)\s+hab/i))) data.features.rooms = parseInt(m[1]);
    else if ((m = t.match(/^(\d+)\s+ba[ñn]/i))) data.features.bathrooms = parseInt(m[1]);
    else if ((m = t.match(/planta\s+(.+)/i))) data.features.floor = m[1].trim();
  });
  // Extended details
  document.querySelectorAll('.details-property-h3 ~ ul li, .details-property li, [class*="details"] li').forEach(li => {
    const t = li.textContent.trim();
    if (t.includes('Terraza')) data.features.terrace = true;
    if (t.includes('Piscina')) data.features.pool = true;
    if (t.includes('Garaje') || t.includes('Parking')) data.features.garage = true;
    if (t.includes('Ascensor')) data.features.elevator = true;
    if (t.includes('Aire acondicionado')) data.features.ac = true;
    if (t.includes('Calefacción') || t.includes('Calefaccion')) data.features.heating = true;
  });

  // 5. Description
  const descEl = document.querySelector('.adCommentsLanguage, #descriptionContainer, [class*="description-container"]');
  data.description = descEl ? descEl.textContent.trim().substring(0, 3000) : '';

  // 6. Photos — collect up to 15 unique high-res URLs
  const photos = [];
  const seen = new Set();
  const addPhoto = (src) => {
    if (!src || seen.has(src) || photos.length >= 15) return;
    // Upgrade to high-res format
    src = src.replace(/\/blur\/[^/]+\//, '/blur/WEB_DETAIL_TOP-L-L/');
    src = src.split('?')[0];  // remove query params
    if (src.includes('idealista.com')) {
      seen.add(src);
      photos.push(src);
    }
  };
  document.querySelectorAll('img[src*="idealista.com"]').forEach(img => addPhoto(img.src));
  document.querySelectorAll('img[data-src*="idealista.com"]').forEach(img => addPhoto(img.dataset.src));
  document.querySelectorAll('source[srcset*="idealista.com"]').forEach(s => {
    s.srcset.split(',').forEach(part => addPhoto(part.trim().split(' ')[0]));
  });
  // Try to find photos in JSON data on page
  const bodyHtml = document.body.innerHTML;
  const photoMatches = bodyHtml.matchAll(/id\.pro\.es\.image\.master\/([a-zA-Z0-9]+)\.jpg/g);
  for (const m of photoMatches) {
    addPhoto(`https://img4.idealista.com/blur/WEB_DETAIL_TOP-L-L/0/id.pro.es.image.master/${m[1]}.jpg`);
  }
  data.photos = photos;

  // 7. Property type & condition
  const bodyText = document.body.innerText.toLowerCase();
  data.tipo = '';
  if (/\bpiso\b/.test(bodyText)) data.tipo = 'Piso';
  else if (/\bchalet\b|\bvilla\b/.test(bodyText)) data.tipo = 'Chalet';
  else if (/\bcasa\b/.test(bodyText)) data.tipo = 'Casa';
  else if (/\blocal\b/.test(bodyText)) data.tipo = 'Local';
  else if (/\bterreno\b|\bsolar\b/.test(bodyText)) data.tipo = 'Solar';

  data.condition = '';
  if (/a reformar|para reformar|necesita reforma/.test(bodyText)) data.condition = 'Needs Renovation';
  else if (/obra nueva|primera ocupaci[oó]n|nuevo|a estrenar/.test(bodyText)) data.condition = 'New';
  else if (/reformad|buen estado|excelente estado/.test(bodyText)) data.condition = 'Good';

  // 8. Coordinates
  const coordM = document.body.innerHTML.match(/"latitude":([\d.]+),"longitude":([\d.-]+)/);
  if (coordM) data.coords = `${coordM[1]},${coordM[2]}`;

  // 9. Agency
  const agencyEl = document.querySelector('.advertiser-name, [class*="advertiser"] a, .logo-container span');
  data.agency = agencyEl ? agencyEl.textContent.trim() : '';

  // 10. Year built
  const yearM = document.body.innerText.match(/construido en\s+(\d{4})|año de construcci[oó]n[:\s]+(\d{4})/i);
  if (yearM) data.year_built = parseInt(yearM[1] || yearM[2]);

  return JSON.stringify(data);
})()
"""


# ==========================================
# BROWSER BRIDGE (CLI calls)
# ==========================================

def call_browser(action, params):
    cmd = ["openclaw.cmd", "browser"]
    if "profile" in params:
        cmd.extend(["--browser-profile", params["profile"]])
    cmd.append("--json")

    if action == "open":
        cmd.extend(["open", params["targetUrl"]])
    elif action == "snapshot":
        cmd.append("snapshot")
        if "targetId" in params:
            cmd.extend(["--target-id", params["targetId"]])
    elif action == "act":
        req = {k: params[k] for k in ["kind", "fn", "targetId"] if k in params}
        cmd.extend(["act", json.dumps(req)])
    elif action == "close":
        cmd.append("close")
        if "targetId" in params:
            cmd.append(params["targetId"])
    else:
        return None

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=90)
        if result.returncode != 0:
            print(f"  ⚠ Browser error: {result.stderr[:200]}")
            return None
        # Find JSON in output
        lines = result.stdout.strip().split('\n')
        json_lines = []
        capturing = False
        for line in lines:
            if line.strip().startswith('{'):
                capturing = True
            if capturing:
                json_lines.append(line)
        if json_lines:
            return json.loads('\n'.join(json_lines))
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        print(f"  ⚠ Browser call error: {e}")
        return None


def extract_property_data(target_id):
    """Extract all property data using JavaScript evaluation."""
    res = call_browser("act", {
        "targetId": target_id,
        "profile": "openclaw",
        "kind": "evaluate",
        "fn": EXTRACTOR_JS
    })
    if not res:
        return {}
    
    # Result may be in res["result"] or res["value"]
    raw = res.get("result") or res.get("value") or res.get("output") or ""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except:
            pass
    
    # Fallback: try snapshot-based parsing
    snap_res = call_browser("snapshot", {"targetId": target_id, "profile": "openclaw"})
    if snap_res and "snapshot" in snap_res:
        return parse_snapshot_fallback(snap_res["snapshot"])
    return {}


def parse_snapshot_fallback(snap):
    """Fallback parser from snapshot text."""
    data = {}
    
    # Title from heading level 1
    m = re.search(r'heading\s+"([^"]{10,100})"\s+\[level=1\]', snap)
    if m: data["title"] = m.group(1).strip()
    
    # Price
    m = re.search(r'([\d]{2,3}[.\s]\d{3}(?:[.\s]\d{3})?)\s*€', snap)
    if m: data["price"] = int(re.sub(r'[.\s]', '', m.group(1)))
    
    # Area
    m = re.search(r'(\d{2,4})\s*m²', snap)
    if m: data["features"] = data.get("features", {})
    if m: data["features"]["area"] = int(m.group(1))
    
    # Rooms (habitaciones)
    m = re.search(r'(\d)\s+habitaci', snap, re.I)
    if m:
        data.setdefault("features", {})
        data["features"]["rooms"] = int(m.group(1))
    
    # Bathrooms (baños)
    m = re.search(r'(\d)\s+ba[ñn]o', snap, re.I)
    if m:
        data.setdefault("features", {})
        data["features"]["bathrooms"] = int(m.group(1))
    
    # Photos from snapshot image references
    photos = re.findall(r'id\.pro\.es\.image\.master/([a-zA-Z0-9]+)\.jpg', snap)
    data["photos"] = [
        f"https://img4.idealista.com/blur/WEB_DETAIL_TOP-L-L/0/id.pro.es.image.master/{h}.jpg"
        for h in photos[:10]
    ]
    
    return data


# ==========================================
# NOTION HELPERS
# ==========================================

def notion_query_all(filter_body=None):
    """Get all pages from Notion DB."""
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    items = []
    has_more = True
    cursor = None
    while has_more:
        payload = {"page_size": 100}
        if filter_body: payload["filter"] = filter_body
        if cursor: payload["start_cursor"] = cursor
        res = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=30)
        if res.status_code != 200:
            print(f"  ⚠ Notion query error: {res.status_code} {res.text[:200]}")
            break
        data = res.json()
        items.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        cursor = data.get("next_cursor")
    return items


def get_existing_urls():
    """Get all Idealista URLs already in Notion."""
    pages = notion_query_all()
    urls = {}
    for page in pages:
        url = page["properties"].get("Map", {}).get("url") or \
              page["properties"].get("URL", {}).get("url")
        if url:
            urls[url] = page["id"]
    return urls


def get_empty_pages(limit=50):
    """Find pages that are missing key data (no price or no area)."""
    pages = notion_query_all()
    empty = []
    for page in pages:
        props = page["properties"]
        price = props.get("Price", {}).get("number")
        area = props.get("Area (m²)", {}).get("number")
        url = props.get("Map", {}).get("url") or props.get("URL", {}).get("url")
        
        if url and (price is None or area is None):
            empty.append({"notion_id": page["id"], "url": url, "has_price": price is not None, "has_area": area is not None})
    
    return empty[:limit]


def build_notion_properties(data):
    """Build Notion properties dict from extracted data."""
    features = data.get("features", {})
    props = {}

    # Name / Title
    title = data.get("title", "Sin título")
    if title:
        props["Name"] = {"title": [{"text": {"content": title[:200]}}]}

    # URL
    url = data.get("url")
    if url:
        props["Map"] = {"url": url}

    # Price
    price = data.get("price") or 0
    if price:
        props["Price"] = {"number": price}

    # Area
    area = features.get("area") or data.get("area") or 0
    if area:
        props["Area (m²)"] = {"number": area}

    # Rooms
    rooms = features.get("rooms") or data.get("rooms") or 0
    if rooms:
        props["Bedrooms No."] = {"number": rooms}

    # Bathrooms
    bathrooms = features.get("bathrooms") or data.get("bathrooms") or 0
    if bathrooms:
        props["Bathroom No."] = {"number": bathrooms}

    # Address (if field exists — rich_text)
    address = data.get("address", "")
    if address:
        props["Address"] = {"rich_text": [{"text": {"content": address[:200]}}]}

    return props


def build_notion_children(data):
    """Build page content blocks: photos + description + features."""
    children = []
    features = data.get("features", {})
    
    # Photos
    photos = data.get("photos", [])
    if photos:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📷 Фотографии"}}]}
        })
        for photo_url in photos[:12]:
            children.append({
                "object": "block",
                "type": "image",
                "image": {"type": "external", "external": {"url": photo_url}}
            })

    # Description
    desc = data.get("description", "").strip()
    if desc:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📝 Описание"}}]}
        })
        # Split into chunks of 2000 chars (Notion limit per block)
        for i in range(0, min(len(desc), 6000), 2000):
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": desc[i:i+2000]}}]}
            })

    # Characteristics
    char_lines = []
    if features.get("floor"): char_lines.append(f"🏢 Этаж: {features['floor']}")
    if features.get("terrace"): char_lines.append("🌿 Терраса: да")
    if features.get("pool"): char_lines.append("🏊 Бассейн: да")
    if features.get("garage"): char_lines.append("🚗 Гараж: да")
    if features.get("elevator"): char_lines.append("🛗 Лифт: да")
    if features.get("ac"): char_lines.append("❄️ Кондиционер: да")
    if features.get("heating"): char_lines.append("🔥 Отопление: да")
    if data.get("year_built"): char_lines.append(f"📅 Год: {data['year_built']}")
    if data.get("condition"): char_lines.append(f"🔧 Состояние: {data['condition']}")
    if data.get("tipo"): char_lines.append(f"🏠 Тип: {data['tipo']}")
    if data.get("agency"): char_lines.append(f"🏢 Агентство: {data['agency']}")
    if data.get("coords"): char_lines.append(f"📍 Координаты: {data['coords']}")

    if char_lines:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📋 Характеристики"}}]}
        })
        for line in char_lines:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line}}]}
            })

    return children


def add_to_notion(data):
    """Create new Notion page with full data."""
    props = build_notion_properties(data)
    children = build_notion_children(data)
    
    payload = {
        "parent": {"database_id": DB_ID},
        "properties": props
    }
    if children:
        payload["children"] = children[:100]  # Notion limit

    res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=30)
    if res.status_code in (200, 201):
        title = data.get("title", data.get("url", "?"))[:60]
        photos_count = len(data.get("photos", []))
        print(f"  ✅ Added: {title} | 💰{data.get('price',0):,}€ | 📷{photos_count} фото")
        return res.json().get("id")
    else:
        print(f"  ❌ Failed to add: {res.status_code} {res.text[:200]}")
        return None


def update_notion_page(page_id, data):
    """Update existing Notion page with new data."""
    props = build_notion_properties(data)
    children = build_notion_children(data)
    
    # Update properties
    res = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={"properties": props},
        timeout=30
    )
    if res.status_code not in (200, 201):
        print(f"  ❌ Props update failed: {res.status_code}")
        return False
    
    # Append content blocks (photos, description, features)
    if children:
        res2 = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": children[:100]},
            timeout=30
        )
        if res2.status_code not in (200, 201):
            print(f"  ⚠ Children append failed: {res2.status_code}")
    
    title = data.get("title", data.get("url", "?"))[:60]
    photos_count = len(data.get("photos", []))
    print(f"  🔄 Updated: {title} | 💰{data.get('price',0):,}€ | 📷{photos_count} фото")
    return True


# ==========================================
# MAIN SYNC LOGIC
# ==========================================

def get_property_urls_from_agency(main_target_id):
    """Get all property URLs from agency listing page."""
    print("  📸 Taking agency snapshot...")
    snap_res = call_browser("snapshot", {"targetId": main_target_id, "profile": "openclaw"})
    if not snap_res or "snapshot" not in snap_res:
        return []
    
    snap = snap_res["snapshot"]
    matches = re.findall(r'/url:\s+(/(?:ru/)?pro/.+?/inmueble/(\d+)/)', snap)
    
    unique = []
    seen_ids = set()
    for full_path, prop_id in matches:
        if prop_id not in seen_ids:
            unique.append({
                "url": f"https://www.idealista.com{full_path}",
                "id": prop_id
            })
            seen_ids.add(prop_id)
    
    print(f"  🏠 Found {len(unique)} property URLs on agency page")
    return unique


def process_agency(agency_url):
    """Sync new properties from an Idealista agency page."""
    print(f"\n{'='*60}")
    print(f"🏢 Syncing agency: {agency_url}")
    print(f"{'='*60}")
    
    existing_urls = get_existing_urls()
    print(f"📊 Notion has {len(existing_urls)} existing properties")
    
    # Open agency page
    res_open = call_browser("open", {"targetUrl": agency_url, "profile": "openclaw"})
    if not res_open or "targetId" not in res_open:
        print("❌ Failed to open agency page")
        return {"added": 0, "skipped": 0, "errors": 0}
    
    main_tid = res_open["targetId"]
    time.sleep(5)
    
    stats = {"added": 0, "skipped": 0, "errors": 0}
    
    try:
        prop_urls = get_property_urls_from_agency(main_tid)
        new_props = [p for p in prop_urls if p["url"] not in existing_urls]
        print(f"  ✨ New properties to add: {len(new_props)} (skipping {len(prop_urls) - len(new_props)} existing)")
        
        for i, prop in enumerate(new_props, 1):
            print(f"\n  [{i}/{len(new_props)}] {prop['url']}")
            
            res_prop = call_browser("open", {"targetUrl": prop["url"], "profile": "openclaw"})
            if not res_prop or "targetId" not in res_prop:
                print("    ⚠ Failed to open property page")
                stats["errors"] += 1
                continue
            
            prop_tid = res_prop["targetId"]
            time.sleep(random.uniform(3, 6))
            
            # Extract all data via JavaScript
            data = extract_property_data(prop_tid)
            data["url"] = prop["url"]
            
            # Ensure we have at least the title
            if not data.get("title"):
                data["title"] = f"Propiedad {prop['id']}"
            
            if add_to_notion(data):
                stats["added"] += 1
            else:
                stats["errors"] += 1
            
            call_browser("close", {"targetId": prop_tid})
            time.sleep(random.uniform(8, 15))
        
        stats["skipped"] = len(prop_urls) - len(new_props)
    
    finally:
        call_browser("close", {"targetId": main_tid})
    
    print(f"\n📊 Agency sync done: +{stats['added']} added, {stats['skipped']} skipped, {stats['errors']} errors")
    return stats


def fill_empty_pages(limit=30):
    """Find and fill pages that are missing key data."""
    print(f"\n{'='*60}")
    print(f"🔍 Looking for empty pages in Notion...")
    print(f"{'='*60}")
    
    empty = get_empty_pages(limit)
    print(f"📋 Found {len(empty)} pages with incomplete data")
    
    if not empty:
        print("✅ All pages have data!")
        return {"filled": 0, "errors": 0}
    
    stats = {"filled": 0, "errors": 0}
    
    for i, page in enumerate(empty, 1):
        url = page["url"]
        notion_id = page["notion_id"]
        missing = []
        if not page["has_price"]: missing.append("цена")
        if not page["has_area"]: missing.append("площадь")
        
        print(f"\n  [{i}/{len(empty)}] Нет {', '.join(missing)}: {url[:70]}")
        
        res_prop = call_browser("open", {"targetUrl": url, "profile": "openclaw"})
        if not res_prop or "targetId" not in res_prop:
            print("    ⚠ Failed to open page")
            stats["errors"] += 1
            continue
        
        prop_tid = res_prop["targetId"]
        time.sleep(random.uniform(4, 7))
        
        data = extract_property_data(prop_tid)
        data["url"] = url
        
        if data.get("price") or data.get("features", {}).get("area"):
            if update_notion_page(notion_id, data):
                stats["filled"] += 1
            else:
                stats["errors"] += 1
        else:
            print(f"    ⚠ Could not extract data from page (may be deleted)")
            stats["errors"] += 1
        
        call_browser("close", {"targetId": prop_tid})
        time.sleep(random.uniform(5, 12))
    
    print(f"\n📊 Fill-empty done: {stats['filled']} updated, {stats['errors']} errors")
    return stats


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    if not NOTION_API_KEY:
        print("❌ NOTION_API_KEY not set")
        sys.exit(1)
    
    args = sys.argv[1:]
    do_fill_empty = "--fill-empty" in args
    agency_url = next((a for a in args if a.startswith("http")), None)
    
    if not agency_url and not do_fill_empty:
        print("Usage:")
        print("  python deep_sync_v2.py <agency_url>")
        print("  python deep_sync_v2.py --fill-empty")
        print("  python deep_sync_v2.py <agency_url> --fill-empty")
        sys.exit(1)
    
    total_stats = {"added": 0, "skipped": 0, "errors": 0, "filled": 0}
    
    if agency_url:
        s = process_agency(agency_url)
        total_stats["added"] += s["added"]
        total_stats["skipped"] += s["skipped"]
        total_stats["errors"] += s["errors"]
    
    if do_fill_empty:
        s = fill_empty_pages(limit=30)
        total_stats["filled"] = s["filled"]
        total_stats["errors"] += s["errors"]
    
    # Output JSON for cron to parse
    print(f"\n__RESULT__")
    print(json.dumps(total_stats))
