import json, os, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
CACHE, STATE, OUT = Path("data/toei_gtfs.zip"), Path("data/gtfs_state.json"), Path("direct_timetable.json")
JST = timezone(timedelta(hours=9))


def now(): return datetime.now(JST)
def read(z, name): return pd.read_csv(z.open(name), dtype=str).fillna("")


def next_weekday():
    # 次の平日を対象にする
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def get_gtfs():
    # 7日以内は保存済みGTFSを再利用する
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
            "last_modified": r.headers.get("Last-Modified", ""),
        }, ensure_ascii=False, indent=2))
        print("最新GTFSを取得")

    except requests.RequestException:
        # 通信失敗時も既存データがあれば継続する
        if not CACHE.exists():
            raise
        print("取得失敗のため保存済みGTFSを使用")


def active_services(z, day):
    # 指定日に運行する列車を判定する
    ymd, weekday = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    c = read(z, "calendar.txt")
    ids = set(c.loc[
        (c["start_date"] <= ymd)
        & (c["end_date"] >= ymd)
        & (c[weekday] == "1"),
        "service_id",
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

        # 発着時刻がない行は除外
        times = times[
            (times["arrival_time"] != "")
            & (times["departure_time"] != "")
        ].copy()
        times["stop_sequence"] = times["stop_sequence"].astype(int)

        # 対象日に運行する列車へ路線名を付ける
        trips = trips[trips["service_id"].isin(active_services(z, day))].merge(
            routes[["route_id", "route_short_name", "route_long_name"]],
            on="route_id",
            how="left",
        )
        times = times.merge(
            trips[["trip_id", "trip_headsign", "route_short_name", "route_long_name"]],
            on="trip_id",
        ).merge(
            stops[["stop_id", "stop_name"]],
            on="stop_id",
        ).sort_values(["trip_id", "stop_sequence"])

        # 駅ごとの乗り入れ路線を作成
        times["route"] = times["route_short_name"].where(
            times["route_short_name"] != "", times["route_long_name"]
        ).replace("", "都営線")
        station_routes = (
            times.groupby("stop_name")["route"]
            .agg(lambda x: sorted(set(x)))
            .to_dict()
        )

        # 各列車の停車順・時刻をコンパクトに保存
        output_trips = []
        for _, group in times.groupby("trip_id", sort=False):
            if len(group) < 2:
                continue
            first = group.iloc[0]
            output_trips.append({
                "route": first["route"],
                "destination": first["trip_headsign"] or "行先情報なし",
                "stops": [
                    [x.stop_name, x.arrival_time[:5], x.departure_time[:5]]
                    for x in group.itertuples()
                ],
            })

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    OUT.write_text(json.dumps({
        "service_date": day.isoformat(),
        "gtfs_fetched_at": state.get("fetched_at", ""),
        "generated_at": now().isoformat(timespec="minutes"),
        "stations": [
            {"name": name, "routes": routes}
            for name, routes in sorted(station_routes.items())
        ],
        "trips": output_trips,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"{len(output_trips)}列車、{len(station_routes)}駅を保存しました")


if __name__ == "__main__":
    main()
