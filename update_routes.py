import io, zipfile
import requests

# 東京都交通局GTFSを取得
url = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
r = requests.get(url, timeout=120)
r.raise_for_status()

# ZIP内のファイル名を確認
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    for name in z.namelist():
        print(name)
