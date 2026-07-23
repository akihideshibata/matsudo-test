import io, json, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pandas as pd, requests

URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
STATION, OUT = "新橋", Path("departures.json")

def read(z, name):
    # GTFS内のCSVを文字列として読み込む
    return pd.read_csv(z.open(name), dtype=str).fillna("")

def next_weekday():
    # 次の平日を対象にする
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def active_services(z, day):
    # 指定日に運行するservice_idを取得
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
    # 最新GTFSをネットから取得
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    day = next_weekday()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
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

        departures = [{
            "time": x.departure_time[:5],
            "route": x.route_short_name or x.route_long_name or "都営線",
            "destination": x.trip_headsign or "行先情報なし"
        } for x in data.itertuples()]

    OUT.write_text(json.dumps({
        "station": STATION,
        "service_date": day.isoformat(),
        "fetched_at": datetime.now(
            timezone(timedelta(hours=9))
        ).isoformat(timespec="minutes"),
        "source": "東京都交通局・公共交通オープンデータセンター",
        "departures": departures
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{STATION}駅の発車時刻を{len(departures)}件保存しました")

if __name__ == "__main__":
    main()
