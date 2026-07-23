import io, zipfile
import pandas as pd
import requests

# 東京都交通局GTFSを取得
url = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
r = requests.get(url, timeout=120)
r.raise_for_status()

with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    stops = pd.read_csv(z.open("stops.txt"), dtype=str).fillna("")
    times = pd.read_csv(z.open("stop_times.txt"), dtype=str).fillna("")

    # 新橋駅のstop_idを取得
    stop_id = stops.loc[stops["stop_name"] == "新橋", "stop_id"].iloc[0]

    # 新橋駅を7〜9時台に発車する列車を先頭20件表示
    data = times[
        (times["stop_id"] == stop_id)
        & times["departure_time"].str.match(r"^(0[7-9]):")
    ].sort_values("departure_time").head(20)

    print(data[["departure_time", "trip_id"]].to_string(index=False))
