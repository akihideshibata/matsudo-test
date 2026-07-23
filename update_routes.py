import io, zipfile
import pandas as pd
import requests

# 東京都交通局GTFSを取得
url = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
r = requests.get(url, timeout=120)
r.raise_for_status()

# 駅名を読み取り、「新橋」を含むものだけ表示
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    stops = pd.read_csv(z.open("stops.txt"), dtype=str).fillna("")
    print(stops.loc[stops["stop_name"].str.contains("新橋", regex=False),
                    ["stop_id", "stop_name"]].to_string(index=False))
