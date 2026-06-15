import pandas as pd

# Load the data the logger collected
df = pd.read_csv("arc_occupancy.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["hour"] = df["timestamp"].dt.hour
df["day"] = df["timestamp"].dt.day_name()

print(f"Loaded {len(df)} readings across {df['facility_name'].nunique()} zones")
print(f"Date range: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}\n")

# For each zone, show average busyness by hour
for zone in df["facility_name"].unique():
    z = df[df["facility_name"] == zone]
    print(f"=== {zone} ===")
    by_hour = z.groupby("hour")["pct_full"].mean().round(1)

    # best (quietest) times during normal hours 6am-11pm
    daytime = by_hour[(by_hour.index >= 6) & (by_hour.index <= 23)]
    quietest = daytime.nsmallest(3)
    busiest = daytime.nlargest(3)

    print("  Quietest hours:", ", ".join(f"{h}:00 ({p}%)" for h, p in quietest.items()))
    print("  Busiest hours: ", ", ".join(f"{h}:00 ({p}%)" for h, p in busiest.items()))
    print()