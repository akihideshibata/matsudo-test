import requests

# 東京都交通局GTFSを取得できるか確認
url = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
r = requests.get(url, timeout=120)
r.raise_for_status()

print(f"取得成功：{len(r.content):,} bytes")
