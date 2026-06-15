# ARC Pulse

Live and predicted occupancy for the UC Davis Activities and Recreation Center (ARC).

The official rec portal shows current occupancy as a single number. This project logs that number over time to answer the questions it can't: when is the ARC typically busy, is it busier or quieter than normal right now, and when's the best time to go.

## How it works

A logger fetches the public facility-occupancy page every 10 minutes and records each zone's current and maximum count to a CSV. Over time this builds a historical dataset used for pattern analysis and forecasting.

Tracked zones: ARC Access, Recreation Pool, Rock Wall (auto-detects new zones if added).

## Data

Each row: `timestamp, facility_id, facility_name, current, maximum, remaining, pct_full, page_last_update`

All data is aggregate facility counts — no personal or individual information.

## Status

Collecting data. Analysis and dashboard in progress.
