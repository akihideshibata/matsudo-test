import json, os, re, time, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

GTFS_URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
REVERSE_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"

CACHE = Path("data/toei_gtfs.zip")
STATE = Path("data/gtfs_state.json")
LOCATIONS = Path("station_locations.json")
UNRESOLVED = Path("unresolved_stations.json")
OUT = Path("direct_timetable.json")
JST = timezone(timedelta(hours=9))


def now():
    return datetime.now(JST)


def read(z, name):
    # GTFS内のCSVをすべて文字列として読む
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
        print("保存済みGTFSを使用")
        return

    headers = {}
    if not force:
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]

    try:
        r = requests.get(GTFS_URL, headers=headers, timeout=120)

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
        # 通信失敗時も既存GTFSがあれば処理を続ける
        if not CACHE.exists():
            raise
        print("取得失敗のため保存済みGTFSを使用")


def active_services(z, day):
    # 指定日に運行するservice_idを取得
    ymd, weekday = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    calendar = read(z, "calendar.txt")
    ids = set(calendar.loc[
        (calendar["start_date"] <= ymd)
        & (calendar["end_date"] >= ymd)
        & (calendar[weekday] == "1"),
        "service_id",
    ])

    if "calendar_dates.txt" in z.namelist():
        special = read(z, "calendar_dates.txt")
        special = special[special["date"] == ymd]
        ids |= set(special.loc[special["exception_type"] == "1", "service_id"])
        ids -= set(special.loc[special["exception_type"] == "2", "service_id"])

    return ids


def get_municipalities(session):
    # 自治体コードと「都道府県＋市区町村」の対応表を取得
    # muni.jsをUTF-8として明示的に読み込む
    response = session.get(MUNI_URL, timeout=30)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig")
    result = {}

    for code, value in re.findall(
        r'MUNI_ARRAY\["(\d+)"\]\s*=\s*[\'"]([^\'"]+)',
        text,
    ):
        parts = value.split(",")
        if len(parts) >= 4:
            result[code] = parts[1] + parts[3]

    return result


def update_locations(stops):
    # 保存済み住所を読み、新しいstop_idだけ照会する
    locations = json.loads(LOCATIONS.read_text()) if LOCATIONS.exists() else {}
    unresolved = []
    columns = ["stop_id", "stop_name", "stop_lat", "stop_lon"]

    stations = stops[
        (stops["stop_id"] != "")
        & (stops["stop_lat"] != "")
        & (stops["stop_lon"] != "")
    ][columns].drop_duplicates("stop_id")

    new_rows = [
        row for row in stations.itertuples(index=False)
        if row.stop_id not in locations
        or locations[row.stop_id].get("lat") != row.stop_lat
        or locations[row.stop_id].get("lon") != row.stop_lon
    ]

    if not new_rows:
        print("新しい駅なし：住所照会を省略")
        return locations

    print(f"住所未登録のstop_id：{len(new_rows)}件")
    session = requests.Session()
    session.headers["User-Agent"] = "reverse-commute-prototype/1.0"
    municipalities = get_municipalities(session)

    for row in new_rows:
        try:
            r = session.get(
                REVERSE_URL,
                params={"lat": row.stop_lat, "lon": row.stop_lon},
                timeout=20,
            )
            r.raise_for_status()
            result = r.json().get("results", {})
            code = result.get("muniCd", "")
            location = municipalities.get(code, "")

            if not location:
                raise ValueError(f"自治体を判定できません：{code}")

            locations[row.stop_id] = {
                "name": row.stop_name,
                "lat": row.stop_lat,
                "lon": row.stop_lon,
                "municipality_code": code,
                "location": location,
                "updated_at": now().isoformat(timespec="minutes"),
            }
            print(f"住所追加：{row.stop_name} → {location}")

        except Exception as e:
            unresolved.append({
                "stop_id": row.stop_id,
                "name": row.stop_name,
                "lat": row.stop_lat,
                "lon": row.stop_lon,
                "error": str(e),
            })
            print(f"住所未判定：{row.stop_name}（{row.stop_id}）")

        # 新規駅だけを低頻度で照会
        time.sleep(0.15)

    LOCATIONS.write_text(
        json.dumps(locations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    UNRESOLVED.write_text(
        json.dumps(unresolved, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return locations


def main():
    get_gtfs()
    day = next_weekday()

    with zipfile.ZipFile(CACHE) as z:
        stops = read(z, "stops.txt")
        times = read(z, "stop_times.txt")
        trips = read(z, "trips.txt")
        routes = read(z, "routes.txt")

        locations = update_locations(stops)

        # 時刻がない行は除外
        times = times[
            (times["arrival_time"] != "")
            & (times["departure_time"] != "")
        ].copy()
        times["stop_sequence"] = times["stop_sequence"].astype(int)

        # 対象日の列車だけに絞る
        trips = trips[
            trips["service_id"].isin(active_services(z, day))
        ].merge(
            routes[[
                "route_id",
                "route_short_name",
                "route_long_name",
            ]],
            on="route_id",
            how="left",
        )

        times = times.merge(
            trips[[
                "trip_id",
                "trip_headsign",
                "route_short_name",
                "route_long_name",
            ]],
            on="trip_id",
        ).merge(
            stops[[
                "stop_id",
                "stop_name",
            ]],
            on="stop_id",
        ).sort_values([
            "trip_id",
            "stop_sequence",
        ])

        times["route"] = times["route_short_name"].where(
            times["route_short_name"] != "",
            times["route_long_name"],
        ).replace("", "都営線")

        # 駅名ごとの路線と所在地を作る
        station_routes = (
            times.groupby("stop_name")["route"]
            .agg(lambda x: sorted(set(x)))
            .to_dict()
        )

        station_locations = {}
        for row in times[["stop_id", "stop_name"]].drop_duplicates().itertuples(index=False):
            location = locations.get(row.stop_id, {}).get("location", "")
            if location and not station_locations.get(row.stop_name):
                station_locations[row.stop_name] = location

        # 列車ごとの停車駅と時刻を保存
        output_trips = []

        for _, group in times.groupby("trip_id", sort=False):
            if len(group) < 2:
                continue

            first = group.iloc[0]
            output_trips.append({
                "route": first["route"],
                "destination": first["trip_headsign"] or "行先情報なし",
                "stops": [
                    [
                        row.stop_name,
                        row.arrival_time[:5],
                        row.departure_time[:5],
                    ]
                    for row in group.itertuples()
                ],
            })

    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    OUT.write_text(json.dumps({
        "service_date": day.isoformat(),
        "gtfs_fetched_at": state.get("fetched_at", ""),
        "generated_at": now().isoformat(timespec="minutes"),
        "stations": [
            {
                "name": name,
                "routes": routes,
                "location": station_locations.get(name, "所在地未登録"),
            }
            for name, routes in sorted(station_routes.items())
        ],
        "trips": output_trips,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(
        f"{len(output_trips)}列車、"
        f"{len(station_routes)}駅を保存しました"
    )


if __name__ == "__main__":
    main()
