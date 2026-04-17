# Idealista-Notion Sync — Project Memory

## Overview
Daily sync of property listings from Idealista agency pages to Notion database "Residential Properties".

## Key Files
- `agencies_queue.json` — rotation queue of agency URLs (processed one per day)
- `scripts/deep_sync_v2.py` — main sync script (uses Playwright internally)
- `SKILL.md` — full skill documentation

## Database IDs
- Residential Properties: `21512f74-2f9e-8153-bdda-c3df73a32f59`

## Notes
- Script uses Playwright internally — do NOT use web_fetch or browser tool directly
- idealista.com blocks web_fetch requests (403)
- No other MEMORY.md, DESIGN.md or config files exist in this project
