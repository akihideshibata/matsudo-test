import io, json, os, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
STATION = "新橋"
CACHE = Path("data/toei_gtfs.zip")
STATE = Path("data/gtfs_state.json")
OUT = Path("departures.json")
JST = timezone(timedelta(hours=9))


def now():
    return datetime.now(JST)


def read(z, name):
    # GTFS内のCSVを文字列として読み込む
    return pd.read_csv(z.open(name), dtype=str).fillna("")


def next_weekday():
    # 次の平日を対象日にする
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def get_gtfs():
    # 7日以内なら保存済みGTFSを再利用
    CACHE.parent.mkdir(exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    checked = datetime.fromisoformat(state["checked_at"]) if state.get("checked_at") else None
    force = os.getenv("FORCE_UPDATE", "false").lower() == "true"

    if CACHE.exists() and checked and not force and now() - checked < timedelta(days=7):
        print("7日以内のため保存済みGTFSを使用")
        return CACHE.read_bytes()

    # 7日経過後は更新確認。未更新なら304で本体を取得しない
    headers = {}
    if not force:
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]

    try:
        r = requests.get(URL, headers=headers, timeout=120)
        if r.status_code == 304 and CACHE.exists():
            state["checked_at"] = now().isoformat(timespec="minutes")
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            print("GTFSに変更なし。保存済みデータを使用")
            return CACHE.read_bytes()

        r.raise_for_status()
        CACHE.write_bytes(r.content)
        STATE.write_text(json.dumps({
            "checked_at": now().isoformat(timespec="minutes"),
            "fetched_at": now().isoformat(timespec="minutes"),
            "etag": r.headers.get("ETag", ""),
            "last_modified": r.headers.get("Last-Modified", "")
        }, ensure_ascii=False, indent=2))
        print(f"最新GTFSを取得：{len(r.content):,} bytes")
        return r.content

    except requests.RequestException:
        # 取得失敗時も既存データがあればアプリ更新を継続
        if CACHE.exists():
            print("取得失敗。保存済みGTFSを使用")
            return CACHE.read_bytes()
        raise


def active_services(z, day):
    # 指定日に運行する列車だけを選ぶ
    ymd, weekday = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    c = read(z, "calendar.txt")
    ids = set(c.loc[
        (c["start_date"] <= ymd) & (c["end_date"] >= ymd) & (c[weekday] == "1"),
        "service_id"
    ])

    if "calendar_dates.txt" in z.namelist():
        x = read(z, "calendar_dates.txt")
        x = x[x["date"] == ymd]
        ids |= set(x.loc[x["exception_type"] == "1", "service_id"])
        ids -= set(x.loc[x["exception_type"] == "2", "service_id"])
    return ids


def main():
    content, day = get_gtfs(), next_weekday()

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        stops, times = read(z, "stops.txt"), read(z, "stop_times.txt")
        trips, routes = read(z, "trips.txt"), read(z, "routes.txt")

        stop_id = stops.loc[stops["stop_name"] == STATION, "stop_id"].iloc[0]
        trips = trips[trips["service_id"].isin(active_services(z, day))].merge(
            routes[["route_id", "route_short_name", "route_long_name"]],
            on="route_id", how="left"
        )
        data = times[times["stop_id"] == stop_id].merge(trips, on="trip_id")
        data = data[
            data["departure_time"].str.match(r"^(0[7-9]):")
        ].sort_values("departure_time")

    OUT.write_text(json.dumps({
        "station": STATION,
        "service_date": day.isoformat(),
        "fetched_at": now().isoformat(timespec="minutes"),
        "departures": [{
            "time": x.departure_time[:5],
            "route": x.route_short_name or x.route_long_name or "都営線",
            "destination": x.trip_headsign or "行先情報なし"
        } for x in data.itertuples()]
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{STATION}駅の時刻表を{len(data)}件保存しました")


if __name__ == "__main__":
    main()
