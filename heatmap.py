import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# DEV MODE: swap to "arc_occupancy.csv" when real data is ready.
DATA_FILE = "sample_history.csv"
ZONE = "ARC Access"   # change to "Recreation Pool" or "Rock Wall" to see others

df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["hour"] = df["timestamp"].dt.hour
df["dow"] = df["timestamp"].dt.dayofweek   # 0=Mon ... 6=Sun

z = df[df["facility_name"] == ZONE]

# Build a grid: rows = days of week, cols = hours 6am-11pm
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
hours = list(range(6, 24))
grid = np.full((7, len(hours)), np.nan)

for d in range(7):
    for i, h in enumerate(hours):
        cell = z[(z["dow"] == d) & (z["hour"] == h)]
        if len(cell) > 0:
            grid[d, i] = cell["pct_full"].mean()

# Draw it
fig, ax = plt.subplots(figsize=(12, 5))
im = ax.imshow(grid, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)

ax.set_xticks(range(len(hours)))
ax.set_xticklabels([f"{h}" for h in hours])
ax.set_yticks(range(7))
ax.set_yticklabels(days)
ax.set_xlabel("Hour of day")
ax.set_title(f"{ZONE} — typical busyness by day & hour")
fig.colorbar(im, label="% full")
plt.tight_layout()
plt.savefig("heatmap.png", dpi=120)
print("Saved heatmap.png")