#!/usr/bin/env python3
"""
Idealista Daily Sync with Cron Reporting
Enhanced version that logs all results to Telegram
"""

import sys
import json
import os
import random
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cron_reports_system import report_cron_completion, CronStatus
from skill_logger import log_skill_execution

# --- CONFIG ---
BASE_DIR = r"C:\Users\Val\.openclaw\workspace"
AGENCIES_FILE = os.path.join(BASE_DIR, "agencies_queue.json")
SYNC_SCRIPT = os.path.join(BASE_DIR, "idealista-notion-sync", "scripts", "deep_sync.py")
PYTHON_EXE = r"C:\Python314\python.exe"

def load_queue():
    """Load agencies queue"""
    if os.path.exists(AGENCIES_FILE):
        with open(AGENCIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_queue(queue):
    """Save agencies queue"""
    with open(AGENCIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

def sync_agency(agency_name: str) -> tuple:
    """
    Run sync for single agency
    
    Returns:
        (success: bool, result: dict)
    """
    try:
        print(f"[SYNC] {agency_name}...")
        
        result = subprocess.run(
            [PYTHON_EXE, SYNC_SCRIPT, agency_name],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )
        
        if result.returncode == 0:
            # Try to parse output
            output = result.stdout or ""
            return True, {
                "agency": agency_name,
                "status": "success",
                "output_lines": len(output.split('\n'))
            }
        else:
            error = result.stderr or "Unknown error"
            return False, {
                "agency": agency_name,
                "status": "failed",
                "error": error[:100]
            }
    
    except subprocess.TimeoutExpired:
        return False, {
            "agency": agency_name,
            "status": "timeout",
            "error": "Sync took too long (>5 min)"
        }
    except Exception as e:
        return False, {
            "agency": agency_name,
            "status": "error",
            "error": str(e)[:100]
        }

def run_daily_sync():
    """Run daily sync rotation"""
    
    print("\n" + "="*70)
    print("IDEALISTA DAILY SYNC")
    print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("="*70 + "\n")
    
    queue = load_queue()
    
    if not queue:
        print("[ERROR] No agencies in queue!")
        report_cron_completion(
            cron_name="idealista_daily_sync",
            status=CronStatus.FAILED,
            result={},
            error="No agencies configured"
        )
        return False
    
    # Get next agency (rotate)
    agency = queue.pop(0)
    queue.append(agency)  # Move to back for rotation
    save_queue(queue)
    
    print(f"[ROTATING] Queue: {' → '.join([a.get('name', 'Unknown')[:15] for a in queue[:3]])}\n")
    
    # Run sync
    sync_results = []
    success_count = 0
    fail_count = 0
    
    for agency_info in [agency]:
        agency_name = agency_info.get('name', 'Unknown')
        
        success, result = sync_agency(agency_name)
        sync_results.append(result)
        
        if success:
            success_count += 1
            print(f"  ✅ {agency_name} synced")
        else:
            fail_count += 1
            print(f"  ❌ {agency_name} failed: {result.get('error', 'Unknown')}")
    
    print()
    
    # Determine overall status
    if fail_count == 0:
        overall_status = CronStatus.SUCCESS
    elif success_count > 0:
        overall_status = CronStatus.PARTIAL
    else:
        overall_status = CronStatus.FAILED
    
    # Prepare report
    report_result = {
        "agencies_checked": 1,
        "agencies_success": success_count,
        "agencies_failed": fail_count,
        "details": sync_results,
        "queue_next": queue[0].get('name', 'Unknown') if queue else "None",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    # Send report
    report_cron_completion(
        cron_name="idealista_daily_sync",
        status=overall_status,
        result=report_result,
        error=None if fail_count == 0 else f"{fail_count} agencies failed",
        send_telegram=True
    )
    
    # Schedule next run for tomorrow
    schedule_next_run()
    
    return success_count > 0

def schedule_next_run():
    """Schedule next daily sync"""
    
    tomorrow = datetime.now() + timedelta(days=1)
    random_hour = random.randint(9, 18)
    random_minute = random.randint(0, 59)
    
    run_time = tomorrow.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)
    run_time_iso = run_time.strftime("%Y-%m-%dT%H:%M:%S+01:00")
    
    print(f"[SCHEDULED] Next sync: {run_time_iso} (Madrid time)")

if __name__ == "__main__":
    success = run_daily_sync()
    sys.exit(0 if success else 1)
