from datetime import time
from html import escape
from pathlib import Path
import json
import math

import pandas as pd
import streamlit as st


# ============================================================
# 1. ページ設定・データ読み込み
# ============================================================
st.set_page_config(
    page_title="逆算通勤｜直通版",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

data = json.loads(
    Path("direct_timetable.json").read_text(encoding="utf-8")
)

# 駅名ごとの乗り入れ路線
station_info = {
    x["name"]: x["routes"]
    for x in data["stations"]
}


# ============================================================
# 2. 表示・計算用関数
# ============================================================
LINE_COLORS = {
    "浅草線": "#fbf1f2",
    "三田線": "#edf8fc",
    "新宿線": "#eff8f5",
    "大江戸線": "#f8f0fa",
    "荒川線": "#fff8e9",
    "日暮里・舎人ライナー": "#f5f7fa",
}
DEFAULT_COLOR = "#f8fafc"


def minute(text):
    """HH:MMを比較用の分数へ変換する。"""
    hour, minutes = map(int, text.split(":"))
    return hour * 60 + minutes


def clock(value):
    """分数をHH:MMへ戻す。"""
    return f"{value // 60 % 24:02d}:{value % 60:02d}"


def time_band(minutes):
    """所要時間を分類する。"""
    return next(
        (
            f"{limit}分以内"
            for limit in (15, 30, 45, 60)
            if minutes <= limit
        ),
        "60分超",
    )


def compact_html(text):
    """HTMLを1行化して表示崩れを防ぐ。"""
    return " ".join(
        line.strip()
        for line in text.splitlines()
    )


def line_color(route):
    """路線ごとの淡い背景色を返す。"""
    return next(
        (
            color
            for name, color in LINE_COLORS.items()
            if name in route
        ),
        DEFAULT_COLOR,
    )


def station_font(line_count):
    """乗り入れ路線数に応じて駅名を少し大きくする。"""
    return min(33, 24 + line_count * 0.8)


def clock_html(text):
    """出発時刻のアナログ時計を作る。"""
    hour, minutes = map(int, text.split(":"))
    hour_angle = (hour % 12) * 30 + minutes * 0.5
    minute_angle = minutes * 6
    numbers = ""

    for number in range(1, 13):
        angle = math.radians(number * 30 - 90)
        x = 31 + 24 * math.cos(angle)
        y = 31 + 24 * math.sin(angle)
        numbers += (
            f'<span class="clock-number" '
            f'style="left:{x}px;top:{y}px">{number}</span>'
        )

    return f"""
    <div class="clock">
        {numbers}
        <div class="hand hour-hand"
             style="transform:rotate({hour_angle}deg)"></div>
        <div class="hand minute-hand"
             style="transform:rotate({minute_angle}deg)"></div>
        <div class="clock-center"></div>
    </div>
    """


def search_routes(destination, target):
    """指定時刻までに直通で着く最新列車を駅ごとに選ぶ。"""
    target_min = minute(target)
    latest = {}

    for trip in data["trips"]:
        stops = trip["stops"]

        for destination_index, destination_stop in enumerate(stops):
            if destination_stop[0] != destination:
                continue

            arrival = minute(destination_stop[1])

            if arrival > target_min:
                continue

            for origin_stop in stops[:destination_index]:
                station = origin_stop[0]
                departure = minute(origin_stop[2])

                if station == destination or departure >= arrival:
                    continue

                candidate = {
                    "駅名": station,
                    "出発": clock(departure),
                    "到着": clock(arrival),
                    "所要時間": arrival - departure,
                    "経路": trip["route"],
                    "行先": trip["destination"],
                    "路線一覧": station_info.get(
                        station,
                        [trip["route"]],
                    ),
                    "出発分": departure,
                }

                if (
                    station not in latest
                    or departure > latest[station]["出発分"]
                ):
                    latest[station] = candidate

    return sorted(
        latest.values(),
        key=lambda x: x["出発分"],
        reverse=True,
    )


# ============================================================
# 3. デザイン
# ============================================================
st.markdown(
    """
    <style>
    .block-container{
        max-width:1180px;
        padding:4.3rem 1.2rem 4rem!important
    }

    .selector-label{
        color:#667085;
        font-size:.8rem;
        font-weight:750;
        margin-bottom:.25rem
    }

    .page-title{
        font-size:clamp(1.8rem,4vw,2.6rem);
        font-weight:900;
        line-height:1.2;
        letter-spacing:-.05em;
        margin-top:.65rem
    }

    .subtitle{
        color:#667085;
        margin:.4rem 0 1rem
    }

    .notice{
        padding:.65rem .85rem;
        border:1px solid #98a2b3;
        border-radius:10px;
        background:#f8fafc;
        margin:.7rem 0 1rem;
        font-size:.84rem
    }

    .band-title{
        font-size:1.3rem;
        font-weight:850;
        margin:1.5rem 0 .55rem;
        border-bottom:1px solid #d0d5dd;
        padding-bottom:.3rem
    }

    .band-count{
        color:#667085;
        font-size:.78rem;
        font-weight:500
    }

    .station-card{
        display:grid;
        grid-template-columns:
            minmax(145px,.9fr)
            minmax(260px,1.35fr)
            minmax(230px,1.2fr);
        align-items:center;
        gap:clamp(.7rem,1.5vw,1.2rem);
        border:1px solid #98a2b380;
        border-radius:14px;
        padding:.9rem 1rem;
        margin-bottom:.65rem;
        min-width:0;
        overflow:hidden;
        box-shadow:0 1px 3px #0000000b
    }

    .station-area,
    .departure-area,
    .summary-area{
        min-width:0
    }

    .station-name{
        font-weight:900;
        line-height:1.05;
        letter-spacing:-.04em;
        overflow-wrap:anywhere
    }

    .station-suffix{
        font-size:13px;
        margin-left:2px
    }

    .location{
        color:#667085;
        font-size:.78rem;
        margin-top:.3rem
    }

    .departure-area{
        display:flex;
        align-items:center;
        gap:.75rem
    }

    .departure-message{
        font-size:clamp(1rem,1.7vw,1.25rem);
        font-weight:850;
        line-height:1.25
    }

    .departure-time{
        font-size:clamp(1.65rem,3vw,2.15rem);
        font-weight:950;
        letter-spacing:-.05em
    }

    .departure-suffix{
        font-size:.95rem;
        font-weight:800;
        margin-left:.2rem
    }

    .arrival{
        color:#667085;
        font-size:.74rem;
        margin-top:.25rem
    }

    .clock{
        position:relative;
        width:62px;
        height:62px;
        border:2px solid #344054;
        border-radius:50%;
        background:#ffffffcf;
        flex:0 0 62px
    }

    .clock-number{
        position:absolute;
        width:12px;
        height:12px;
        margin:-6px;
        text-align:center;
        line-height:12px;
        font-size:7px;
        font-weight:750;
        color:#475467
    }

    .hand{
        position:absolute;
        left:29px;
        bottom:30px;
        transform-origin:bottom center;
        background:#344054;
        border-radius:4px
    }

    .hour-hand{
        width:4px;
        height:15px
    }

    .minute-hand{
        width:2px;
        height:21px
    }

    .clock-center{
        position:absolute;
        left:27px;
        top:27px;
        width:6px;
        height:6px;
        border-radius:50%;
        background:#344054
    }

    .route-main{
        font-size:.9rem;
        font-weight:800;
        line-height:1.4;
        overflow-wrap:anywhere
    }

    .meta-row{
        display:flex;
        gap:.35rem;
        flex-wrap:wrap;
        margin-top:.45rem
    }

    .chip{
        padding:.22rem .43rem;
        border-radius:7px;
        background:#ffffffb0;
        border:1px solid #d0d5ddbb;
        font-size:.69rem;
        font-weight:700
    }

    details{
        margin-top:.5rem;
        font-size:.72rem;
        color:#475467
    }

    summary{
        cursor:pointer;
        font-weight:750;
        color:#344054;
        list-style:none
    }

    summary::-webkit-details-marker{
        display:none
    }

    summary:after{
        content:" ＋";
        color:#667085
    }

    details[open] summary:after{
        content:" −"
    }

    .details-body{
        margin-top:.45rem;
        padding:.55rem .65rem;
        border-radius:8px;
        background:#ffffff9c;
        line-height:1.65
    }

    .detail-label{
        font-weight:800;
        color:#344054
    }

    .empty{
        padding:2rem;
        text-align:center;
        border:1px dashed #98a2b3;
        border-radius:14px;
        color:#667085
    }

    @media(max-width:900px){
        .station-card{
            grid-template-columns:
                minmax(140px,.75fr)
                minmax(240px,1.25fr)
        }

        .summary-area{
            grid-column:1/-1;
            border-top:1px solid #98a2b34d;
            padding-top:.55rem
        }
    }

    @media(max-width:620px){
        .block-container{
            padding-top:4rem!important
        }

        .station-card{
            display:block
        }

        .departure-area,
        .summary-area{
            margin-top:.75rem
        }

        .clock{
            width:56px;
            height:56px;
            flex-basis:56px
        }

        .clock-number{
            display:none
        }

        .hand{
            left:26px;
            bottom:27px
        }

        .hour-hand{
            height:14px
        }

        .minute-hand{
            height:19px
        }

        .clock-center{
            left:24px;
            top:24px
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. 目的駅・到着時刻
# ============================================================
stations = sorted(station_info)
default_station = (
    stations.index("新橋")
    if "新橋" in stations
    else 0
)

destination_column, time_column = st.columns([2, 1])

with destination_column:
    st.markdown(
        '<div class="selector-label">目的駅</div>',
        unsafe_allow_html=True,
    )
    destination = st.selectbox(
        "目的駅",
        stations,
        index=default_station,
        label_visibility="collapsed",
    )

with time_column:
    st.markdown(
        '<div class="selector-label">到着時刻</div>',
        unsafe_allow_html=True,
    )
    arrival_time = st.time_input(
        "到着時刻",
        value=time(8, 0),
        step=60,
        label_visibility="collapsed",
    )

target = arrival_time.strftime("%H:%M")

st.markdown(
    compact_html(
        f"""
        <div class="page-title">
            {escape(destination)}駅に{target}までに着くには？
        </div>
        <div class="subtitle">
            どの駅で、何時発の電車に乗れば間に合うか
        </div>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# 5. 検索結果作成
# ============================================================
rows = search_routes(destination, target)
df = pd.DataFrame(rows)

bands = [
    "15分以内",
    "30分以内",
    "45分以内",
    "60分以内",
    "60分超",
]

if not df.empty:
    df["時間圏"] = df["所要時間"].apply(time_band)


# ============================================================
# 6. 絞り込み条件
# ============================================================
with st.popover("⚙️ 絞り込み条件"):
    selected_bands = st.multiselect(
        f"{destination}までの所要時間",
        bands,
        default=bands,
    )

    keyword = st.text_input(
        "駅名検索",
        placeholder="例：浅草、新宿",
    )

    route_options = (
        sorted(df["経路"].unique())
        if not df.empty
        else []
    )

    selected_routes = st.multiselect(
        "利用路線",
        route_options,
        default=route_options,
    )

st.markdown(
    f"""
    <div class="notice">
        <strong>乗換なしの直通列車のみ表示しています。</strong>
        対象ダイヤ：{escape(data["service_date"])}｜
        GTFS取得：{escape(data.get("gtfs_fetched_at") or "取得日時不明")}
    </div>
    """,
    unsafe_allow_html=True,
)

if not df.empty:
    df = df[
        df["時間圏"].isin(selected_bands)
        & df["経路"].isin(selected_routes)
    ].copy()

    if keyword.strip():
        df = df[
            df["駅名"].str.contains(
                keyword.strip(),
                na=False,
                regex=False,
            )
        ]


# ============================================================
# 7. 駅カード表示
# ============================================================
if df.empty:
    st.markdown(
        '<div class="empty">'
        "条件に一致する直通列車がありません。"
        "</div>",
        unsafe_allow_html=True,
    )

else:
    for band in bands:
        band_df = df[df["時間圏"] == band]

        if band_df.empty:
            continue

        st.markdown(
            f'<div class="band-title">{band} '
            f'<span class="band-count">'
            f'{len(band_df)}駅'
            f"</span></div>",
            unsafe_allow_html=True,
        )

        for _, row in band_df.iterrows():
            station = escape(str(row["駅名"]))
            route = escape(str(row["経路"]))
            train_destination = escape(str(row["行先"]))
            lines = escape(
                " ／ ".join(row["路線一覧"])
            )
            line_count = len(row["路線一覧"])

            card = f"""
            <div class="station-card"
                 style="background:{line_color(str(row["経路"]))}">

                <div class="station-area">
                    <div class="station-name"
                         style="font-size:{station_font(line_count)}px">
                        {station}
                        <span class="station-suffix">駅</span>
                    </div>
                    <div class="location">
                        都営交通ネットワーク
                    </div>
                </div>

                <div class="departure-area">
                    {clock_html(str(row["出発"]))}

                    <div>
                        <div class="departure-message">
                            <span class="departure-time">
                                {row["出発"]}
                            </span>
                            <span class="departure-suffix">
                                発の電車に乗る
                            </span>
                        </div>

                        <div class="arrival">
                            {escape(destination)}駅 {row["到着"]}着
                        </div>
                    </div>
                </div>

                <div class="summary-area">
                    <div class="route-main">
                        {route}・乗換なし
                    </div>

                    <div class="meta-row">
                        <span class="chip">乗換なし</span>
                        <span class="chip">
                            {line_count}路線接続
                        </span>
                    </div>

                    <details>
                        <summary>経路の詳細を見る</summary>

                        <div class="details-body">
                            <div>
                                <span class="detail-label">
                                    所要時間：
                                </span>
                                {row["所要時間"]}分
                            </div>

                            <div>
                                <span class="detail-label">
                                    到着：
                                </span>
                                {row["到着"]}
                            </div>

                            <div>
                                <span class="detail-label">
                                    利用経路：
                                </span>
                                {route}
                            </div>

                            <div>
                                <span class="detail-label">
                                    列車の行先：
                                </span>
                                {train_destination}
                            </div>

                            <div>
                                <span class="detail-label">
                                    駅の乗り入れ：
                                </span>
                                {lines}
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
# 8. 表・CSV
# ============================================================
with st.expander("検索結果を表で確認する"):
    if df.empty:
        st.info("表示できる検索結果がありません。")

    else:
        output = df[
            [
                "駅名",
                "出発",
                "到着",
                "所要時間",
                "経路",
                "行先",
            ]
        ].copy()

        st.dataframe(
            output,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "CSVで保存",
            output.to_csv(
                index=False
            ).encode("utf-8-sig"),
            (
                f"{destination}_"
                f"{target.replace(':', '')}_direct.csv"
            ),
            "text/csv",
        )


# ============================================================
# 9. 出典・免責
# ============================================================
st.caption(
    "東京都交通局が公共交通オープンデータセンターを通じて"
    "提供するGTFSデータを加工して利用しています（CC BY 4.0）。"
)

st.caption(
    "正確性・完全性は保証されません。表示内容について"
    "交通事業者へ直接問い合わせないでください。"
)
