import io, json, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# 新橋駅の朝の発車時刻をJSONへ保存
url = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
r = requests.get(url, timeout=120)
r.raise_for_status()

with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    stops = pd.read_csv(z.open("stops.txt"), dtype=str).fillna("")
    times = pd.read_csv(z.open("stop_times.txt"), dtype=str).fillna("")
    stop_id = stops.loc[stops["stop_name"] == "新橋", "stop_id"].iloc[0]
    data = times[
        (times["stop_id"] == stop_id)
        & times["departure_time"].str.match(r"^(0[7-9]):")
    ].sort_values("departure_time").head(20)

result = {
    "station": "新橋",
    "fetched_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes"),
    "departures": [x[:5] for x in data["departure_time"]]
}

Path("departures.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f'{len(result["departures"])}件をdepartures.jsonへ保存しました')
