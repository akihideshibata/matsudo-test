import json, os, re, time, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests

GTFS_URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
REVERSE_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"
ESTAT_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
RENT_STATS_ID, RENT_SOURCE_YEAR, RENT_REFERENCE_AREA = "0004021492", 2023, 25
CACHE, STATE = Path("data/toei_gtfs.zip"), Path("data/gtfs_state.json")
LOCATIONS, UNRESOLVED = Path("station_locations.json"), Path("unresolved_stations.json")
MUNICIPALITY_STATS = Path("municipality_stats.json")
MUNICIPALITY_STATE = Path("data/municipality_stats_state.json")
OUT, JST = Path("direct_timetable.json"), timezone(timedelta(hours=9))


# ============================================================
# 共通
# ============================================================
def now(): return datetime.now(JST)


def load_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})


def save_json(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        value, ensure_ascii=False, indent=None if compact else 2,
        separators=(",", ":") if compact else None
    ), encoding="utf-8")


def read(z, name): return pd.read_csv(z.open(name), dtype=str).fillna("")


def as_list(value): return value if isinstance(value, list) else ([value] if value else [])


def normalize(text):
    return str(text).replace("平方メートル", "㎡").replace("ｍ2", "㎡").replace(
        "m2", "㎡").replace("１", "1").replace("０", "0").replace("　", "").replace(" ", "")


def representative_days():
    # 次の平日・土曜・日曜
    start = date.today() + timedelta(days=1)

    def find(predicate):
        d = start
        while not predicate(d): d += timedelta(days=1)
        return d

    return {
        "weekday": find(lambda d: d.weekday() < 5),
        "saturday": find(lambda d: d.weekday() == 5),
        "sunday": find(lambda d: d.weekday() == 6),
    }


# ============================================================
# GTFS
# ============================================================
def get_gtfs():
    CACHE.parent.mkdir(exist_ok=True)
    state, force = load_json(STATE), os.getenv("FORCE_UPDATE", "false").lower() == "true"
    checked = datetime.fromisoformat(state["checked_at"]) if state.get("checked_at") else None

    if CACHE.exists() and checked and not force and now() - checked < timedelta(days=7):
        print("保存済みGTFSを使用")
        return

    headers = {}
    if not force:
        if state.get("etag"): headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"): headers["If-Modified-Since"] = state["last_modified"]

    try:
        r = requests.get(GTFS_URL, headers=headers, timeout=120)
        if r.status_code == 304 and CACHE.exists():
            state["checked_at"] = now().isoformat(timespec="minutes")
            save_json(STATE, state)
            print("GTFSに変更なし")
            return

        r.raise_for_status()
        CACHE.write_bytes(r.content)
        save_json(STATE, {
            "checked_at": now().isoformat(timespec="minutes"),
            "fetched_at": now().isoformat(timespec="minutes"),
            "etag": r.headers.get("ETag", ""),
            "last_modified": r.headers.get("Last-Modified", ""),
        })
        print("最新GTFSを取得")
    except requests.RequestException:
        if not CACHE.exists(): raise
        print("取得失敗のため保存済みGTFSを使用")


def active_services(z, day):
    ymd, weekday = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    calendar = read(z, "calendar.txt")
    ids = set(calendar.loc[
        (calendar["start_date"] <= ymd) & (calendar["end_date"] >= ymd)
        & (calendar[weekday] == "1"), "service_id"
    ])

    if "calendar_dates.txt" in z.namelist():
        special = read(z, "calendar_dates.txt")
        special = special[special["date"] == ymd]
        ids |= set(special.loc[special["exception_type"] == "1", "service_id"])
        ids -= set(special.loc[special["exception_type"] == "2", "service_id"])
    return ids


# ============================================================
# 所在地
# ============================================================
def get_municipalities(session):
    r = session.get(MUNI_URL, timeout=30)
    r.raise_for_status()
    result = {}

    for code, value in re.findall(
        r'MUNI_ARRAY\["(\d+)"\]\s*=\s*[\'"]([^\'"]+)',
        r.content.decode("utf-8-sig"),
    ):
        parts = value.split(",")
        if len(parts) >= 4: result[code] = parts[1] + parts[3]
    return result


def update_locations(stops):
    locations, unresolved = load_json(LOCATIONS), []
    stations = stops[
        (stops["stop_id"] != "") & (stops["stop_lat"] != "") & (stops["stop_lon"] != "")
    ][["stop_id", "stop_name", "stop_lat", "stop_lon"]].drop_duplicates("stop_id")

    rows = [
        row for row in stations.itertuples(index=False)
        if row.stop_id not in locations
        or locations[row.stop_id].get("lat") != row.stop_lat
        or locations[row.stop_id].get("lon") != row.stop_lon
    ]

    if not rows:
        print("新しい駅なし：住所照会を省略")
        return locations

    session = requests.Session()
    session.headers["User-Agent"] = "reverse-commute-prototype/1.0"
    municipalities = get_municipalities(session)
    print(f"住所未登録のstop_id：{len(rows)}件")

    for row in rows:
        try:
            r = session.get(REVERSE_URL, params={
                "lat": row.stop_lat, "lon": row.stop_lon
            }, timeout=20)
            r.raise_for_status()
            code = r.json().get("results", {}).get("muniCd", "")
            location = municipalities.get(code, "")
            if not location: raise ValueError(f"自治体を判定できません：{code}")

            locations[row.stop_id] = {
                "name": row.stop_name, "lat": row.stop_lat, "lon": row.stop_lon,
                "municipality_code": code, "location": location,
                "updated_at": now().isoformat(timespec="minutes"),
            }
            print(f"住所追加：{row.stop_name} → {location}")
        except Exception as e:
            unresolved.append({
                "stop_id": row.stop_id, "name": row.stop_name,
                "lat": row.stop_lat, "lon": row.stop_lon, "error": str(e),
            })
            print(f"::warning::住所未判定：{row.stop_name}（{row.stop_id}）")
        time.sleep(.15)

    save_json(LOCATIONS, locations)
    save_json(UNRESOLVED, unresolved)
    return locations


# ============================================================
# e-Stat
# ============================================================
def estat_classes(data):
    result = {}
    for obj in as_list(data["CLASS_INF"]["CLASS_OBJ"]):
        result[str(obj["@id"])] = {
            "name": str(obj.get("@name", "")),
            "classes": {
                str(x.get("@code", "")): {
                    "name": str(x.get("@name", "")),
                    "unit": str(x.get("@unit", "")),
                }
                for x in as_list(obj.get("CLASS"))
            },
        }
    return result


def find_code(classes, words):
    words, matches = [normalize(x) for x in words], []
    for code, info in classes.items():
        name = normalize(info["name"])
        if all(x in name for x in words): matches.append((len(name), code))
    return min(matches)[1] if matches else None


def select_rent_dimensions(objects):
    filters, found = {}, False
    for dimension, obj in objects.items():
        if dimension in ("area", "time"): continue
        code = find_code(obj["classes"], ["延べ面積1㎡当たり家賃"])
        if code: found = True
        else: code = find_code(obj["classes"], ["総数"])
        if code: filters[dimension] = code
    if not found: raise ValueError("家賃単価の分類コードを特定できませんでした")
    return filters


def parse_number(value):
    text = str(value).replace(",", "").strip()
    if text in ("", "-", "…", "...", "X", "x", "***"): return None
    try: return float(text)
    except ValueError: return None


def is_municipality_code(code):
    return len(code) == 5 and code.isdigit() and code != "00000" and not code.endswith("000")


def fetch_rent_stats():
    app_id = os.getenv("ESTAT_APP_ID", "").strip()
    if not app_id: raise RuntimeError("GitHub SecretのESTAT_APP_IDが設定されていません")

    print("e-Statから全国の家賃データを取得")
    r = requests.get(ESTAT_URL, params={
        "appId": app_id, "statsDataId": RENT_STATS_ID, "lang": "J",
        "metaGetFlg": "Y", "cntGetFlg": "N", "limit": 100000,
    }, timeout=180)
    r.raise_for_status()
    root = r.json()["GET_STATS_DATA"]

    if int(root["RESULT"].get("STATUS", -1)) != 0:
        raise RuntimeError(root["RESULT"].get("ERROR_MSG", "e-Stat APIエラー"))

    statistical = root["STATISTICAL_DATA"]
    objects, municipalities = estat_classes(statistical), {}
    filters = select_rent_dimensions(objects)
    area_names = {code: x["name"] for code, x in objects["area"]["classes"].items()}

    for value in as_list(statistical.get("DATA_INF", {}).get("VALUE", [])):
        area = str(value.get("@area", ""))
        if not is_municipality_code(area): continue
        if any(str(value.get(f"@{dimension}", "")) != code
               for dimension, code in filters.items()): continue

        rent = parse_number(value.get("$"))
        if rent is not None:
            municipalities[area] = {
                "municipality": area_names.get(area, ""),
                "rent_per_sqm": round(rent),
                "rent_25sqm": round(rent * RENT_REFERENCE_AREA),
            }

    if not municipalities: raise RuntimeError("家賃データを抽出できませんでした")

    output = {
        "source": "令和5年住宅・土地統計調査",
        "source_year": RENT_SOURCE_YEAR,
        "stats_data_id": RENT_STATS_ID,
        "reference_area_sqm": RENT_REFERENCE_AREA,
        "fetched_at": now().isoformat(timespec="minutes"),
        "municipalities": municipalities,
    }
    save_json(MUNICIPALITY_STATS, output)
    save_json(MUNICIPALITY_STATE, {
        "rent_source_year": RENT_SOURCE_YEAR,
        "stats_data_id": RENT_STATS_ID,
        "checked_at": now().isoformat(timespec="minutes"),
    })
    print(f"家賃データ：{len(municipalities)}自治体を保存")
    return output


def update_municipality_stats():
    force = os.getenv("FORCE_STATS_UPDATE", "false").lower() == "true"
    if MUNICIPALITY_STATS.exists() and not force:
        print("保存済み自治体統計を使用：e-Stat照会なし")
        return load_json(MUNICIPALITY_STATS)

    try:
        return fetch_rent_stats()
    except Exception as e:
        if MUNICIPALITY_STATS.exists():
            print(f"::warning::家賃更新失敗のため保存済みデータを使用：{e}")
            return load_json(MUNICIPALITY_STATS)
        raise


# ============================================================
# ダイヤ生成
# ============================================================
def build_timetable(z, day, stop_times, trips, routes, stops):
    day_trips = trips[trips["service_id"].isin(active_services(z, day))].merge(
        routes[["route_id", "route_short_name", "route_long_name"]],
        on="route_id", how="left",
    )

    times = stop_times.merge(
        day_trips[["trip_id", "trip_headsign", "route_short_name", "route_long_name"]],
        on="trip_id",
    ).merge(
        stops[["stop_id", "stop_name"]], on="stop_id"
    ).sort_values(["trip_id", "stop_sequence"])

    times["route"] = times["route_short_name"].where(
        times["route_short_name"] != "", times["route_long_name"]
    ).replace("", "都営線")

    output = []
    for _, group in times.groupby("trip_id", sort=False):
        if len(group) < 2: continue
        first = group.iloc[0]
        output.append({
            "route": first["route"],
            "destination": first["trip_headsign"] or "行先情報なし",
            "stops": [[x.stop_name, x.arrival_time[:5], x.departure_time[:5]]
                      for x in group.itertuples()],
        })
    return times, output


def main():
    get_gtfs()
    stats, days = update_municipality_stats(), representative_days()

    with zipfile.ZipFile(CACHE) as z:
        stops, stop_times = read(z, "stops.txt"), read(z, "stop_times.txt")
        trips, routes = read(z, "trips.txt"), read(z, "routes.txt")
        locations = update_locations(stops)
        stop_times = stop_times[
            (stop_times["arrival_time"] != "") & (stop_times["departure_time"] != "")
        ].copy()
        stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)

        frames, timetables = {}, {}
        for name, day in days.items():
            frames[name], timetables[name] = build_timetable(
                z, day, stop_times, trips, routes, stops
            )
            print(f"{name}：{len(timetables[name])}列車")

        combined = pd.concat(frames.values(), ignore_index=True)
        station_routes = combined.groupby("stop_name")["route"].agg(
            lambda x: sorted(set(x))
        ).to_dict()

        rents, details = stats.get("municipalities", {}), {}
        for row in combined[["stop_id", "stop_name"]].drop_duplicates().itertuples(index=False):
            location = locations.get(row.stop_id, {})
            code = str(location.get("municipality_code", ""))
            rent = rents.get(code, {})
            if row.stop_name not in details or location.get("location"):
                details[row.stop_name] = {
                    "location": location.get("location", "所在地未登録"),
                    "municipality_code": code,
                    "rent_per_sqm": rent.get("rent_per_sqm"),
                    "rent_25sqm": rent.get("rent_25sqm"),
                }

    state = load_json(STATE)
    save_json(OUT, {
        "service_date": days["weekday"].isoformat(),
        "service_dates": {k: v.isoformat() for k, v in days.items()},
        "gtfs_fetched_at": state.get("fetched_at", ""),
        "generated_at": now().isoformat(timespec="minutes"),
        "rent_source_year": stats.get("source_year"),
        "rent_reference_area_sqm": stats.get("reference_area_sqm"),
        "stations": [{
            "name": name, "routes": routes,
            **details.get(name, {
                "location": "所在地未登録", "municipality_code": "",
                "rent_per_sqm": None, "rent_25sqm": None,
            }),
        } for name, routes in sorted(station_routes.items())],
        "timetables": timetables,
        "trips": timetables["weekday"],
    }, compact=True)

    print(f"{len(station_routes)}駅、平日・土曜・日曜ダイヤを保存しました")


if __name__ == "__main__":
    main()
