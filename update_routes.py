import gzip, json, math, os, re, shutil, time, zipfile
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

# ============================================================
# 1. GTFSデータソース
# ============================================================
BASIC_SOURCES = {
    "toei": {
        "name": "東京都交通局",
        "label": "都営",
        "url": "https://api.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip",
        "token_env": "ODPT_API_KEY",
    },
    "tokyometro": {
        "name": "東京メトロ",
        "label": "東京メトロ",
        "url": "https://api.odpt.org/api/v4/files/TokyoMetro/data/TokyoMetro-Train-GTFS.zip",
        "token_env": "ODPT_API_KEY",
    },
    "twr": {
        "name": "東京臨海高速鉄道",
        "label": "りんかい線",
        "url": "https://api.odpt.org/api/v4/files/TWR/data/TWR-Train-GTFS.zip",
        "token_env": "ODPT_API_KEY",
    },
    "mir": {
        "name": "首都圏新都市鉄道",
        "label": "つくばエクスプレス",
        "url": "https://api.odpt.org/api/v4/files/MIR/data/MIR-Train-GTFS.zip",
        "token_env": "ODPT_API_KEY",
    },
    "tamamonorail": {
        "name": "多摩都市モノレール",
        "label": "多摩モノレール",
        "url": "https://api.odpt.org/api/v4/files/TamaMonorail/data/TamaMonorail-Train-GTFS.zip",
        "token_env": "ODPT_API_KEY",
    },
}

CHALLENGE_SOURCES = {
    "jreast": {
        "name": "JR東日本",
        "label": "JR東日本",
        "url": (
            "https://api-challenge.odpt.org/api/v4/files/"
            "JR-East/data/JR-East-Train-GTFS.zip"
        ),
        "token_env": "ODPT_CHALLENGE_API_KEY",
    },
}

# ============================================================
# 2. 保存先・外部API
# ============================================================
DATA = Path("data")
BASIC_DIR = DATA / "gtfs/basic"
CHALLENGE_DIR = DATA / "gtfs/challenge"
BASIC_STATE = DATA / "gtfs_basic_state.json"
CHALLENGE_STATE = DATA / "gtfs_challenge_state.json"

BASIC_OUT = Path("direct_timetable_basic.json.gz")
CHALLENGE_OUT = Path("direct_timetable_challenge.json.gz")
BUILD_CONFIG = Path("build_config.json")

LOCATIONS = Path("station_locations.json")
UNRESOLVED = Path("unresolved_stations.json")
MUNICIPALITY_STATS = Path("municipality_stats.json")
MUNICIPALITY_STATE = DATA / "municipality_stats_state.json"

REVERSE_URL = (
    "https://mreversegeocoder.gsi.go.jp/"
    "reverse-geocoder/LonLatToAddress"
)
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"
ESTAT_URL = (
    "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
)

RENT_STATS_ID = "0004021492"
RENT_SOURCE_YEAR = 2023
RENT_REFERENCE_AREA = 25

JST = timezone(timedelta(hours=9))
CHECK_DAYS = 7
MERGE_DISTANCE_M = 500


# ============================================================
# 3. 共通処理
# ============================================================
def now():
    return datetime.now(JST)


def env_bool(name):
    return os.getenv(name, "false").strip().lower() == "true"


def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
    )

    if path.suffix == ".gz":
        with gzip.open(
            path,
            "wt",
            encoding="utf-8",
            compresslevel=9,
        ) as f:
            f.write(text)
    else:
        path.write_text(text, encoding="utf-8")


def read(z, name):
    return pd.read_csv(z.open(name), dtype=str).fillna("")


def as_list(value):
    return value if isinstance(value, list) else ([value] if value else [])


def normalize(text):
    return (
        str(text)
        .replace("平方メートル", "㎡")
        .replace("ｍ2", "㎡")
        .replace("m2", "㎡")
        .replace("１", "1")
        .replace("０", "0")
        .replace("　", "")
        .replace(" ", "")
    )


def station_base(name):
    # 「東京駅」と「東京」を同一視
    return re.sub(r"駅$", "", str(name).strip())


def representative_days():
    # 明日以降の平日・土曜・日曜を1日ずつ選ぶ
    start = date.today() + timedelta(days=1)

    def find(predicate):
        day = start
        while not predicate(day):
            day += timedelta(days=1)
        return day

    return {
        "weekday": find(lambda x: x.weekday() < 5),
        "saturday": find(lambda x: x.weekday() == 5),
        "sunday": find(lambda x: x.weekday() == 6),
    }


def distance_m(lat1, lon1, lat2, lon2):
    # 2地点間の直線距離
    radius = 6_371_000
    lat1, lat2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlat = lat2 - lat1
    dlon = math.radians(float(lon2) - float(lon1))
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(value))


def safe_error(error):
    # アクセストークンをログへ出さず、エラー種別だけ表示
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", "")
    return (
        f"{type(error).__name__}"
        f"{f'（HTTP {status}）' if status else ''}"
    )


# ============================================================
# 4. GTFS取得
# ============================================================
def download_sources(sources, directory, state_path):
    directory.mkdir(parents=True, exist_ok=True)
    states = load_json(state_path)
    force = env_bool("FORCE_UPDATE")

    for key, source in sources.items():
        token = os.getenv(source["token_env"], "").strip()

        if not token:
            raise RuntimeError(
                f'GitHub Secret「{source["token_env"]}」が'
                f"設定されていません"
            )

        cache = directory / f"{key}.zip"
        state = states.get(key, {})
        checked = (
            datetime.fromisoformat(state["checked_at"])
            if state.get("checked_at")
            else None
        )

        if (
            cache.exists()
            and checked
            and not force
            and now() - checked < timedelta(days=CHECK_DAYS)
        ):
            print(f'{source["name"]}：保存済みGTFSを使用')
            continue

        headers = {}

        if not force:
            if state.get("etag"):
                headers["If-None-Match"] = state["etag"]
            if state.get("last_modified"):
                headers["If-Modified-Since"] = state["last_modified"]

        try:
            response = requests.get(
                source["url"],
                params={"acl:consumerKey": token},
                headers=headers,
                timeout=240,
            )

            if response.status_code == 304 and cache.exists():
                state["checked_at"] = now().isoformat(
                    timespec="minutes"
                )
                states[key] = state
                print(f'{source["name"]}：変更なし')
                continue

            response.raise_for_status()

            if not zipfile.is_zipfile(BytesIO(response.content)):
                raise ValueError("取得内容がZIP形式ではありません")

            cache.write_bytes(response.content)
            states[key] = {
                "name": source["name"],
                "checked_at": now().isoformat(timespec="minutes"),
                "fetched_at": now().isoformat(timespec="minutes"),
                "etag": response.headers.get("ETag", ""),
                "last_modified": response.headers.get(
                    "Last-Modified",
                    "",
                ),
            }
            print(f'{source["name"]}：最新GTFSを取得')

        except Exception as error:
            if not cache.exists():
                raise RuntimeError(
                    f'{source["name"]}のGTFS取得失敗：'
                    f"{safe_error(error)}"
                ) from error

            print(
                f'::warning::{source["name"]}の取得失敗。'
                f'保存済みGTFSを使用：{safe_error(error)}'
            )

    save_json(state_path, states)
    return states


def active_services(z, day):
    # 指定日に有効なservice_idを取得
    ymd = day.strftime("%Y%m%d")
    weekday = day.strftime("%A").lower()
    service_ids = set()

    if "calendar.txt" in z.namelist():
        calendar = read(z, "calendar.txt")
        service_ids = set(
            calendar.loc[
                (calendar["start_date"] <= ymd)
                & (calendar["end_date"] >= ymd)
                & (calendar[weekday] == "1"),
                "service_id",
            ]
        )

    if "calendar_dates.txt" in z.namelist():
        special = read(z, "calendar_dates.txt")
        special = special[special["date"] == ymd]

        service_ids |= set(
            special.loc[
                special["exception_type"] == "1",
                "service_id",
            ]
        )
        service_ids -= set(
            special.loc[
                special["exception_type"] == "2",
                "service_id",
            ]
        )

    return service_ids


# ============================================================
# 5. GTFS読込
# ============================================================
def add_prefix(frame, columns, prefix):
    # 事業者間で同じIDがあっても衝突しないようにする
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].apply(
                lambda value: f"{prefix}:{value}" if value else ""
            )


def load_feeds(sources, directory):
    feeds, stop_frames = {}, []

    for key, source in sources.items():
        cache = directory / f"{key}.zip"

        if not cache.exists():
            print(f'::warning::{source["name"]}のGTFSがありません')
            continue

        with zipfile.ZipFile(cache) as z:
            required = {
                "stops.txt",
                "stop_times.txt",
                "trips.txt",
                "routes.txt",
            }
            missing = required - set(z.namelist())

            if missing:
                print(
                    f'::warning::{source["name"]}を除外：'
                    f'不足ファイル {sorted(missing)}'
                )
                continue

            stops = read(z, "stops.txt")
            stop_times = read(z, "stop_times.txt")
            trips = read(z, "trips.txt")
            routes = read(z, "routes.txt")

        add_prefix(stops, ["stop_id", "parent_station"], key)
        add_prefix(stop_times, ["stop_id", "trip_id"], key)
        add_prefix(
            trips,
            ["trip_id", "route_id", "service_id"],
            key,
        )
        add_prefix(routes, ["route_id"], key)

        feeds[key] = {
            "source": source,
            "cache": cache,
            "stops": stops,
            "stop_times": stop_times,
            "trips": trips,
            "routes": routes,
        }

        valid = stops[
            (stops["stop_id"] != "")
            & (stops["stop_name"] != "")
            & (stops["stop_lat"] != "")
            & (stops["stop_lon"] != "")
        ][
            [
                "stop_id",
                "stop_name",
                "stop_lat",
                "stop_lon",
            ]
        ].copy()

        valid["operator"] = source["label"]
        stop_frames.append(valid)

    if not feeds:
        raise RuntimeError("利用可能なGTFSがありません")

    return feeds, pd.concat(stop_frames, ignore_index=True)


# ============================================================
# 6. 駅統合
# ============================================================
def build_station_map(stops):
    # 同名かつ500m以内の停留所を同一駅として扱う
    groups, mapping = {}, {}

    for row in stops.itertuples(index=False):
        base = station_base(row.stop_name)
        matched = None

        for group in groups.get(base, []):
            if (
                distance_m(
                    row.stop_lat,
                    row.stop_lon,
                    group["lat"],
                    group["lon"],
                )
                <= MERGE_DISTANCE_M
            ):
                matched = group
                break

        if matched is None:
            matched = {
                "lat": row.stop_lat,
                "lon": row.stop_lon,
                "operators": set(),
                "stop_ids": [],
            }
            groups.setdefault(base, []).append(matched)

        matched["operators"].add(row.operator)
        matched["stop_ids"].append(row.stop_id)

    for base, clusters in groups.items():
        for cluster in clusters:
            name = (
                base
                if len(clusters) == 1
                else (
                    f'{base}（'
                    f'{"・".join(sorted(cluster["operators"]))}'
                    f"）"
                )
            )

            for stop_id in cluster["stop_ids"]:
                mapping[stop_id] = name

    return mapping


# ============================================================
# 7. 所在地
# ============================================================
def get_municipalities(session):
    response = session.get(MUNI_URL, timeout=30)
    response.raise_for_status()
    result = {}

    for _, value in re.findall(
        r'MUNI_ARRAY\["(\d+)"\]\s*=\s*[\'"]([^\'"]+)',
        response.content.decode("utf-8-sig"),
    ):
        parts = value.split(",")

        if len(parts) >= 4:
            # 正式な5桁自治体コードで保存
            result[parts[2].zfill(5)] = parts[1] + parts[3]

    return result


def update_locations(stops):
    locations = load_json(LOCATIONS)
    unresolved = []
    stations = stops.drop_duplicates("stop_id")

    # 新規駅または座標変更駅だけ国土地理院へ問い合わせる
    rows = [
        row
        for row in stations.itertuples(index=False)
        if row.stop_id not in locations
        or locations[row.stop_id].get("lat") != row.stop_lat
        or locations[row.stop_id].get("lon") != row.stop_lon
    ]

    if not rows:
        print("新しい駅なし：住所照会を省略")
        return locations

    session = requests.Session()
    session.headers["User-Agent"] = "reverse-commute-app/1.0"
    municipalities = get_municipalities(session)

    print(f"住所未登録：{len(rows)}件")

    for row in rows:
        try:
            response = session.get(
                REVERSE_URL,
                params={
                    "lat": row.stop_lat,
                    "lon": row.stop_lon,
                },
                timeout=20,
            )
            response.raise_for_status()

            code = response.json().get(
                "results",
                {},
            ).get("muniCd", "")
            location = municipalities.get(code, "")

            if not location:
                raise ValueError(
                    f"自治体を判定できません：{code}"
                )

            locations[row.stop_id] = {
                "name": row.stop_name,
                "lat": row.stop_lat,
                "lon": row.stop_lon,
                "municipality_code": code,
                "location": location,
                "updated_at": now().isoformat(timespec="minutes"),
            }

        except Exception as error:
            unresolved.append(
                {
                    "stop_id": row.stop_id,
                    "name": row.stop_name,
                    "lat": row.stop_lat,
                    "lon": row.stop_lon,
                    "error": str(error),
                }
            )
            print(f"::warning::住所未判定：{row.stop_name}")

        time.sleep(0.15)

    save_json(LOCATIONS, locations)
    save_json(UNRESOLVED, unresolved)
    return locations


# ============================================================
# 8. e-Stat家賃データ
# ============================================================
def estat_classes(data):
    result = {}

    for obj in as_list(data["CLASS_INF"]["CLASS_OBJ"]):
        result[str(obj["@id"])] = {
            "classes": {
                str(item.get("@code", "")): {
                    "name": str(item.get("@name", ""))
                }
                for item in as_list(obj.get("CLASS"))
            }
        }

    return result


def find_code(classes, words):
    words = [normalize(word) for word in words]
    matches = []

    for code, info in classes.items():
        name = normalize(info["name"])

        if all(word in name for word in words):
            matches.append((len(name), code))

    return min(matches)[1] if matches else None


def select_rent_dimensions(objects):
    filters, found = {}, False

    for dimension, obj in objects.items():
        if dimension in ("area", "time"):
            continue

        code = find_code(
            obj["classes"],
            ["延べ面積1㎡当たり家賃"],
        )

        if code:
            found = True
        else:
            code = find_code(obj["classes"], ["総数"])

        if code:
            filters[dimension] = code

    if not found:
        raise ValueError(
            "家賃単価の分類コードを特定できません"
        )

    return filters


def parse_number(value):
    text = str(value).replace(",", "").strip()

    if text in ("", "-", "…", "...", "X", "x", "***"):
        return None

    try:
        return float(text)
    except ValueError:
        return None


def is_municipality_code(code):
    return (
        len(code) == 5
        and code.isdigit()
        and code != "00000"
        and not code.endswith("000")
    )


def fetch_rent_stats():
    app_id = os.getenv("ESTAT_APP_ID", "").strip()

    if not app_id:
        raise RuntimeError(
            "GitHub Secret「ESTAT_APP_ID」が設定されていません"
        )

    print("e-Statから全国の家賃データを取得")

    response = requests.get(
        ESTAT_URL,
        params={
            "appId": app_id,
            "statsDataId": RENT_STATS_ID,
            "lang": "J",
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
            "limit": 100000,
        },
        timeout=180,
    )
    response.raise_for_status()

    root = response.json()["GET_STATS_DATA"]

    if int(root["RESULT"].get("STATUS", -1)) != 0:
        raise RuntimeError(
            root["RESULT"].get(
                "ERROR_MSG",
                "e-Stat APIエラー",
            )
        )

    statistical = root["STATISTICAL_DATA"]
    objects = estat_classes(statistical)
    filters = select_rent_dimensions(objects)
    municipalities = {}

    area_names = {
        code: item["name"]
        for code, item in objects["area"]["classes"].items()
    }

    for value in as_list(
        statistical.get("DATA_INF", {}).get("VALUE", [])
    ):
        area = str(value.get("@area", ""))

        if not is_municipality_code(area):
            continue

        if any(
            str(value.get(f"@{dimension}", "")) != code
            for dimension, code in filters.items()
        ):
            continue

        rent = parse_number(value.get("$"))

        if rent is not None:
            municipalities[area] = {
                "municipality": area_names.get(area, ""),
                "rent_per_sqm": round(rent),
                "rent_25sqm": round(
                    rent * RENT_REFERENCE_AREA
                ),
            }

    if not municipalities:
        raise RuntimeError("家賃データを抽出できません")

    output = {
        "source": "令和5年住宅・土地統計調査",
        "source_year": RENT_SOURCE_YEAR,
        "stats_data_id": RENT_STATS_ID,
        "reference_area_sqm": RENT_REFERENCE_AREA,
        "fetched_at": now().isoformat(timespec="minutes"),
        "municipalities": municipalities,
    }

    save_json(MUNICIPALITY_STATS, output)
    save_json(
        MUNICIPALITY_STATE,
        {
            "rent_source_year": RENT_SOURCE_YEAR,
            "stats_data_id": RENT_STATS_ID,
            "checked_at": now().isoformat(timespec="minutes"),
        },
    )

    print(f"家賃データ：{len(municipalities)}自治体")
    return output


def update_municipality_stats():
    if (
        MUNICIPALITY_STATS.exists()
        and not env_bool("FORCE_STATS_UPDATE")
    ):
        print("保存済み自治体統計を使用")
        return load_json(MUNICIPALITY_STATS)

    try:
        return fetch_rent_stats()

    except Exception as error:
        if MUNICIPALITY_STATS.exists():
            print(f"::warning::家賃更新失敗：{error}")
            return load_json(MUNICIPALITY_STATS)
        raise


# ============================================================
# 9. 時刻表生成
# ============================================================
def route_name(row, fallback):
    return (
        str(row.route_long_name)
        or str(row.route_short_name)
        or fallback
    )


def build_timetable(key, feed, station_map, day):
    with zipfile.ZipFile(feed["cache"]) as z:
        services = {
            f"{key}:{service_id}"
            for service_id in active_services(z, day)
        }

    if not services:
        return pd.DataFrame(), []

    stops = feed["stops"]
    stop_times = feed["stop_times"].copy()
    trips = feed["trips"].copy()
    routes = feed["routes"].copy()

    if "trip_headsign" not in trips.columns:
        trips["trip_headsign"] = ""

    for column in ("route_short_name", "route_long_name"):
        if column not in routes.columns:
            routes[column] = ""

    stop_times = stop_times[
        (stop_times["arrival_time"] != "")
        & (stop_times["departure_time"] != "")
    ].copy()

    stop_times["stop_sequence"] = pd.to_numeric(
        stop_times["stop_sequence"],
        errors="coerce",
    )
    stop_times = stop_times.dropna(
        subset=["stop_sequence"]
    )

    day_trips = trips[
        trips["service_id"].isin(services)
    ].merge(
        routes[
            [
                "route_id",
                "route_short_name",
                "route_long_name",
            ]
        ],
        on="route_id",
        how="left",
    )

    joined = (
        stop_times.merge(
            day_trips[
                [
                    "trip_id",
                    "trip_headsign",
                    "route_short_name",
                    "route_long_name",
                ]
            ],
            on="trip_id",
        )
        .merge(
            stops[["stop_id", "stop_name"]],
            on="stop_id",
        )
        .sort_values(
            ["trip_id", "stop_sequence"]
        )
    )

    joined["stop_name"] = (
        joined["stop_id"]
        .map(station_map)
        .fillna(joined["stop_name"])
    )
    joined["route"] = joined.apply(
        lambda row: route_name(
            row,
            feed["source"]["label"],
        ),
        axis=1,
    )
    joined["operator"] = feed["source"]["name"]

    output = []

    for _, group in joined.groupby(
        "trip_id",
        sort=False,
    ):
        if len(group) < 2:
            continue

        first = group.iloc[0]
        output.append(
            {
                "operator": feed["source"]["name"],
                "route": first["route"],
                "destination": (
                    first["trip_headsign"]
                    or "行先情報なし"
                ),
                "stops": [
                    [
                        row.stop_name,
                        row.arrival_time[:5],
                        row.departure_time[:5],
                    ]
                    for row in group.itertuples()
                ],
            }
        )

    return joined, output


def build_output(
    sources,
    directory,
    state,
    stats,
    days,
    output_path,
):
    feeds, all_stops = load_feeds(
        sources,
        directory,
    )
    station_map = build_station_map(all_stops)
    locations = update_locations(all_stops)
    rents = stats.get("municipalities", {})

    frames = {
        day_type: []
        for day_type in days
    }
    timetables = {
        day_type: []
        for day_type in days
    }

    for key, feed in feeds.items():
        for day_type, day in days.items():
            frame, trips = build_timetable(
                key,
                feed,
                station_map,
                day,
            )

            if not frame.empty:
                frames[day_type].append(frame)

            timetables[day_type].extend(trips)

            print(
                f'{feed["source"]["name"]} {day_type}：'
                f"{len(trips)}列車"
            )

    all_frames = [
        frame
        for day_frames in frames.values()
        for frame in day_frames
    ]

    if not all_frames:
        raise RuntimeError(
            "対象日の列車を生成できません"
        )

    combined = pd.concat(
        all_frames,
        ignore_index=True,
    )

    station_routes = (
        combined.groupby("stop_name")["route"]
        .agg(lambda values: sorted(set(values)))
        .to_dict()
    )
    station_operators = (
        combined.groupby("stop_name")["operator"]
        .agg(lambda values: sorted(set(values)))
        .to_dict()
    )

    details = {}
    coordinate_rows = []

    for row in all_stops.itertuples(index=False):
        name = station_map.get(
            row.stop_id,
            station_base(row.stop_name),
        )
        location = locations.get(row.stop_id, {})
        code = str(
            location.get(
                "municipality_code",
                "",
            )
        )
        rent = rents.get(code, {})

        # 統合駅の代表座標を作るため全停留所座標を保存
        coordinate_rows.append(
            {
                "name": name,
                "lat": float(row.stop_lat),
                "lon": float(row.stop_lon),
            }
        )

        if name not in details or location.get("location"):
            details[name] = {
                "location": location.get(
                    "location",
                    "所在地未登録",
                ),
                "municipality_code": code,
                "rent_per_sqm": rent.get(
                    "rent_per_sqm"
                ),
                "rent_25sqm": rent.get(
                    "rent_25sqm"
                ),
            }

    # 同一駅に属する全停留所座標の平均を代表座標にする
    coordinates = (
        pd.DataFrame(coordinate_rows)
        .groupby("name")[["lat", "lon"]]
        .mean()
        .to_dict("index")
    )

    output = {
        "service_date": days["weekday"].isoformat(),
        "service_dates": {
            key: value.isoformat()
            for key, value in days.items()
        },
        "generated_at": now().isoformat(
            timespec="minutes"
        ),
        "rent_source_year": stats.get(
            "source_year"
        ),
        "rent_reference_area_sqm": stats.get(
            "reference_area_sqm"
        ),
        "sources": [
            {
                "id": key,
                "name": source["name"],
                "fetched_at": state.get(
                    key,
                    {},
                ).get(
                    "fetched_at",
                    "",
                ),
            }
            for key, source in sources.items()
        ],
        "stations": [
            {
                "name": name,
                "routes": routes,
                "operators": station_operators.get(
                    name,
                    [],
                ),
                "lat": (
                    round(
                        coordinates[name]["lat"],
                        7,
                    )
                    if name in coordinates
                    else None
                ),
                "lon": (
                    round(
                        coordinates[name]["lon"],
                        7,
                    )
                    if name in coordinates
                    else None
                ),
                **details.get(
                    name,
                    {
                        "location": "所在地未登録",
                        "municipality_code": "",
                        "rent_per_sqm": None,
                        "rent_25sqm": None,
                    },
                ),
            }
            for name, routes in sorted(
                station_routes.items()
            )
        ],
        "timetables": timetables,
        "trips": timetables["weekday"],
    }

    save_json(
        output_path,
        output,
        compact=True,
    )

    print(
        f"{len(feeds)}事業者、"
        f"{len(station_routes)}駅を"
        f"{output_path}へ保存"
    )


# ============================================================
# 10. 実行
# ============================================================
def purge_challenge_data():
    # JR由来のキャッシュ・状態・公開データを削除
    if CHALLENGE_DIR.exists():
        shutil.rmtree(CHALLENGE_DIR)

    for path in (
        CHALLENGE_STATE,
        CHALLENGE_OUT,
    ):
        if path.exists():
            path.unlink()

    print(
        "JR東日本のチャレンジ由来データを削除"
    )


def main():
    enable_jr = env_bool("ENABLE_JR")

    if env_bool("PURGE_CHALLENGE_DATA"):
        purge_challenge_data()
        enable_jr = False

    stats = update_municipality_stats()
    days = representative_days()

    # 通常5社は常に最新の代表日で再生成
    basic_state = download_sources(
        BASIC_SOURCES,
        BASIC_DIR,
        BASIC_STATE,
    )
    build_output(
        BASIC_SOURCES,
        BASIC_DIR,
        basic_state,
        stats,
        days,
        BASIC_OUT,
    )

    # JRは設定がONのときだけ最新の代表日で再生成
    if enable_jr:
        challenge_state = download_sources(
            CHALLENGE_SOURCES,
            CHALLENGE_DIR,
            CHALLENGE_STATE,
        )
        build_output(
            CHALLENGE_SOURCES,
            CHALLENGE_DIR,
            challenge_state,
            stats,
            days,
            CHALLENGE_OUT,
        )

    elif CHALLENGE_OUT.exists():
        CHALLENGE_OUT.unlink()
        print(
            "JR東日本をOFF：公開用JRデータを削除"
        )

    save_json(
        BUILD_CONFIG,
        {
            "jr_enabled": enable_jr,
            "challenge_data_enabled": enable_jr,
            "generated_at": now().isoformat(
                timespec="minutes"
            ),
            "basic_output": BASIC_OUT.name,
            "challenge_output": (
                CHALLENGE_OUT.name
                if enable_jr
                else None
            ),
        },
    )

    print(
        f'生成完了：JR東日本 '
        f'{"ON" if enable_jr else "OFF"}'
    )


if __name__ == "__main__":
    main()
