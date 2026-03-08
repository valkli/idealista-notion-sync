import sys
import json
import os
import random
import subprocess
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from skill_logger import log_skill_execution

# --- CONFIG ---
# Use absolute paths to avoid issues when running from cron
BASE_DIR = r"C:\Users\Val\.openclaw\workspace"
AGENCIES_FILE = os.path.join(BASE_DIR, "agencies_queue.json")
SYNC_SCRIPT = os.path.join(BASE_DIR, "idealista-notion-sync", "scripts", "deep_sync.py")
PYTHON_EXE = r"C:\Python314\python.exe"

def load_queue():
    if os.path.exists(AGENCIES_FILE):
        with open(AGENCIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_queue(queue):
    with open(AGENCIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

def schedule_next_run():
    # Schedule for tomorrow between 09:00 and 18:00 Madrid
    tomorrow = datetime.now() + timedelta(days=1)
    random_hour = random.randint(9, 18)
    random_minute = random.randint(0, 59)
    
    run_time = tomorrow.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)
    # Madrid is UTC+1
    run_time_iso = run_time.strftime("%Y-%m-%dT%H:%M:%S+01:00")
    
    print(f"SCHEDULING_NEXT_RUN: {run_time_iso}")
    
    # We use openclaw.cmd to schedule the next turn
    cmd = [
        "openclaw.cmd", "cron", "add", "--json",
        "--job", json.dumps({
            "name": "idealista_daily_sync",
            "schedule": { "kind": "at", "at": run_time_iso },
            "payload": {
                "kind": "systemEvent",
                "text": "System: Triggering daily Idealista sync rotation."
            },
            "sessionTarget": "main"
        })
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        print(f"Failed to schedule next run: {e}")

@log_skill_execution("Idealista_Master_Scheduler")
def main():
    queue = load_queue()
    if not queue:
        print("Queue empty. Nothing to do.")
        return
        
    # Pick the first agency
    target_url = queue.pop(0)
    print(f"STARTING_SYNC: {target_url}")
    
    # Run the deep sync script
    # We pass the Notion API key via env (it should be available in the environment)
    # or we can read it from secrets_registry.md here if needed.
    # For now, we assume it's set in the system or we'll let the agent trigger it.
    
    # Actually, the scheduler should just trigger the script.
    # To keep it simple, we'll just rotate the file and print the command for the agent to see.
    
    queue.append(target_url)
    save_queue(queue)
    
    print(f"ROTATION_COMPLETE. Next up: {queue[0]}")
    
    # The agent receiving the systemEvent from cron will see this and run:
    # python idealista-notion-sync/scripts/deep_sync.py <target_url>
    # AND then run the scheduler again to pick the next date.
    
    schedule_next_run()

if __name__ == "__main__":
    main()
