import pandas as pd

# DEV MODE: swap to "arc_occupancy.csv" when real data is ready.
DATA_FILE = "sample_history.csv"

# Only recommend reasonable workout hours (skip the near-closing dead zone)
OPEN_START = 7    # 7am
OPEN_END = 20     # 8pm

df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["hour"] = df["timestamp"].dt.hour
df["dow"] = df["timestamp"].dt.dayofweek

days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def ampm(h):
    period = "am" if h < 12 else "pm"
    hr = h % 12
    if hr == 0: hr = 12
    return f"{hr}{period}"

for zone in df["facility_name"].unique():
    z = df[df["facility_name"] == zone]

    # average busyness per (day, hour) slot, within sensible workout hours
    in_hours = z[(z["hour"] >= OPEN_START) & (z["hour"] <= OPEN_END)]
    slots = (in_hours.groupby(["dow", "hour"])["pct_full"]
             .mean()
             .reset_index())

    print(f"=== {zone} — quietest workout time each day ===")
    # for each day, find that day's single quietest hour
    for d in range(7):
        day_slots = slots[slots["dow"] == d]
        if len(day_slots) == 0:
            continue
        best = day_slots.nsmallest(1, "pct_full").iloc[0]
        h = ampm(int(best["hour"]))
        p = best["pct_full"]
        print(f"  {days[d]:<10} {h:<5} — typically {p:.0f}% full")
    print()