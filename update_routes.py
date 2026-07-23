import json, os, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pandas as pd, requests

URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
DEST, LIMIT = "新橋", 8 * 60
CACHE, STATE, OUT = Path("data/toei_gtfs.zip"), Path("data/gtfs_state.json"), Path("direct_routes.json")
JST = timezone(timedelta(hours=9))

def now(): return datetime.now(JST)
def read(z, name): return pd.read_csv(z.open(name), dtype=str).fillna("")
def minute(t):
    h, m, *_ = map(int, t.split(":"))
    return h * 60 + m
def clock(m): return f"{m // 60 % 24:02d}:{m % 60:02d}"

def next_weekday():
    # 次の平日を対象にする
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5: d += timedelta(days=1)
    return d

def get_gtfs():
    # 7日以内は保存済みGTFSを再利用
    CACHE.parent.mkdir(exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    checked = datetime.fromisoformat(state["checked_at"]) if state.get("checked_at") else None
    force = os.getenv("FORCE_UPDATE", "false").lower() == "true"

    if CACHE.exists() and checked and not force and now() - checked < timedelta(days=7):
        print("保存済みGTFSを使用")
        return

    headers = {}
    if not force:
        if state.get("etag"): headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"): headers["If-Modified-Since"] = state["last_modified"]

    try:
        r = requests.get(URL, headers=headers, timeout=120)
        if r.status_code == 304 and CACHE.exists():
            state["checked_at"] = now().isoformat(timespec="minutes")
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            print("GTFSに変更なし")
            return

        r.raise_for_status()
        CACHE.write_bytes(r.content)
        STATE.write_text(json.dumps({
            "checked_at": now().isoformat(timespec="minutes"),
            "fetched_at": now().isoformat(timespec="minutes"),
            "etag": r.headers.get("ETag", ""),
            "last_modified": r.headers.get("Last-Modified", "")
        }, ensure_ascii=False, indent=2))
        print("最新GTFSを取得")
    except requests.RequestException:
        if not CACHE.exists(): raise
        print("取得失敗のため保存済みGTFSを使用")

def active_services(z, day):
    # 対象日に運行する列車を選ぶ
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
    get_gtfs()
    day = next_weekday()

    with zipfile.ZipFile(CACHE) as z:
        stops, times = read(z, "stops.txt"), read(z, "stop_times.txt")
        trips, routes = read(z, "trips.txt"), read(z, "routes.txt")

        # 時刻が空欄の行を除外してから分へ変換
        times = times[
            (times["departure_time"] != "")
            & (times["arrival_time"] != "")
        ].copy()
        
        times["seq"] = times["stop_sequence"].astype(int)
        times["dep_min"] = times["departure_time"].map(minute)
        times["arr_min"] = times["arrival_time"].map(minute)

        # 対象日の列車に路線名を付与
        trips = trips[trips["service_id"].isin(active_services(z, day))].merge(
            routes[["route_id", "route_short_name", "route_long_name"]],
            on="route_id", how="left"
        )

        # 新橋へ8時までに着く列車
        dest_ids = set(stops.loc[stops["stop_name"] == DEST, "stop_id"])
        arrivals = times[
            times["stop_id"].isin(dest_ids) & times["arr_min"].between(5 * 60, LIMIT)
        ][["trip_id", "arr_min", "seq"]].rename(
            columns={"arr_min": "dest_arr", "seq": "dest_seq"}
        )

        # 同じ列車で新橋より前に停車する駅を抽出
        data = times.merge(arrivals, on="trip_id").merge(
            trips[["trip_id", "trip_headsign", "route_short_name", "route_long_name"]],
            on="trip_id"
        ).merge(stops[["stop_id", "stop_name"]], on="stop_id")

        data = data[
            (data["seq"] < data["dest_seq"]) & (data["stop_name"] != DEST)
        ]

        # 各駅で最も遅く出発できる直通列車を選ぶ
        data = data.loc[data.groupby("stop_name")["dep_min"].idxmax()]
        data = data.sort_values("dep_min", ascending=False)

        routes_out = [{
            "station": x.stop_name,
            "departure": clock(x.dep_min),
            "arrival": clock(x.dest_arr),
            "minutes": int(x.dest_arr - x.dep_min),
            "route": x.route_short_name or x.route_long_name or "都営線",
            "destination": x.trip_headsign or "行先情報なし"
        } for x in data.itertuples()]

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    OUT.write_text(json.dumps({
        "destination": DEST,
        "arrival_limit": "08:00",
        "service_date": day.isoformat(),
        "gtfs_fetched_at": state.get("fetched_at", ""),
        "generated_at": now().isoformat(timespec="minutes"),
        "routes": routes_out
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(routes_out)}駅の直通経路を保存しました")

if __name__ == "__main__":
    main()
