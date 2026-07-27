import gzip, json, math
from datetime import time
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

# ============================================================
# 1. ページ・データ読込
# ============================================================
st.set_page_config(
    page_title="通勤時間と家賃で住む駅探し",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def load_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def merge_data(parts):
    # 通常データとJRデータを駅名単位で統合
    stations = {}
    timetables = {"weekday": [], "saturday": [], "sunday": []}
    sources = []

    for part in parts:
        if not part:
            continue

        sources.extend(part.get("sources", []))

        for station in part.get("stations", []):
            name = station["name"]
            current = stations.setdefault(
                name,
                {
                    "name": name,
                    "routes": [],
                    "operators": [],
                    "location": "所在地未登録",
                    "municipality_code": "",
                    "rent_per_sqm": None,
                    "rent_25sqm": None,
                    "lat": None,
                    "lon": None,
                    "_coord_count": 0,
                },
            )

            current["routes"] = sorted(
                set(current["routes"] + station.get("routes", []))
            )
            current["operators"] = sorted(
                set(current["operators"] + station.get("operators", []))
            )

            if station.get("location") not in ("", "所在地未登録"):
                current["location"] = station["location"]
                current["municipality_code"] = station.get(
                    "municipality_code", ""
                )

            for key in ("rent_per_sqm", "rent_25sqm"):
                if station.get(key) is not None:
                    current[key] = station[key]

            # 通常版とJR版の両方にある駅は代表座標を平均
            if station.get("lat") is not None and station.get("lon") is not None:
                count = current["_coord_count"]
                lat, lon = float(station["lat"]), float(station["lon"])
                current["lat"] = (
                    lat
                    if count == 0
                    else (current["lat"] * count + lat) / (count + 1)
                )
                current["lon"] = (
                    lon
                    if count == 0
                    else (current["lon"] * count + lon) / (count + 1)
                )
                current["_coord_count"] = count + 1

        for day_type in timetables:
            timetables[day_type].extend(
                part.get("timetables", {}).get(day_type, [])
            )

    for station in stations.values():
        station.pop("_coord_count", None)

    primary = next((part for part in parts if part), {})

    return {
        "service_date": primary.get("service_date", ""),
        "service_dates": primary.get("service_dates", {}),
        "generated_at": primary.get("generated_at", ""),
        "rent_source_year": primary.get("rent_source_year"),
        "rent_reference_area_sqm": primary.get("rent_reference_area_sqm"),
        "stations": sorted(stations.values(), key=lambda x: x["name"]),
        "timetables": timetables,
        "sources": sources,
    }


config = load_json("build_config.json")
basic = load_json("direct_timetable_basic.json.gz")
challenge = (
    load_json("direct_timetable_challenge.json.gz")
    if config.get("jr_enabled")
    else {}
)
data = merge_data([basic, challenge])

if not data.get("stations"):
    st.error("時刻表データがありません。GitHub Actionsを実行してください。")
    st.stop()

station_info = {
    station["name"]: {
        "routes": station.get("routes", []),
        "operators": station.get("operators", []),
        "location": station.get("location", "所在地未登録"),
        "rent": station.get("rent_25sqm"),
        "lat": station.get("lat"),
        "lon": station.get("lon"),
    }
    for station in data["stations"]
}

timetables = data["timetables"]
service_dates = data.get("service_dates", {})
st.session_state.setdefault("show_nearby", False)


# ============================================================
# 2. 路線カラー
# ============================================================
LINE_STYLES = {
    "浅草線": ("#e85298", "#fff2f7"),
    "三田線": ("#0079c2", "#edf8ff"),
    "新宿線": ("#6cbb5a", "#f1faef"),
    "大江戸線": ("#b6007a", "#fbf0f8"),
    "荒川線": ("#ee7b1a", "#fff8eb"),
    "日暮里・舎人": ("#9caeb7", "#f3f6f7"),
    "銀座線": ("#f39700", "#fff7e9"),
    "丸ノ内線": ("#e60012", "#fff1f2"),
    "日比谷線": ("#9caeb7", "#f4f6f7"),
    "東西線": ("#00a7db", "#edfaff"),
    "千代田線": ("#009944", "#edfaf2"),
    "有楽町線": ("#d7c447", "#fffced"),
    "半蔵門線": ("#9b7cb6", "#f8f3fb"),
    "南北線": ("#00ada9", "#effafa"),
    "副都心線": ("#bb641d", "#fff6ef"),
    "りんかい": ("#00a7e3", "#eefaff"),
    "つくばエクスプレス": ("#003894", "#eef4ff"),
    "多摩モノレール": ("#ff8a00", "#fff7ec"),
    "山手線": ("#9acd32", "#f5faec"),
    "京浜東北": ("#00b2e5", "#eefaff"),
    "根岸線": ("#00b2e5", "#eefaff"),
    "中央線快速": ("#f15a22", "#fff5ef"),
    "中央・総武": ("#ffd400", "#fffceb"),
    "総武線快速": ("#0067a5", "#eff7fc"),
    "横須賀線": ("#0067a5", "#eff7fc"),
    "埼京線": ("#00a65a", "#effaf4"),
    "川越線": ("#00a65a", "#effaf4"),
    "常磐線": ("#00a85a", "#effaf4"),
    "京葉線": ("#c9242f", "#fff1f2"),
    "武蔵野線": ("#f15a22", "#fff5ef"),
    "東海道線": ("#f68b1f", "#fff6ed"),
    "湘南新宿": ("#e87511", "#fff6ed"),
    "上野東京": ("#7a5c3e", "#f8f4ef"),
}

DEFAULT_STYLE = ("#667085", "#f8fafc")


# ============================================================
# 3. 計算
# ============================================================
def minute(text):
    hour, minute_value = map(int, text.split(":"))
    return hour * 60 + minute_value


def clock(value):
    return f"{value // 60 % 24:02d}:{value % 60:02d}"


def distance_m(lat1, lon1, lat2, lon2):
    # 緯度経度から2駅間の直線距離を計算
    radius = 6_371_000
    lat1, lat2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlat = lat2 - lat1
    dlon = math.radians(float(lon2) - float(lon1))
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(value))


def estimated_walk_minutes(distance):
    # 直線距離を1.25倍し、歩行速度75m/分で概算
    return max(1, math.ceil(float(distance) * 1.25 / 75))


def nearby_stations(destination, radius):
    # 目的駅から指定半径内にある別名駅を抽出
    base = station_info[destination]

    if base["lat"] is None or base["lon"] is None:
        return []

    result = []

    for name, info in station_info.items():
        if (
            name == destination
            or info["lat"] is None
            or info["lon"] is None
        ):
            continue

        distance = round(
            distance_m(
                base["lat"],
                base["lon"],
                info["lat"],
                info["lon"],
            )
        )

        if distance <= radius:
            result.append(
                {
                    "name": name,
                    "distance": distance,
                    "walk": estimated_walk_minutes(distance),
                }
            )

    return sorted(result, key=lambda x: (x["distance"], x["name"]))


def time_band(value):
    return next(
        (
            f"{limit}分以内"
            for limit in (15, 30, 45, 60)
            if value <= limit
        ),
        "60分超",
    )


def rent_man(value):
    return f"{float(value) / 10000:.1f}万円" if pd.notna(value) else ""


def relative_rent(rent, base):
    if pd.isna(rent) or pd.isna(base) or not base:
        return None
    return round(float(rent) / float(base) * 100)


def rent_level(ratio):
    if pd.isna(ratio):
        return "不明"
    if ratio < 90:
        return "安い"
    if ratio <= 110:
        return "同程度"
    return "高い"


def compact_html(text):
    return " ".join(line.strip() for line in text.splitlines())


def line_style(route):
    return next(
        (
            style
            for name, style in LINE_STYLES.items()
            if name in str(route)
        ),
        DEFAULT_STYLE,
    )


def station_label(name):
    routes = "・".join(station_info[name]["routes"])
    return f"{routes}｜{name}" if routes else name


def toggle_nearby():
    st.session_state.show_nearby = not st.session_state.show_nearby


def clock_html(text):
    hour, minutes = map(int, text.split(":"))
    numbers = ""

    for number in range(1, 13):
        angle = math.radians(number * 30 - 90)
        x = 26 + 20 * math.cos(angle)
        y = 26 + 20 * math.sin(angle)
        numbers += (
            f'<span class="clock-number" '
            f'style="left:{x}px;top:{y}px">{number}</span>'
        )

    return f"""
    <div class="clock">
        {numbers}
        <div class="hand hour-hand"
             style="transform:rotate(
             {(hour % 12) * 30 + minutes * .5}deg)"></div>
        <div class="hand minute-hand"
             style="transform:rotate({minutes * 6}deg)"></div>
        <div class="clock-center"></div>
    </div>
    """


def search_routes(trips, destinations, target_minute):
    # 目的駅と選択した近隣駅を検索し、各出発駅の最遅便を選ぶ
    latest = {}

    for trip in trips:
        stops = trip.get("stops", [])

        for destination_index, destination_stop in enumerate(stops):
            destination = destination_stop[0]

            if destination not in destinations:
                continue

            walk = destinations[destination]
            arrival = minute(destination_stop[1])

            if arrival + walk > target_minute:
                continue

            for origin in stops[:destination_index]:
                station = origin[0]
                departure = minute(origin[2])

                if station in destinations or departure >= arrival:
                    continue

                info = station_info.get(station, {})
                candidate = {
                    "駅名": station,
                    "所在地": info.get("location", "所在地未登録"),
                    "家賃": info.get("rent"),
                    "出発": clock(departure),
                    "到着": clock(arrival),
                    "到着駅": destination,
                    "徒歩時間": walk,
                    "目的地到着": clock(arrival + walk),
                    "乗車時間": arrival - departure,
                    "所要時間": arrival + walk - departure,
                    "経路": trip.get("route", "路線情報なし"),
                    "事業者": trip.get("operator", ""),
                    "行先": trip.get("destination", "行先情報なし"),
                    "路線一覧": info.get("routes", []),
                    "出発分": departure,
                }

                current = latest.get(station)

                if (
                    current is None
                    or departure > current["出発分"]
                    or (
                        departure == current["出発分"]
                        and candidate["所要時間"] < current["所要時間"]
                    )
                ):
                    latest[station] = candidate

    return sorted(
        latest.values(),
        key=lambda row: row["出発分"],
        reverse=True,
    )


def day_text(result):
    if not result:
        return "該当する直通列車なし"

    walk = (
        f'＋徒歩{result["徒歩時間"]}分'
        if result["徒歩時間"]
        else ""
    )

    return (
        f'{result["出発"]}発'
        f'（{result["到着駅"]} {result["到着"]}着{walk}）'
    )


# ============================================================
# 4. CSS
# ============================================================
st.markdown(
    """
<style>
.block-container{max-width:1240px;padding:3.25rem 1rem 3rem!important}
.selector-label{opacity:.68;font-size:.72rem;font-weight:750;margin-bottom:.16rem}
.heading-row{display:flex;align-items:baseline;justify-content:space-between;
gap:1rem;margin:.5rem 0}
.page-title{font-size:clamp(1.25rem,2.3vw,1.85rem);font-weight:900;
line-height:1.2;letter-spacing:-.04em}
.page-note{opacity:.58;font-size:.68rem;text-align:right;white-space:nowrap}
.challenge-notice{padding:.42rem .65rem;margin:.2rem 0 .55rem;
border:1px solid #e5a00080;border-radius:9px;background:#fff8df;
color:#694c00;font-size:.68rem}

.near-destination{padding:.6rem .72rem;margin:.35rem 0 .6rem;
border:1px solid #98a2b360;border-radius:10px;background:rgba(128,128,128,.05)}
.near-destination-title{font-size:.76rem;font-weight:850;margin-bottom:.1rem}
.near-destination-note{font-size:.64rem;opacity:.65;margin-bottom:.35rem}

.st-key-nearby_toggle [data-testid="stHorizontalBlock"]{align-items:center!important}
.st-key-nearby_toggle [data-testid="stMarkdownContainer"],
.st-key-nearby_toggle [data-testid="stMarkdownContainer"] p{margin:0!important}
.nearby-row{display:flex;align-items:center;justify-content:space-between;
height:34px;padding:0 .65rem;background:rgba(128,128,128,.08);
border:1px solid rgba(128,128,128,.35);border-radius:9px;font-size:.7rem}
.st-key-nearby_toggle div[data-testid="stButton"] button{
height:34px!important;min-height:34px!important;padding:0 .6rem!important;
font-size:.68rem!important;white-space:nowrap;border-radius:9px!important}

.station-card{position:relative;display:grid;
grid-template-columns:minmax(145px,1fr) minmax(190px,1.1fr)
minmax(180px,1fr) 42px;
grid-template-areas:"station departure route info"
"location arrival rent info";
align-items:center;gap:.08rem clamp(.7rem,1.8vw,1.4rem);
color:#283141!important;background:var(--card-bg)!important;
border:1px solid #98a2b380;border-left:6px solid var(--line-color)!important;
border-radius:12px;padding:.62rem .85rem;margin-bottom:.42rem;
box-shadow:0 1px 3px #0000000b}
.station-card div,.station-card span,.station-card summary{color:#283141!important}
.station-name{grid-area:station;font-size:clamp(1.25rem,2.2vw,1.7rem);
font-weight:900;line-height:1.05;letter-spacing:-.04em;overflow-wrap:anywhere}
.location{grid-area:location;color:#667085!important;font-size:.68rem}
.departure-wrap{grid-area:departure;display:flex;align-items:center;gap:.55rem}
.departure{font-size:clamp(1.45rem,2.6vw,1.95rem);font-weight:950;
letter-spacing:-.05em;white-space:nowrap}
.arrival{grid-area:arrival;color:#667085!important;font-size:.68rem;
padding-left:58px;white-space:nowrap}
.route{grid-area:route;font-size:.81rem;font-weight:850;line-height:1.25}
.rent{grid-area:rent;color:#475467!important;font-size:.72rem;
font-weight:800;white-space:nowrap}

.clock{position:relative;width:52px;height:52px;flex:0 0 52px;
border:2px solid #344054;border-radius:50%;background:#fff}
.clock-number{position:absolute;width:10px;height:10px;margin:-5px;
text-align:center;line-height:10px;font-size:6px;font-weight:750}
.hand{position:absolute;left:24px;bottom:25px;transform-origin:bottom center;
background:#344054;border-radius:4px}
.hour-hand{width:4px;height:12px}.minute-hand{width:2px;height:18px}
.clock-center{position:absolute;left:21px;top:21px;width:6px;height:6px;
border-radius:50%;background:#344054}

.details-area{grid-area:info;text-align:center}
details{font-size:.68rem}
summary{display:inline-flex;align-items:center;justify-content:center;
width:28px;height:28px;border:1px solid #98a2b3;border-radius:50%;
background:#ffffffb8;cursor:pointer;list-style:none;font-family:serif;
font-size:.8rem;font-weight:900}
summary::-webkit-details-marker{display:none}
.details-body{position:absolute;z-index:20;right:.8rem;top:3.2rem;
width:min(390px,calc(100vw - 3rem));padding:.65rem .75rem;
border:1px solid #d0d5dd;border-radius:9px;background:#fff;text-align:left;
line-height:1.65;box-shadow:0 7px 20px #0002}
.detail-label{font-weight:850}
.detail-divider{height:1px;background:#e4e7ec;margin:.35rem 0}
.empty{padding:2rem;text-align:center;border:1px dashed rgba(128,128,128,.6);
border-radius:12px}

@media(max-width:620px){
.block-container{padding:2.9rem .55rem 2.5rem!important}
div[data-testid="stHorizontalBlock"]{display:flex!important;
flex-direction:row!important;flex-wrap:nowrap!important;gap:.3rem!important}
div[data-testid="stHorizontalBlock"]>div{min-width:0!important}
.selector-label{font-size:.59rem;margin-bottom:.08rem}
.heading-row{display:block;margin:.4rem 0 .42rem}
.page-title{font-size:1rem}
.page-note{margin-top:.12rem;font-size:.56rem;text-align:left;white-space:normal}
.challenge-notice{font-size:.57rem;padding:.35rem .45rem}
.near-destination{padding:.45rem .5rem}
.nearby-row{height:31px;padding:0 .42rem;font-size:.58rem}
.st-key-nearby_toggle div[data-testid="stButton"] button{
height:31px!important;min-height:31px!important;padding:0 .35rem!important;
font-size:.58rem!important}
.station-card{grid-template-columns:minmax(0,1.2fr) minmax(100px,.88fr)
minmax(112px,.9fr);grid-template-areas:"station departure rent"
"location arrival route";gap:.1rem .32rem;border-left-width:5px!important;
border-radius:10px;padding:.48rem .5rem;margin-bottom:.34rem}
.station-name{font-size:1.2rem;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}
.location{font-size:.57rem;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}
.departure-wrap{display:block}.clock{display:none}
.departure{font-size:1.25rem;line-height:1}
.arrival{padding:0;font-size:.54rem}
.rent{position:relative;padding-right:22px;font-size:.58rem}
.route{font-size:.57rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.details-area{position:absolute;top:.31rem;right:.3rem}
summary{width:20px;height:20px;font-size:.6rem}
.details-body{position:relative;right:auto;top:auto;width:auto;
margin-top:.35rem;box-shadow:none}
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# 5. 検索条件
# ============================================================
stations = sorted(
    station_info,
    key=lambda name: (
        "・".join(station_info[name]["routes"]),
        name,
    ),
)

destination_col, time_col, filter_col = st.columns(
    [2.5, 1.05, 0.38]
)

with destination_col:
    st.markdown(
        '<div class="selector-label">勤務先・目的駅</div>',
        unsafe_allow_html=True,
    )
    selected_destination = st.selectbox(
        "勤務先・目的駅",
        stations,
        index=None,
        placeholder="神保町（駅名・路線で検索）",
        format_func=station_label,
        label_visibility="collapsed",
    )

destination = selected_destination or (
    "神保町" if "神保町" in station_info else stations[0]
)

with time_col:
    st.markdown(
        '<div class="selector-label">到着</div>',
        unsafe_allow_html=True,
    )
    arrival_time = st.time_input(
        "到着時刻",
        value=time(8),
        step=60,
        label_visibility="collapsed",
    )

target = arrival_time.strftime("%H:%M")
target_minute = minute(target)
destination_rent = station_info[destination]["rent"]

# 目的駅の近隣駅も到着候補に含める
destination_options = {destination: 0}
nearby_mode = st.toggle(
    "近隣駅も到着候補に含める",
    value=False,
)

if nearby_mode:
    st.markdown(
        '<div class="near-destination">',
        unsafe_allow_html=True,
    )

    radius = st.select_slider(
        "近隣駅として探す範囲",
        options=[300, 400, 500, 600, 800, 1000],
        value=500,
        format_func=lambda value: f"{value}m",
    )

    candidates = nearby_stations(destination, radius)

    if not candidates:
        st.info(
            "指定範囲内に、座標を確認できる別の駅はありません。"
        )
    else:
        st.markdown(
            (
                f'<div class="near-destination-title">'
                f"近くの駅を{len(candidates)}駅見つけました"
                f"</div>"
                f'<div class="near-destination-note">'
                f"使用する駅と、そこから目的地までの徒歩時間を"
                f"調整できます。"
                f"</div>"
            ),
            unsafe_allow_html=True,
        )

        for candidate in candidates:
            name = candidate["name"]
            distance = candidate["distance"]
            estimated = candidate["walk"]
            key_base = f"{destination}_{radius}_{name}"

            use_col, walk_col = st.columns(
                [3.2, 1.2],
                vertical_alignment="center",
            )

            with use_col:
                use_station = st.checkbox(
                    f"{name}（直線約{distance}m）",
                    value=True,
                    key=f"use_{key_base}",
                )

            with walk_col:
                walk = st.number_input(
                    f"{name}から目的地まで",
                    min_value=1,
                    max_value=30,
                    value=estimated,
                    step=1,
                    key=f"walk_{key_base}",
                    label_visibility="collapsed",
                )

            if use_station:
                destination_options[name] = int(walk)

    st.markdown("</div>", unsafe_allow_html=True)

weekday_df = pd.DataFrame(
    search_routes(
        timetables.get("weekday", []),
        destination_options,
        target_minute,
    )
)

saturday = {
    row["駅名"]: row
    for row in search_routes(
        timetables.get("saturday", []),
        destination_options,
        target_minute,
    )
}

sunday = {
    row["駅名"]: row
    for row in search_routes(
        timetables.get("sunday", []),
        destination_options,
        target_minute,
    )
}

bands = [
    "15分以内",
    "30分以内",
    "45分以内",
    "60分以内",
    "60分超",
]

if not weekday_df.empty:
    weekday_df["時間圏"] = weekday_df["所要時間"].apply(
        time_band
    )
    weekday_df["相対家賃"] = weekday_df["家賃"].apply(
        lambda value: relative_rent(
            value,
            destination_rent,
        )
    )
    weekday_df["家賃区分"] = weekday_df["相対家賃"].apply(
        rent_level
    )

with filter_col:
    st.markdown(
        '<div class="selector-label">条件</div>',
        unsafe_allow_html=True,
    )

    with st.popover("⚙"):
        st.checkbox(
            "10分未満の出発駅も表示",
            key="show_nearby",
        )

        rent_filter = st.radio(
            "家賃",
            ["すべて", "安い", "同程度", "高い"],
            horizontal=True,
        )

        route_options = (
            sorted(weekday_df["経路"].dropna().unique())
            if not weekday_df.empty
            else []
        )

        selected_routes = st.multiselect(
            "利用路線",
            route_options,
            default=route_options,
        )

        selected_bands = st.multiselect(
            f"{destination}までの所要時間",
            bands,
            default=bands,
        )

        keyword = st.text_input(
            "駅名検索",
            placeholder="例：浅草、新宿",
        )


# ============================================================
# 6. タイトル・JR表示
# ============================================================
st.markdown(
    compact_html(
        f"""
        <div class="heading-row">
            <div class="page-title">
                {escape(destination)}に{target}までに着くには？
            </div>
            <div class="page-note">
                平日・直通のみ｜
                対象 {escape(service_dates.get("weekday", ""))}
            </div>
        </div>
        """
    ),
    unsafe_allow_html=True,
)

if len(destination_options) > 1:
    st.caption(
        "到着候補："
        + "、".join(destination_options)
        + "。近隣駅は設定した徒歩時間を差し引いて検索しています。"
    )

if config.get("jr_enabled"):
    st.markdown(
        """
        <div class="challenge-notice">
        JR東日本の公共交通オープンデータチャレンジ2026限定データを
        利用しています。
        </div>
        """,
        unsafe_allow_html=True,
    )

df = weekday_df.copy()

if not df.empty:
    df = df[
        df["時間圏"].isin(selected_bands)
        & df["経路"].isin(selected_routes)
    ]

    if rent_filter != "すべて":
        df = df[df["家賃区分"] == rent_filter]

    if keyword.strip():
        df = df[
            df["駅名"].str.contains(
                keyword.strip(),
                na=False,
                regex=False,
            )
        ]

nearby_count = (
    len(df[df["所要時間"] < 10])
    if not df.empty
    else 0
)

if not st.session_state.show_nearby and not df.empty:
    df = df[df["所要時間"] >= 10].copy()


# ============================================================
# 7. 近距離の出発駅切替
# ============================================================
if nearby_count or st.session_state.show_nearby:
    with st.container(key="nearby_toggle"):
        notice_col, button_col = st.columns(
            [5.4, 1],
            vertical_alignment="center",
        )

        with notice_col:
            message = (
                f"<strong>近距離の出発駅も表示中</strong>"
                f"<span>10分未満の{nearby_count}駅を含む</span>"
                if st.session_state.show_nearby
                else
                f"<strong>少し離れた候補を優先して表示中</strong>"
                f"<span>10分未満の{nearby_count}駅を省略</span>"
            )

            st.markdown(
                compact_html(
                    f'<div class="nearby-row">{message}</div>'
                ),
                unsafe_allow_html=True,
            )

        with button_col:
            st.button(
                (
                    "隠す"
                    if st.session_state.show_nearby
                    else "表示"
                ),
                key="toggle_nearby_button",
                use_container_width=True,
                on_click=toggle_nearby,
            )


# ============================================================
# 8. 結果カード
# ============================================================
if df.empty:
    st.markdown(
        '<div class="empty">条件に一致する直通列車がありません。</div>',
        unsafe_allow_html=True,
    )

else:
    for _, row in df.iterrows():
        raw_station = str(row["駅名"])
        station = escape(raw_station)
        location = escape(str(row["所在地"]))
        route = escape(str(row["経路"]))
        operator = escape(str(row["事業者"]))
        train_destination = escape(str(row["行先"]))
        routes = escape(" ／ ".join(row["路線一覧"]))
        arrival_station = escape(str(row["到着駅"]))
        walk = int(row["徒歩時間"])

        accent, background = line_style(row["経路"])
        rent = row["家賃"]
        ratio = row["相対家賃"]
        sat = saturday.get(raw_station)
        sun = sunday.get(raw_station)

        ratio_text = (
            f"{int(ratio)}%"
            if pd.notna(ratio)
            else "算出不可"
        )
        candidate_rent = (
            f"25㎡換算 約{rent_man(rent)}"
            if pd.notna(rent)
            else "情報なし"
        )
        destination_rent_text = (
            f"25㎡換算 約{rent_man(destination_rent)}"
            if pd.notna(destination_rent)
            else "情報なし"
        )
        arrival_text = (
            f'{arrival_station} {row["到着"]}着'
            f' → 徒歩{walk}分'
            f' → {escape(destination)} {row["目的地到着"]}'
            if walk
            else f'{escape(destination)} {row["到着"]}着'
        )

        card = f"""
        <div class="station-card"
             style="--line-color:{accent};--card-bg:{background}">
            <div class="station-name">{station}</div>
            <div class="location">{location}</div>

            <div class="departure-wrap">
                {clock_html(str(row["出発"]))}
                <div class="departure">{row["出発"]}発</div>
            </div>

            <div class="arrival">{arrival_text}</div>

            <div class="rent">家賃：{row["家賃区分"]}</div>
            <div class="route">{route}・直通</div>

            <div class="details-area">
                <details>
                    <summary>i</summary>
                    <div class="details-body">
                        <div>
                            <span class="detail-label">所在地：</span>
                            {location}
                        </div>
                        <div>
                            <span class="detail-label">乗り入れ路線：</span>
                            {routes}
                        </div>
                        <div>
                            <span class="detail-label">運行事業者：</span>
                            {operator or "情報なし"}
                        </div>

                        <div class="detail-divider"></div>

                        <div>
                            <span class="detail-label">家賃評価：</span>
                            {row["家賃区分"]}
                        </div>
                        <div>
                            <span class="detail-label">相対家賃：</span>
                            {ratio_text}
                        </div>
                        <div>
                            <span class="detail-label">{station}：</span>
                            {candidate_rent}
                        </div>
                        <div>
                            <span class="detail-label">
                                {escape(destination)}：
                            </span>
                            {destination_rent_text}
                        </div>

                        <div class="detail-divider"></div>

                        <div>
                            <span class="detail-label">平日：</span>
                            {row["出発"]}発
                            （{arrival_text}・{route}）
                        </div>
                        <div>
                            <span class="detail-label">土曜：</span>
                            {escape(day_text(sat))}
                        </div>
                        <div>
                            <span class="detail-label">日曜：</span>
                            {escape(day_text(sun))}
                        </div>
                        <div>
                            <span class="detail-label">乗車時間：</span>
                            {row["乗車時間"]}分
                        </div>
                        <div>
                            <span class="detail-label">
                                徒歩を含む所要時間：
                            </span>
                            {row["所要時間"]}分
                        </div>
                        <div>
                            <span class="detail-label">列車の行先：</span>
                            {train_destination}
                        </div>
                    </div>
                </details>
            </div>
        </div>
        """

        st.markdown(
            compact_html(card),
            unsafe_allow_html=True,
        )


# ============================================================
# 9. 表・CSV・出典
# ============================================================
with st.expander("検索結果を表で確認する"):
    if df.empty:
        st.info("表示できる検索結果がありません。")

    else:
        output = df[
            [
                "駅名",
                "所在地",
                "家賃区分",
                "相対家賃",
                "家賃",
                "出発",
                "到着駅",
                "到着",
                "徒歩時間",
                "目的地到着",
                "乗車時間",
                "所要時間",
                "経路",
                "事業者",
                "行先",
            ]
        ].copy()

        output["相対家賃"] = output["相対家賃"].apply(
            lambda value: (
                f"{int(value)}%"
                if pd.notna(value)
                else ""
            )
        )
        output["家賃"] = output["家賃"].apply(
            lambda value: (
                rent_man(value)
                if pd.notna(value)
                else ""
            )
        )

        st.dataframe(
            output,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "CSVで保存",
            output.to_csv(index=False).encode("utf-8-sig"),
            f"{destination}_{target.replace(':', '')}_direct.csv",
            "text/csv",
        )

basic_sources = [
    source["name"]
    for source in basic.get("sources", [])
    if source.get("name")
]
challenge_sources = [
    source["name"]
    for source in challenge.get("sources", [])
    if source.get("name")
]

st.caption(
    "家賃は、目的駅比90%未満を「安い」、90〜110%を"
    "「同程度」、110%超を「高い」と表示しています。"
)
st.caption(
    "家賃目安は住宅・土地統計調査の市区町村別1㎡当たり家賃を"
    "25㎡に換算した参考値です。"
)
st.caption(
    f'通常データ提供元：{"、".join(basic_sources)}。'
    "各提供データを加工して利用しています。"
)

if challenge_sources:
    st.caption(
        f'チャレンジ限定データ提供元：'
        f'{"、".join(challenge_sources)}。'
    )

st.caption(
    "所在地と近隣駅の距離はGTFS座標と国土地理院の情報を基に"
    "算出しています。徒歩時間は直線距離からの概算で、"
    "実際の経路や駅構内移動は含みません。"
)
