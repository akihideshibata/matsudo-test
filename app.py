from datetime import datetime, time
from html import escape
from pathlib import Path
import json, math

import pandas as pd
import streamlit as st


# ============================================================
# 1. ページ設定・データ読込
# ============================================================
st.set_page_config(
    page_title="逆算通勤｜直通版",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

data = json.loads(Path("direct_timetable.json").read_text(encoding="utf-8"))
station_info = {x["name"]: x["routes"] for x in data["stations"]}


# ============================================================
# 2. 表示用関数
# ============================================================
LINE_COLORS = {
    "浅草線": "#fbf1f2", "三田線": "#edf8fc", "新宿線": "#eff8f5",
    "大江戸線": "#f8f0fa", "荒川線": "#fff8e9",
    "日暮里・舎人ライナー": "#f5f7fa",
}
DEFAULT_COLOR = "#f8fafc"


def minute(text):
    # HH:MMを比較用の分へ変換
    h, m = map(int, text.split(":"))
    return h * 60 + m


def clock(minutes):
    # 分をHH:MMへ変換
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def time_band(minutes):
    return next(
        (f"{x}分以内" for x in (15, 30, 45, 60) if minutes <= x),
        "60分超",
    )


def compact_html(text):
    return " ".join(x.strip() for x in text.splitlines())


def line_color(route):
    return next(
        (color for name, color in LINE_COLORS.items() if name in route),
        DEFAULT_COLOR,
    )


def station_font(count):
    return min(33, 24 + count * .8)


def clock_html(text):
    # 出発時刻をアナログ時計で表示
    hour, minutes = map(int, text.split(":"))
    hour_angle, minute_angle = (hour % 12) * 30 + minutes * .5, minutes * 6
    numbers = ""

    for number in range(1, 13):
        angle = math.radians(number * 30 - 90)
        x, y = 31 + 24 * math.cos(angle), 31 + 24 * math.sin(angle)
        numbers += (
            f'<span class="clock-number" style="left:{x}px;top:{y}px">'
            f"{number}</span>"
        )

    return f"""
    <div class="clock">
        {numbers}
        <div class="hand hour-hand" style="transform:rotate({hour_angle}deg)"></div>
        <div class="hand minute-hand" style="transform:rotate({minute_angle}deg)"></div>
        <div class="clock-center"></div>
    </div>
    """


def search_routes(destination, target):
    # 保存済み全列車から、指定時刻までに着く最新列車を駅ごとに選ぶ
    target_min, latest = minute(target), {}

    for trip in data["trips"]:
        stops = trip["stops"]

        for destination_index, stop in enumerate(stops):
            if stop[0] != destination or minute(stop[1]) > target_min:
                continue

            arrival = minute(stop[1])

            for origin in stops[:destination_index]:
                departure = minute(origin[2])
                station = origin[0]

                if station == destination or departure >= arrival:
                    continue

                candidate = {
                    "駅名": station,
                    "出発": clock(departure),
                    "到着": clock(arrival),
                    "所要時間": arrival - departure,
                    "経路": trip["route"],
                    "行先": trip["destination"],
                    "路線一覧": station_info.get(station, [trip["route"]]),
                    "出発分": departure,
                }

                if station not in latest or departure > latest[station]["出発分"]:
                    latest[station] = candidate

    return sorted(latest.values(), key=lambda x: x["出発分"], reverse=True)


# ============================================================
# 3. CSS
# ============================================================
st.markdown(
    """
    <style>
    .block-container{max-width:1180px;padding:4.8rem 1.2rem 4rem!important}
    .page-title{font-size:clamp(1.8rem,4vw,2.5rem);font-weight:900;
        line-height:1.2;letter-spacing:-.05em}
    .subtitle{color:#667085;margin:.4rem 0 1rem}
    .notice{padding:.65rem .85rem;border:1px solid #98a2b3;border-radius:10px;
        background:#f8fafc;margin:.7rem 0 1rem;font-size:.84rem}
    .band-title{font-size:1.3rem;font-weight:850;margin:1.5rem 0 .55rem;
        border-bottom:1px solid #d0d5dd;padding-bottom:.3rem}
    .band-count{color:#667085;font-size:.78rem;font-weight:500}

    .station-card{display:grid;
        grid-template-columns:minmax(145px,.9fr) minmax(260px,1.35fr)
        minmax(230px,1.2fr);align-items:center;gap:clamp(.7rem,1.5vw,1.2rem);
        border:1px solid #98a2b380;border-radius:14px;padding:.9rem 1rem;
        margin-bottom:.65rem;min-width:0;overflow:hidden;
        box-shadow:0 1px 3px #0000000b}
    .station-area,.departure-area,.summary-area{min-width:0}
    .station-name{font-weight:900;line-height:1.05;letter-spacing:-.04em;
        overflow-wrap:anywhere}
    .station-suffix{font-size:13px;margin-left:2px}
    .location{color:#667085;font-size:.78rem;margin-top:.3rem}

    .departure-area{display:flex;align-items:center;gap:.75rem}
    .departure-message{font-size:clamp(1rem,1.7vw,1.25rem);
        font-weight:850;line-height:1.25}
    .departure-time{font-size:clamp(1.65rem,3vw,2.15rem);
        font-weight:950;letter-spacing:-.05em}
    .departure-suffix{font-size:.95rem;font-weight:800;margin-left:.2rem}
    .arrival{color:#667085;font-size:.74rem;margin-top:.25rem}

    .clock{position:relative;width:62px;height:62px;border:2px solid #344054;
        border-radius:50%;background:#ffffffcf;flex:0 0 62px}
    .clock-number{position:absolute;width:12px;height:12px;margin:-6px;
        text-align:center;line-height:12px;font-size:7px;font-weight:750;color:#475467}
    .hand{position:absolute;left:29px;bottom:30px;transform-origin:bottom center;
        background:#344054;border-radius:4px}
    .hour-hand{width:4px;height:15px}.minute-hand{width:2px;height:21px}
    .clock-center{position:absolute;left:27px;top:27px;width:6px;height:6px;
        border-radius:50%;background:#344054}

    .route-main{font-size:.9rem;font-weight:800;line-height:1.4;
        overflow-wrap:anywhere}
    .meta-row{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.45rem}
    .chip{padding:.22rem .43rem;border-radius:7px;background:#ffffffb0;
        border:1px solid #d0d5ddbb;font-size:.69rem;font-weight:700}

    details{margin-top:.5rem;font-size:.72rem;color:#475467}
    summary{cursor:pointer;font-weight:750;color:#344054;list-style:none}
    summary::-webkit-details-marker{display:none}
    summary:after{content:" ＋";color:#667085}
    details[open] summary:after{content:" −"}
    .details-body{margin-top:.45rem;padding:.55rem .65rem;border-radius:8px;
        background:#ffffff9c;line-height:1.65}
    .detail-label{font-weight:800;color:#344054}
    .empty{padding:2rem;text-align:center;border:1px dashed #98a2b3;
        border-radius:14px;color:#667085}

    @media(max-width:900px){
        .station-card{grid-template-columns:minmax(140px,.75fr) minmax(240px,1.25fr)}
        .summary-area{grid-column:1/-1;border-top:1px solid #98a2b34d;padding-top:.55rem}
    }
    @media(max-width:620px){
        .block-container{padding-top:4.3rem!important}
        .station-card{display:block}
        .departure-area,.summary-area{margin-top:.75rem}
        .clock{width:56px;height:56px;flex-basis:56px}
        .clock-number{display:none}.hand{left:26px;bottom:27px}
        .hour-hand{height:14px}.minute-hand{height:19px}
        .clock-center{left:24px;top:24px}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. 検索条件
# ============================================================
stations = sorted(station_info)
default_station = stations.index("新橋") if "新橋" in stations else 0

destination = st.selectbox(
    "目的駅",
    stations,
    index=default_station,
)

arrival_time = st.time_input(
    "到着時刻",
    value=time(8, 0),
    step=300,
)
target = arrival_time.strftime("%H:%M")

st.markdown(
    compact_html(
        f"""
        <div class="page-title">{escape(destination)}駅に{target}までに着くには？</div>
        <div class="subtitle">どの駅で、何時発の電車に乗れば間に合うか</div>
        """
    ),
    unsafe_allow_html=True,
)

rows = search_routes(destination, target)
df = pd.DataFrame(rows)

bands = ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"]

if not df.empty:
    df["時間圏"] = df["所要時間"].apply(time_band)

with st.popover("⚙️ 絞り込み条件"):
    selected_bands = st.multiselect(
        f"{destination}までの所要時間",
        bands,
        default=bands,
    )
    keyword = st.text_input("駅名検索", placeholder="例：浅草、新宿")
    selected_routes = st.multiselect(
        "利用路線",
        sorted(df["経路"].unique()) if not df.empty else [],
        default=sorted(df["経路"].unique()) if not df.empty else [],
    )

st.markdown(
    f"""
    <div class="notice">
        <strong>乗換なしの直通列車のみ表示しています。</strong>
        対象ダイヤ：{data["service_date"]}｜
        GTFS取得：{data["gtfs_fetched_at"] or "取得日時不明"}
    </div>
    """,
    unsafe_allow_html=True,
)

if not df.empty:
    df = df[
        df["時間圏"].isin(selected_bands)
        & df["経路"].isin(selected_routes)
    ]
    if keyword.strip():
        df = df[df["駅名"].str.contains(keyword.strip(), na=False)]


# ============================================================
# 5. カード表示
# ============================================================
if df.empty:
    st.markdown(
        '<div class="empty">条件に一致する直通列車がありません。</div>',
        unsafe_allow_html=True,
    )
else:
    for band in bands:
        band_df = df[df["時間圏"] == band]
        if band_df.empty:
            continue

        st.markdown(
            f'<div class="band-title">{band} '
            f'<span class="band-count">{len(band_df)}駅</span></div>',
            unsafe_allow_html=True,
        )
