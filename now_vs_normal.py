import pandas as pd

# DEV MODE: swap to "arc_occupancy.csv" when real data is ready.
DATA_FILE = "sample_history.csv"

df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["hour"] = df["timestamp"].dt.hour
df["dow"] = df["timestamp"].dt.dayofweek

# For each zone, compare the MOST RECENT reading to the historical
# average for that same day-of-week + hour.
for zone in df["facility_name"].unique():
    z = df[df["facility_name"] == zone].sort_values("timestamp")
    latest = z.iloc[-1]                      # most recent reading = "now"
    now_pct = latest["pct_full"]
    now_dow = latest["dow"]
    now_hour = latest["hour"]
    day_name = latest["timestamp"].day_name()

    # historical readings for this same weekday + hour
    same_slot = z[(z["dow"] == now_dow) & (z["hour"] == now_hour)]
    normal = same_slot["pct_full"].mean()
    spread = same_slot["pct_full"].std()

    # how far from normal? (in standard deviations)
    if spread and spread > 0:
        diff = (now_pct - normal) / spread
    else:
        diff = 0

    if diff < -0.6:
        verdict = "QUIETER than usual — good time to go"
    elif diff > 0.6:
        verdict = "BUSIER than usual"
    else:
        verdict = "about normal"

    print(f"=== {zone} ===")
    print(f"  Now: {now_pct:.0f}% full ({day_name} {now_hour}:00)")
    print(f"  Typical for this time: {normal:.0f}%")
    print(f"  Verdict: {verdict}")
    print()
