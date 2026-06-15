import pandas as pd
import matplotlib.pyplot as plt

# DEV MODE: build against sample data. Swap to "arc_occupancy.csv" when real data is ready.
DATA_FILE = "sample_history.csv"

df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["hour"] = df["timestamp"].dt.hour

plt.figure(figsize=(11, 6))
for zone in df["facility_name"].unique():
    z = df[df["facility_name"] == zone]
    by_hour = z.groupby("hour")["pct_full"].mean()
    plt.plot(by_hour.index, by_hour.values, marker="o", linewidth=2, label=zone)

plt.xlabel("Hour of day")
plt.ylabel("Average % full")
plt.title("ARC busyness by hour (typical day)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(range(6, 24))
plt.tight_layout()
plt.savefig("busyness_by_hour.png", dpi=120)
print("Saved busyness_by_hour.png")