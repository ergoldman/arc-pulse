# ARC Pulse

Live and predicted occupancy analysis for the UC Davis Activities and Recreation Center (ARC).

The official rec portal shows current occupancy as a single number. This project logs that number over time and turns it into something useful: when the ARC is typically busy, whether it's busier or quieter than normal right now, and the best times to go.

## What's here

- **arc_logger.py** — fetches the public occupancy page every 10 minutes, logs each zone's count to a CSV
- **analyze.py** — busiest and quietest hours per zone
- **charts.py** — average busyness by hour (daily curve)
- **heatmap.py** — typical busyness by day and hour (the week at a glance)
- **now_vs_normal.py** — compares the current reading to the historical norm for that day and hour
- **best_times.py** — quietest workout time for each day of the week
- **sample_history.csv** — three weeks of sample data for development

## How it works

The logger builds a historical dataset of facility occupancy. The analysis scripts read that data to surface patterns the official page doesn't show. Scripts are built against sample data and switch to live data by changing one filename.

All data is aggregate facility counts — no personal or individual information.

## Tracked zones

ARC Access, Recreation Pool, Rock Wall (new zones detected automatically).

## Status

Logger running and collecting. Analysis runs on sample data; switches to live data as the real dataset accumulates.
