import json, os, re, time, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# ============================================================
# 設定
# ============================================================
GTFS_URL = "https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip"
REVERSE_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"
ESTAT_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

# 2023年住宅・土地統計調査：延べ面積1㎡当たり家賃
RENT_STATS_ID = "0004021521"
RENT_SOURCE_YEAR = 2023
RENT_REFERENCE_AREA = 25

CACHE = Path("data/toei_gtfs.zip")
STATE = Path("data/gtfs_state.json")
LOCATIONS = Path("station_locations.json")
UNRESOLVED = Path("unresolved_stations.json")
MUNICIPALITY_STATS = Path("municipality_stats.json")
MUNICIPALITY_STATE = Path("data/municipality_stats_state.json")
OUT = Path("direct_timetable.json")
JST = timezone(timedelta(hours=9))


# ============================================================
# 共通処理
# ============================================================
def now():
    return datetime.now(JST)


def load_json(path, default=None):
    # JSONがなければ既定値を返す
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})


def save_json(path, value, compact=False):
    # 親フォルダを作ってJSONを保存
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        ),
        encoding="utf-8",
    )


def read(z, name):
    # GTFS内のCSVをすべて文字列として読む
    return pd.read_csv(z.open(name), dtype=str).fillna("")


def as_list(value):
    # e-Statで1件だけ辞書になる場合もリストへ統一
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def normalize(text):
    # 表記ゆれを減らして比較する
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


def next_weekday():
    # 次の平日を対象日にする
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ============================================================
# GTFS更新
# ============================================================
def get_gtfs():
    # 7日以内なら保存済みGTFSを再利用
    CACHE.parent.mkdir(exist_ok=True)
    state = load_json(STATE)
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


# ============================================================
# 駅所在地
# ============================================================
def get_municipalities(session):
    # 自治体コードと「都道府県＋市区町村」の対応表を取得
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
    locations = load_json(LOCATIONS)
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
            print(f"::warning::住所未判定：{row.stop_name}（{row.stop_id}）")

        time.sleep(0.15)

    save_json(LOCATIONS, locations)
    save_json(UNRESOLVED, unresolved)
    return locations


# ============================================================
# e-Stat家賃データ
# ============================================================
def estat_classes(statistical_data):
    # 分類IDごとにコード、名称、単位を整理
    class_inf = statistical_data["CLASS_INF"]["CLASS_OBJ"]
    result = {}

    for obj in as_list(class_inf):
        classes = {}
        for item in as_list(obj.get("CLASS")):
            classes[str(item.get("@code", ""))] = {
                "name": str(item.get("@name", "")),
                "unit": str(item.get("@unit", "")),
                "level": str(item.get("@level", "")),
            }

        result[str(obj["@id"])] = {
            "name": str(obj.get("@name", "")),
            "classes": classes,
        }

    return result


def find_code(classes, words):
    # 指定語をすべて含む分類コードを探す
    words = [normalize(x) for x in words]
    matches = []

    for code, info in classes.items():
        name = normalize(info["name"])
        if all(word in name for word in words):
            matches.append((len(name), code))

    return min(matches)[1] if matches else None


def select_rent_dimensions(class_objects):
    # 家賃単価と各分類の「総数」に対応するコードを自動判定
    filters = {}

    for dimension_id, obj in class_objects.items():
        if dimension_id in ("area", "time"):
            continue

        classes = obj["classes"]
        rent_code = find_code(classes, ["延べ面積1㎡当たり家賃"])

        if rent_code:
            filters[dimension_id] = rent_code
            continue

        total_code = find_code(classes, ["総数"])
        if total_code:
            filters[dimension_id] = total_code

    if not any(
        "延べ面積1㎡当たり家賃" in normalize(
            obj["classes"].get(filters.get(dimension_id, ""), {}).get("name", "")
        )
        for dimension_id, obj in class_objects.items()
    ):
        raise ValueError("家賃単価の分類コードを特定できませんでした")

    return filters


def parse_number(value):
    # 秘匿値・欠損値を除き数値へ変換
    text = str(value).replace(",", "").strip()
    if text in ("", "-", "…", "...", "X", "x", "***"):
        return None

    try:
        return float(text)
    except ValueError:
        return None


def is_municipality_code(code):
    # 全国・都道府県を除き、市区町村コードだけを残す
    return (
        len(code) == 5
        and code.isdigit()
        and code != "00000"
        and not code.endswith("000")
    )


def fetch_rent_stats():
    # e-Statから全国の市区町村別家賃を取得
    app_id = os.getenv("ESTAT_APP_ID", "").strip()
    if not app_id:
        raise RuntimeError("GitHub SecretのESTAT_APP_IDが設定されていません")

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
    result = root["RESULT"]

    if int(result.get("STATUS", -1)) != 0:
        raise RuntimeError(result.get("ERROR_MSG", "e-Stat APIエラー"))

    statistical_data = root["STATISTICAL_DATA"]
    class_objects = estat_classes(statistical_data)
    filters = select_rent_dimensions(class_objects)
    area_names = {
        code: info["name"]
        for code, info in class_objects["area"]["classes"].items()
    }

    values = as_list(
        statistical_data.get("DATA_INF", {})
        .get("VALUE", [])
    )
    municipalities = {}

    for value in values:
        area_code = str(value.get("@area", ""))

        if not is_municipality_code(area_code):
            continue

        if any(
            str(value.get(f"@{dimension_id}", "")) != code
            for dimension_id, code in filters.items()
        ):
            continue

        rent_per_sqm = parse_number(value.get("$"))

        if rent_per_sqm is None:
            continue

        municipalities[area_code] = {
            "municipality": area_names.get(area_code, ""),
            "rent_per_sqm": round(rent_per_sqm),
            "rent_25sqm": round(rent_per_sqm * RENT_REFERENCE_AREA),
        }

    if not municipalities:
        raise RuntimeError(
            "家賃データを抽出できませんでした。"
            "e-Stat側の分類構造が変更された可能性があります"
        )

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
    # 初回または強制更新時だけe-Statへ接続
    force = os.getenv("FORCE_STATS_UPDATE", "false").lower() == "true"

    if MUNICIPALITY_STATS.exists() and not force:
        print("保存済み自治体統計を使用：e-Stat照会なし")
        return load_json(MUNICIPALITY_STATS)

    try:
        return fetch_rent_stats()

    except Exception as e:
        # 既存データがあればAPI障害時も処理を続ける
        if MUNICIPALITY_STATS.exists():
            print(f"::warning::家賃更新失敗のため保存済みデータを使用：{e}")
            return load_json(MUNICIPALITY_STATS)
        raise


# ============================================================
# 時刻表JSON生成
# ============================================================
def main():
    get_gtfs()
    stats = update_municipality_stats()
    municipality_rents = stats.get("municipalities", {})
    day = next_weekday()

    with zipfile.ZipFile(CACHE) as z:
        stops = read(z, "stops.txt")
        times = read(z, "stop_times.txt")
        trips = read(z, "trips.txt")
        routes = read(z, "routes.txt")
        locations = update_locations(stops)

        # 時刻がない行を除外
        times = times[
            (times["arrival_time"] != "")
            & (times["departure_time"] != "")
        ].copy()
        times["stop_sequence"] = times["stop_sequence"].astype(int)

        # 対象日の列車だけに絞る
        trips = trips[
            trips["service_id"].isin(active_services(z, day))
        ].merge(
            routes[["route_id", "route_short_name", "route_long_name"]],
            on="route_id",
            how="left",
        )

        times = (
            times.merge(
                trips[[
                    "trip_id",
                    "trip_headsign",
                    "route_short_name",
                    "route_long_name",
                ]],
                on="trip_id",
            )
            .merge(stops[["stop_id", "stop_name"]], on="stop_id")
            .sort_values(["trip_id", "stop_sequence"])
        )

        times["route"] = times["route_short_name"].where(
            times["route_short_name"] != "",
            times["route_long_name"],
        ).replace("", "都営線")

        station_routes = (
            times.groupby("stop_name")["route"]
            .agg(lambda x: sorted(set(x)))
            .to_dict()
        )

        # 駅名ごとに所在地・自治体コード・家賃を整理
        station_details = {}

        for row in times[["stop_id", "stop_name"]].drop_duplicates().itertuples(index=False):
            location = locations.get(row.stop_id, {})
            code = str(location.get("municipality_code", ""))
            rent = municipality_rents.get(code, {})

            if row.stop_name not in station_details or location.get("location"):
                station_details[row.stop_name] = {
                    "location": location.get("location", "所在地未登録"),
                    "municipality_code": code,
                    "rent_per_sqm": rent.get("rent_per_sqm"),
                    "rent_25sqm": rent.get("rent_25sqm"),
                }

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

    state = load_json(STATE)

    save_json(OUT, {
        "service_date": day.isoformat(),
        "gtfs_fetched_at": state.get("fetched_at", ""),
        "generated_at": now().isoformat(timespec="minutes"),
        "rent_source_year": stats.get("source_year"),
        "rent_reference_area_sqm": stats.get("reference_area_sqm"),
        "stations": [
            {
                "name": name,
                "routes": routes,
                **station_details.get(name, {
                    "location": "所在地未登録",
                    "municipality_code": "",
                    "rent_per_sqm": None,
                    "rent_25sqm": None,
                }),
            }
            for name, routes in sorted(station_routes.items())
        ],
        "trips": output_trips,
    }, compact=True)

    print(f"{len(output_trips)}列車、{len(station_routes)}駅を保存しました")


if __name__ == "__main__":
    main()
