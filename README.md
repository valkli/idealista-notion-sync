# Idealista → Notion Sync

> Automated real estate listing synchronization from Idealista.com to a Notion database.

## Overview

An AI-powered agent skill that monitors real estate listings from multiple agencies on Idealista and keeps a structured Notion database in sync — automatically detecting new properties, price changes, and sold/removed listings.

## Features

- **Multi-agency support** — tracks listings from multiple real estate agencies simultaneously
- **Daily automated sync** — scheduled rotation through agencies via cron
- **Smart deduplication** — prevents duplicate entries in Notion
- **Sold property detection** — archives listings no longer available on Idealista
- **Deep sync mode** — full reconciliation for catching edge cases
- **Telegram reporting** — summary report after each sync run

## Architecture

```
Idealista (web) → sync.py → Notion Database
                         ↳ master_scheduler.py (rotation + cron)
                         ↳ cleanup_sold.py (archive removed listings)
                         ↳ deduplicate.py (consistency checks)
```

## Requirements

- Python 3.10+
- Notion API Key (`NOTION_API_KEY` env variable)
- Notion Database ID configured in scripts

## Usage

```bash
# Run sync for a specific agency
python scripts/sync.py

# Run master scheduler (handles rotation)
python scripts/master_scheduler.py

# Check for sold properties
python scripts/check_sold.py

# Clean up sold/archived listings
python scripts/cleanup_sold.py
```

## Environment Variables

```
NOTION_API_KEY=your_notion_integration_key
```

## Agent Skill

This is an **OpenClaw agent skill** — designed to run autonomously as part of an AI-powered automation pipeline. The agent manages scheduling, error handling, and reporting without manual intervention.

---

*Part of the AI automation toolkit for real estate investment operations in Spain.*
