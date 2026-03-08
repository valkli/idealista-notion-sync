---
name: idealista-notion-sync
description: Deep synchronization of property listings from Idealista to the 'Residential Properties' Notion database. Navigates into each listing to extract full details (price, area, rooms, floor) while mimicking human behavior with random delays and once-a-day agency rotation.
---

# Idealista-Notion Deep Sync

This skill synchronizes property listings from Idealista agency pages to your Notion workspace.

## Database
-   **Target**: `Residential Properties`
-   **ID**: `21512f74-2f9e-8153-bdda-c3df73a32f59`

## Logic
1.  **Agency Selection**: Each run selects one agency from the rotation queue.
2.  **Listing Discovery**: Scans the agency's main page for new property IDs.
3.  **Deep Extraction**: For each *new* property, it:
    -   Opens the listing in a new browser tab.
    -   Waits for JS and extracts: Price, Area, Bedrooms, Bathrooms, Floor.
    -   Adds the entry to Notion.
    -   Closes the tab and waits a random interval (5–15s).
4.  **Behavioral Emulation**:
    -   Limits to ~5 properties per session.
    -   Randomizes clicks and wait times.
    -   Schedules the next agency for "Tomorrow" at a random work-hour.

## Usage
To start the rotation or sync a specific agency:
`python scripts/master_scheduler.py`

To sync a specific URL immediately:
`python scripts/deep_sync.py <URL>`
