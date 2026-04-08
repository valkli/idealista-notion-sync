import sys
import json
import subprocess
import time

URL = "https://www.idealista.com/ru/pro/knelitevalencia/venta-viviendas/valencia-provincia/"

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
            
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    try:
        # manual parsing to find json block
        lines = result.stdout.strip().split('\n')
        json_str = ""
        start = False
        for line in lines:
            if line.strip().startswith('{'): start = True
            if start: json_str += line + "\n"
        return json.loads(json_str) if json_str else {}
    except:
        return {}

def main():
    print(f"Opening {URL}...")
    res = call_gateway("browser", "open", {"targetUrl": URL, "profile": "openclaw"})
    if "targetId" not in res:
        print("Failed to open")
        return

    tid = res["targetId"]
    time.sleep(5)
    
    print("Snapshotting...")
    res_snap = call_gateway("browser", "snapshot", {"targetId": tid, "profile": "openclaw"})
    snap = res_snap.get("snapshot", "")
    
    with open("snapshot_debug.txt", "w", encoding="utf-8") as f:
        f.write(snap)
        
    print(f"Saved snapshot to snapshot_debug.txt ({len(snap)} chars)")
    
    # Check regex
    import re
    matches = re.findall(r'link\s+"(.*?)"\s+.*?/url:\s+(/.*?/inmueble/(\d+)/)', snap)
    print(f"Matches found: {len(matches)}")

if __name__ == "__main__":
    main()
