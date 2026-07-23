import json, os
from datetime import date, timedelta
from pathlib import Path
import requests

# 対象駅。最初は主要駅だけで動作確認する
STATIONS = ["北千住", "柏", "日暮里", "上野", "西日暮里", "秋葉原",
            "東京", "神田", "新橋", "浜松町", "品川", "新宿", "渋谷"]
API = "https://api.ekispert.jp/v1/json"
FILE = Path("routes.json")
KEY = os.environ["EKISPERT_KEY"]


def get(path, **params):
    """駅すぱあとAPIを呼び出す。"""
    r = requests.get(f"{API}/{path}", params={"key": KEY, **params}, timeout=30)
    r.raise_for_status()
    return r.json()["ResultSet"]


def as_list(value):
    """JSON内で1件だけ辞書になる項目を、常にリストとして扱う。"""
    return value if isinstance(value, list) else [value]


def next_weekday():
    """検索対象となる直近の平日を返す。"""
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.strftime("%Y%m%d")


def version():
    """鉄道時刻表を含むAPIデータのバージョンを文字列化する。"""
    r = get("dataversion")
    versions = as_list(r["Version"])
    return r["engineVersion"] + ":" + "|".join(
        f'{x["caption"]}={x.get("create", "")}' for x in versions
        if x["caption"] in {"鉄道時刻表", "ＪＲ", "私鉄"}
    )


def route(station, day):
    """松戸8時着に間に合う、最も遅い出発経路を取得する。"""
    r = get("search/course/extreme", viaList=f"{station}:松戸",
            date=day, time="0800", searchType="arrival",
            answerCount=10, searchCount=20, sort="time")
    courses = as_list(r["Course"])
    results = []

    for c in courses:
        rt, points = c["Route"], as_list(c["Route"]["Point"])
        lines = as_list(rt["Line"])
        dep = lines[0]["DepartureState"]["Datetime"]
        arr = lines[-1]["ArrivalState"]["Datetime"]
        names = [x["Name"].split("・")[0] for x in lines]
        transfers = [p["Station"]["Name"] for p in points[1:-1] if "Station" in p]

        results.append({
            "station": station,
            "departure": dep[11:16],
            "arrival": arr[11:16],
            "minutes": int(rt["timeOnBoard"]) + int(rt.get("timeOther", 0))
                       + int(rt.get("timeWalk", 0)),
            "transfers": int(rt["transferCount"]),
            "transfer_stations": transfers,
            "route": names,
        })

    return max(results, key=lambda x: x["departure"])


def main():
    """バージョン変更時だけ全駅を再取得してJSONへ保存する。"""
    new_version = version()
    old = json.loads(FILE.read_text()) if FILE.exists() else {}

    if old.get("version") == new_version:
        print("データバージョンに変更なし")
        return

    day = next_weekday()
    data = [route(station, day) for station in STATIONS]
    FILE.write_text(json.dumps({
        "version": new_version,
        "searched_date": day,
        "destination": "松戸",
        "arrival_limit": "08:00",
        "routes": sorted(data, key=lambda x: x["departure"], reverse=True),
    }, ensure_ascii=False, indent=2))

    print(f"{len(data)}駅を更新しました")


if __name__ == "__main__":
    main()
