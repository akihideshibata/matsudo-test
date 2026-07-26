from datetime import time
from html import escape
from pathlib import Path
import json, math

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

data = json.loads(Path("direct_timetable.json").read_text(encoding="utf-8"))

station_info = {
    x["name"]: {
        "routes": x["routes"],
        "location": x.get("location", "所在地未登録"),
        "rent_per_sqm": x.get("rent_per_sqm"),
        "rent_25sqm": x.get("rent_25sqm"),
    }
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
    # HH:MMを比較用の分数へ変換
    h, m = map(int, text.split(":"))
    return h * 60 + m


def clock(value):
    # 分数をHH:MMへ戻す
    return f"{value // 60 % 24:02d}:{value % 60:02d}"


def time_band(minutes):
    # 絞り込みに使う所要時間帯
    return next(
        (f"{x}分以内" for x in (15, 30, 45, 60) if minutes <= x),
        "60分超",
    )


def rent_man(value):
    # 円を万円単位に変換
    return f"{float(value) / 10000:.1f}万円" if pd.notna(value) else ""


def compact_html(text):
    # Streamlitで余分な改行を作らない
    return " ".join(x.strip() for x in text.splitlines())


def line_color(route):
    # 路線ごとのカード背景色
    return next(
        (color for name, color in LINE_COLORS.items() if name in route),
        DEFAULT_COLOR,
    )


def station_font(count):
    # 乗り入れ路線数に応じて駅名を少し調整
    return min(33, 24 + count * 0.8)


def clock_html(text):
    # PC表示用のアナログ時計
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
    # 指定時刻までに着く最新の直通列車を駅ごとに選ぶ
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

                info = station_info.get(station, {})
                candidate = {
                    "駅名": station,
                    "所在地": info.get("location", "所在地未登録"),
                    "家賃25㎡": info.get("rent_25sqm"),
                    "家賃㎡単価": info.get("rent_per_sqm"),
                    "出発": clock(departure),
                    "到着": clock(arrival),
                    "所要時間": arrival - departure,
                    "経路": trip["route"],
                    "行先": trip["destination"],
                    "路線一覧": info.get("routes", [trip["route"]]),
                    "出発分": departure,
                }

                if station not in latest or departure > latest[station]["出発分"]:
                    latest[station] = candidate

    return sorted(latest.values(), key=lambda x: x["出発分"], reverse=True)


# ============================================================
# 3. デザイン
# ============================================================
st.markdown(
    """
    <style>
    /* ページ全体 */
    .block-container{
        max-width:1180px;
        padding:3.6rem 1.1rem 4rem!important;
    }

    /* 上部検索欄 */
    .selector-label{
        color:var(--text-color);
        opacity:.68;
        font-size:.76rem;
        font-weight:750;
        margin-bottom:.22rem;
    }
    .page-title{
        color:var(--text-color);
        font-size:clamp(1.65rem,3.6vw,2.45rem);
        font-weight:900;
        line-height:1.2;
        letter-spacing:-.05em;
        margin-top:.65rem;
    }
    .subtitle{
        color:var(--text-color);
        opacity:.66;
        margin:.3rem 0 .7rem;
    }
    .mobile-summary{
        display:none;
        color:var(--text-color);
        opacity:.7;
        font-size:.76rem;
        margin:.35rem 0 .5rem;
    }

    /* 注意欄は端末テーマに合わせる */
    .notice{
        color:var(--text-color)!important;
        background:rgba(128,128,128,.08);
        border:1px solid rgba(128,128,128,.45);
        border-radius:10px;
        padding:.55rem .75rem;
        margin:.45rem 0 .8rem;
        font-size:.78rem;
    }
    .notice *{color:inherit!important}

    /* カード */
    .station-card{
        display:grid;
        grid-template-columns:minmax(180px,.95fr) minmax(250px,1.3fr)
            minmax(210px,1fr);
        align-items:center;
        gap:clamp(.7rem,1.5vw,1.2rem);
        border:1px solid #98a2b380;
        border-radius:14px;
        padding:.78rem 1rem;
        margin-bottom:.58rem;
        min-width:0;
        overflow:hidden;
        box-shadow:0 1px 3px #0000000b;
    }

    /* カード内は端末テーマに関係なく濃色表示 */
    .station-card,
    .station-card div,
    .station-card span,
    .station-card summary{
        color:#283141;
    }
    .station-area,.departure-area,.summary-area{min-width:0}

    .station-name{
        font-weight:900;
        line-height:1.05;
        letter-spacing:-.04em;
        overflow-wrap:anywhere;
    }
    .station-suffix{
        font-size:13px;
        margin-left:2px;
    }
    .location{
        color:#667085!important;
        font-size:.76rem;
        margin-top:.26rem;
    }

    /* 家賃 */
    .rent-box{
        margin-top:.45rem;
        padding-top:.38rem;
        border-top:1px solid #98a2b340;
    }
    .rent-label{
        color:#667085!important;
        font-size:.66rem;
        font-weight:800;
    }
    .rent-value{
        color:#344054!important;
        font-size:.86rem;
        font-weight:850;
        margin-top:.05rem;
    }

    /* 発着時刻 */
    .departure-area{
        display:flex;
        align-items:center;
        gap:.7rem;
    }
    .departure-time{
        color:#283141!important;
        font-size:clamp(1.8rem,3vw,2.25rem);
        font-weight:950;
        letter-spacing:-.05em;
        white-space:nowrap;
    }
    .departure-suffix{
        font-size:.95rem;
        font-weight:850;
        margin-left:.18rem;
    }
    .arrival{
        color:#667085!important;
        font-size:.73rem;
        margin-top:.18rem;
    }

    /* 時計 */
    .clock{
        position:relative;
        width:62px;
        height:62px;
        border:2px solid #344054;
        border-radius:50%;
        background:#fff;
        flex:0 0 62px;
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
        color:#475467!important;
    }
    .hand{
        position:absolute;
        left:29px;
        bottom:30px;
        transform-origin:bottom center;
        background:#344054;
        border-radius:4px;
    }
    .hour-hand{width:4px;height:15px}
    .minute-hand{width:2px;height:21px}
    .clock-center{
        position:absolute;
        left:27px;
        top:27px;
        width:6px;
        height:6px;
        border-radius:50%;
        background:#344054;
    }

    /* 路線・詳細 */
    .route-main{
        font-size:.88rem;
        font-weight:850;
        line-height:1.35;
        overflow-wrap:anywhere;
    }
    .meta-row{
        display:flex;
        gap:.32rem;
        flex-wrap:wrap;
        margin-top:.38rem;
    }
    .chip{
        color:#344054!important;
        padding:.18rem .4rem;
        border-radius:7px;
        background:#ffffffb5;
        border:1px solid #d0d5dd;
        font-size:.65rem;
        font-weight:750;
    }
    details{
        margin-top:.4rem;
        font-size:.7rem;
    }
    summary{
        cursor:pointer;
        font-weight:750;
        list-style:none;
    }
    summary::-webkit-details-marker{display:none}
    summary:after{content:" ＋";color:#667085!important}
    details[open] summary:after{content:" −"}
    .details-body{
        margin-top:.4rem;
        padding:.5rem .6rem;
        border-radius:8px;
        background:#ffffffa8;
        line-height:1.6;
    }
    .detail-label{font-weight:800}

    .empty{
        color:var(--text-color);
        padding:2rem;
        text-align:center;
        border:1px dashed rgba(128,128,128,.6);
        border-radius:14px;
    }

    /* タブレット */
    @media(max-width:900px){
        .station-card{
            grid-template-columns:minmax(165px,.8fr) minmax(240px,1.2fr);
        }
        .summary-area{
            grid-column:1/-1;
            border-top:1px solid #98a2b34d;
            padding-top:.5rem;
        }
    }

    /* スマホ */
    @media(max-width:620px){
        .block-container{
            padding:3.2rem .65rem 3rem!important;
        }

        /* Streamlitの列をスマホでも横並びに保つ */
        div[data-testid="stHorizontalBlock"]{
            display:flex!important;
            flex-direction:row!important;
            flex-wrap:nowrap!important;
            gap:.35rem!important;
            align-items:flex-end!important;
        }
        div[data-testid="stHorizontalBlock"] > div{
            min-width:0!important;
        }

        .selector-label{
            font-size:.62rem;
            margin-bottom:.12rem;
        }
        .page-title,.subtitle{display:none}
        .mobile-summary{display:block}
        .notice{
            padding:.42rem .55rem;
            margin:.25rem 0 .55rem;
            font-size:.66rem;
        }

        /* スマホカードは情報密度を優先 */
        .station-card{
            display:grid;
            grid-template-columns:minmax(0,1fr) auto;
            grid-template-areas:
                "station departure"
                "rent route"
                "detail detail";
            align-items:start;
            gap:.42rem .7rem;
            padding:.72rem .78rem;
            border-radius:12px;
            margin-bottom:.48rem;
        }
        .station-area{grid-area:station}
        .departure-area{
            grid-area:departure;
            display:block;
            text-align:right;
        }
        .summary-area{
            grid-area:route;
            border:0;
            padding:0;
            text-align:right;
            align-self:end;
        }

        .station-name{
            font-size:1.38rem!important;
            line-height:1.08;
        }
        .station-suffix{font-size:.68rem}
        .location{
            font-size:.67rem;
            margin-top:.16rem;
        }

        .rent-box{
            grid-area:rent;
            border-top:1px solid #98a2b340;
            margin-top:.28rem;
            padding-top:.32rem;
        }
        .rent-label{font-size:.59rem}
        .rent-value{font-size:.76rem}

        .clock{display:none}
        .departure-time{
            display:block;
            font-size:1.62rem;
            line-height:1;
        }
        .departure-suffix{
            display:block;
            font-size:.68rem;
            margin:.1rem 0 0;
        }
        .arrival{
            font-size:.62rem;
            margin-top:.15rem;
            white-space:nowrap;
        }

        .route-main{
            font-size:.71rem;
            line-height:1.3;
        }
        .meta-row{display:none}

        details{
            grid-area:detail;
            margin-top:.15rem;
            border-top:1px solid #98a2b340;
            padding-top:.35rem;
            text-align:left;
            font-size:.65rem;
        }
        .details-body{font-size:.64rem}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. 目的駅・到着時刻・絞り込み
# ============================================================
stations = sorted(station_info)
default_station = stations.index("新橋") if "新橋" in stations else 0

destination_column, time_column, filter_column = st.columns([2.2, 1, .55])

with destination_column:
    st.markdown('<div class="selector-label">目的駅</div>', unsafe_allow_html=True)
    destination = st.selectbox(
        "目的駅",
        stations,
        index=default_station,
        label_visibility="collapsed",
    )

with time_column:
    st.markdown('<div class="selector-label">到着</div>', unsafe_allow_html=True)
    arrival_time = st.time_input(
        "到着時刻",
        value=time(8, 0),
        step=60,
        label_visibility="collapsed",
    )

target = arrival_time.strftime("%H:%M")
df = pd.DataFrame(search_routes(destination, target))
bands = ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"]

if not df.empty:
    df["時間圏"] = df["所要時間"].apply(time_band)

with filter_column:
    st.markdown('<div class="selector-label">条件</div>', unsafe_allow_html=True)

    with st.popover("⚙️", use_container_width=True):
        selected_bands = st.multiselect(
            f"{destination}までの所要時間",
            bands,
            default=bands,
        )
        keyword = st.text_input(
            "駅名検索",
            placeholder="例：浅草、新宿",
        )
        route_options = sorted(df["経路"].unique()) if not df.empty else []
        selected_routes = st.multiselect(
            "利用路線",
            route_options,
            default=route_options,
        )


# ============================================================
# 5. タイトル・検索条件
# ============================================================
st.markdown(
    compact_html(f"""
        <div class="page-title">
            {escape(destination)}駅に{target}までに着くには？
        </div>
        <div class="subtitle">
            どの駅で、何時発の電車に乗れば間に合うか
        </div>
        <div class="mobile-summary">
            {escape(destination)}駅 {target}着・乗換なし
        </div>
    """),
    unsafe_allow_html=True,
)

st.markdown(
    compact_html(f"""
        <div class="notice">
            <strong>乗換なしの直通列車のみ表示</strong>｜
            対象ダイヤ：{escape(data["service_date"])}｜
            GTFS取得：{escape(data.get("gtfs_fetched_at") or "不明")}
        </div>
    """),
    unsafe_allow_html=True,
)

if not df.empty:
    df = df[
        df["時間圏"].isin(selected_bands)
        & df["経路"].isin(selected_routes)
    ].copy()

    if keyword.strip():
        df = df[
            df["駅名"].str.contains(keyword.strip(), na=False, regex=False)
        ]


# ============================================================
# 6. カード表示
# ============================================================
if df.empty:
    st.markdown(
        '<div class="empty">条件に一致する直通列車がありません。</div>',
        unsafe_allow_html=True,
    )
else:
    for _, row in df.iterrows():
        station = escape(str(row["駅名"]))
        location = escape(str(row["所在地"]))
        route = escape(str(row["経路"]))
        train_destination = escape(str(row["行先"]))
        lines = escape(" ／ ".join(row["路線一覧"]))
        line_count = len(row["路線一覧"])
        rent = row["家賃25㎡"]

        rent_box = ""
        rent_detail = ""

        if pd.notna(rent):
            rent_value = escape(rent_man(rent))
            rent_box = f"""
                <div class="rent-box">
                    <div class="rent-label">公的家賃水準</div>
                    <div class="rent-value">25㎡換算 約{rent_value}</div>
                </div>
            """
            rent_detail = f"""
                <div>
                    <span class="detail-label">公的家賃水準：</span>
                    25㎡換算 約{rent_value}
                </div>
                <div>
                    <span class="detail-label">家賃データ：</span>
                    {escape(str(data.get("rent_source_year", "2023")))}年
                    住宅・土地統計調査
                </div>
            """

        card = f"""
        <div class="station-card"
             style="background:{line_color(str(row["経路"]))}">
            <div class="station-area">
                <div class="station-name"
                     style="font-size:{station_font(line_count)}px">
                    {station}<span class="station-suffix">駅</span>
                </div>
                <div class="location">{location}</div>
                {rent_box}
            </div>

            <div class="departure-area">
                {clock_html(str(row["出発"]))}
                <div>
                    <div>
                        <span class="departure-time">{row["出発"]}発</span>
                    </div>
                    <div class="arrival">
                        {escape(destination)}駅 {row["到着"]}着
                    </div>
                </div>
            </div>

            <div class="summary-area">
                <div class="route-main">{route}・乗換なし</div>
                <div class="meta-row">
                    <span class="chip">乗換なし</span>
                    <span class="chip">{line_count}路線接続</span>
                </div>

                <details>
                    <summary>詳細を見る</summary>
                    <div class="details-body">
                        <div>
                            <span class="detail-label">所在地：</span>{location}
                        </div>
                        {rent_detail}
                        <div>
                            <span class="detail-label">所要時間：</span>
                            {row["所要時間"]}分
                        </div>
                        <div>
                            <span class="detail-label">到着：</span>{row["到着"]}
                        </div>
                        <div>
                            <span class="detail-label">利用経路：</span>{route}
                        </div>
                        <div>
                            <span class="detail-label">列車の行先：</span>
                            {train_destination}
                        </div>
                        <div>
                            <span class="detail-label">駅の乗り入れ：</span>
                            {lines}
                        </div>
                    </div>
                </details>
            </div>
        </div>
        """

        st.markdown(compact_html(card), unsafe_allow_html=True)


# ============================================================
# 7. 表・CSV・出典
# ============================================================
with st.expander("検索結果を表で確認する"):
    if df.empty:
        st.info("表示できる検索結果がありません。")
    else:
        output = df[[
            "駅名",
            "所在地",
            "家賃25㎡",
            "出発",
            "到着",
            "所要時間",
            "経路",
            "行先",
        ]].copy()

        output["家賃25㎡"] = output["家賃25㎡"].apply(
            lambda x: rent_man(x) if pd.notna(x) else ""
        )

        st.dataframe(output, use_container_width=True, hide_index=True)
        st.download_button(
            "CSVで保存",
            output.to_csv(index=False).encode("utf-8-sig"),
            f"{destination}_{target.replace(':', '')}_direct.csv",
            "text/csv",
        )

st.caption(
    "東京都交通局が公共交通オープンデータセンターを通じて提供する"
    "GTFSデータを加工して利用しています（CC BY 4.0）。"
)
st.caption(
    "所在地はGTFS座標と国土地理院の情報を基に自治体単位で表示しています。"
)
st.caption(
    "家賃水準は住宅・土地統計調査の市区町村別1㎡当たり家賃を"
    "25㎡に換算した参考値です。"
)
st.caption(
    "正確性・完全性は保証されません。表示内容について交通事業者へ"
    "直接問い合わせないでください。"
)
