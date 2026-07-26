from datetime import time
from html import escape
from pathlib import Path
import json

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
    # 絞り込み用の所要時間帯
    return next(
        (f"{x}分以内" for x in (15, 30, 45, 60) if minutes <= x),
        "60分超",
    )


def rent_man(value):
    # 円を万円単位へ変換
    return f"{float(value) / 10000:.1f}万円" if pd.notna(value) else ""


def compact_html(text):
    # Streamlitで余分な空白を作らない
    return " ".join(x.strip() for x in text.splitlines())


def line_color(route):
    # 路線ごとの背景色
    return next(
        (color for name, color in LINE_COLORS.items() if name in route),
        DEFAULT_COLOR,
    )


def search_routes(destination, target):
    # 指定時刻までに着く最新の直通列車を駅ごとに選ぶ
    target_min, latest = minute(target), {}

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
    /* 全体 */
    .block-container{
        max-width:1240px;
        padding:3.4rem 1rem 3rem!important;
    }

    /* 入力欄 */
    .selector-label{
        color:var(--text-color);
        opacity:.68;
        font-size:.74rem;
        font-weight:750;
        margin-bottom:.18rem;
    }

    /* タイトルと注意書き */
    .heading-row{
        display:flex;
        align-items:baseline;
        justify-content:space-between;
        gap:1rem;
        margin:.55rem 0 .65rem;
    }
    .page-title{
        color:var(--text-color);
        font-size:clamp(1.35rem,2.7vw,2rem);
        font-weight:900;
        line-height:1.2;
        letter-spacing:-.04em;
    }
    .page-note{
        color:var(--text-color);
        opacity:.62;
        font-size:.7rem;
        text-align:right;
        white-space:nowrap;
    }

    /* 駅カード */
    .station-card{
        --card-bg:#f8fafc;
        display:grid;
        grid-template-columns:minmax(150px,1fr) minmax(135px,.85fr)
            minmax(175px,1.1fr) auto;
        grid-template-areas:
            "station departure route details"
            "location arrival rent details";
        align-items:center;
        column-gap:clamp(.7rem,2vw,1.5rem);
        row-gap:.08rem;
        color:#283141!important;
        background:var(--card-bg)!important;
        border:1px solid #98a2b380;
        border-radius:13px;
        padding:.72rem 1rem;
        margin-bottom:.48rem;
        box-shadow:0 1px 3px #0000000b;
        overflow:hidden;
    }

    /* 端末テーマに関係なくカード内は黒系文字 */
    .station-card,
    .station-card div,
    .station-card span,
    .station-card summary{
        color:#283141!important;
    }

    .station-name{
        grid-area:station;
        min-width:0;
        font-size:clamp(1.3rem,2.3vw,1.75rem);
        font-weight:900;
        line-height:1.05;
        letter-spacing:-.04em;
        overflow-wrap:anywhere;
    }
    .location{
        grid-area:location;
        color:#667085!important;
        font-size:.7rem;
        margin-top:.15rem;
    }

    .departure{
        grid-area:departure;
        font-size:clamp(1.5rem,2.8vw,2rem);
        font-weight:950;
        letter-spacing:-.05em;
        white-space:nowrap;
    }
    .arrival{
        grid-area:arrival;
        color:#667085!important;
        font-size:.7rem;
        white-space:nowrap;
    }

    .route{
        grid-area:route;
        font-size:.83rem;
        font-weight:850;
        line-height:1.25;
        overflow-wrap:anywhere;
    }
    .rent{
        grid-area:rent;
        color:#475467!important;
        font-size:.72rem;
        font-weight:750;
    }

    .details-area{
        grid-area:details;
        min-width:70px;
        text-align:right;
    }
    details{
        font-size:.7rem;
    }
    summary{
        cursor:pointer;
        list-style:none;
        font-weight:800;
        white-space:nowrap;
    }
    summary::-webkit-details-marker{display:none}
    summary:after{
        content:" ›";
        color:#667085!important;
        font-size:.9rem;
    }
    details[open] summary:after{content:" −"}
    .details-body{
        position:absolute;
        z-index:5;
        right:1rem;
        width:min(360px,calc(100vw - 3rem));
        margin-top:.4rem;
        padding:.65rem .75rem;
        border:1px solid #d0d5dd;
        border-radius:9px;
        background:#fff;
        color:#283141!important;
        text-align:left;
        line-height:1.65;
        box-shadow:0 7px 20px #0002;
    }
    .details-body,
    .details-body div,
    .details-body span{
        color:#283141!important;
    }
    .detail-label{font-weight:850}

    .empty{
        color:var(--text-color);
        padding:2rem;
        text-align:center;
        border:1px dashed rgba(128,128,128,.6);
        border-radius:13px;
    }

    /* 条件ボタンを小さくする */
    div[data-testid="stPopover"] button{
        min-height:38px!important;
        padding:.3rem .5rem!important;
    }

    /* スマホ */
    @media(max-width:620px){
        .block-container{
            padding:3rem .65rem 2.5rem!important;
        }

        /* 目的駅・時刻・条件を横並びのまま維持 */
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
            font-size:.61rem;
            margin-bottom:.1rem;
        }

        .heading-row{
            display:block;
            margin:.45rem 0 .55rem;
        }
        .page-title{
            font-size:1.05rem;
            line-height:1.25;
        }
        .page-note{
            margin-top:.16rem;
            font-size:.58rem;
            text-align:left;
            white-space:normal;
        }

        /* スマホは3行・2列 */
        .station-card{
            grid-template-columns:minmax(0,1fr) auto;
            grid-template-areas:
                "station departure"
                "location arrival"
                "route rent"
                "details details";
            gap:.18rem .65rem;
            padding:.62rem .72rem;
            border-radius:11px;
            margin-bottom:.42rem;
        }

        .station-name{
            font-size:1.34rem;
        }
        .location{
            font-size:.64rem;
        }
        .departure{
            font-size:1.5rem;
            text-align:right;
        }
        .arrival{
            font-size:.62rem;
            text-align:right;
        }
        .route{
            padding-top:.3rem;
            border-top:1px solid #98a2b338;
            font-size:.68rem;
        }
        .rent{
            padding-top:.3rem;
            border-top:1px solid #98a2b338;
            font-size:.66rem;
            text-align:right;
            white-space:nowrap;
        }
        .details-area{
            padding-top:.25rem;
            text-align:right;
        }
        details{font-size:.65rem}
        .details-body{
            position:relative;
            right:auto;
            width:auto;
            margin-top:.35rem;
            box-shadow:none;
        }
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
destination_column, time_column, filter_column = st.columns([2.4, 1.05, .42])

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

    with st.popover("⚙️"):
        selected_bands = st.multiselect(
            f"{destination}までの所要時間",
            bands,
            default=bands,
        )
        keyword = st.text_input("駅名検索", placeholder="例：浅草、新宿")
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
        <div class="heading-row">
            <div class="page-title">
                {escape(destination)}に{target}までに着くには？
            </div>
            <div class="page-note">
                直通のみ｜対象ダイヤ {escape(data["service_date"])}
            </div>
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
        rent = row["家賃25㎡"]

        rent_text = (
            f"家賃目安 {escape(rent_man(rent))}"
            if pd.notna(rent)
            else "家賃情報なし"
        )
        rent_detail = (
            f"""
            <div>
                <span class="detail-label">家賃目安：</span>
                25㎡換算 約{escape(rent_man(rent))}
            </div>
            <div>
                <span class="detail-label">統計：</span>
                {escape(str(data.get("rent_source_year", "2023")))}年
                住宅・土地統計調査
            </div>
            """
            if pd.notna(rent)
            else ""
        )

        card = f"""
        <div class="station-card"
             style="--card-bg:{line_color(str(row["経路"]))}">
            <div class="station-name">{station}</div>
            <div class="location">{location}</div>

            <div class="departure">{row["出発"]}発</div>
            <div class="arrival">
                {escape(destination)} {row["到着"]}着
            </div>

            <div class="route">{route}・直通</div>
            <div class="rent">{rent_text}</div>

            <div class="details-area">
                <details>
                    <summary>詳細</summary>
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
                            <span class="detail-label">出発：</span>
                            {row["出発"]}
                        </div>
                        <div>
                            <span class="detail-label">到着：</span>
                            {row["到着"]}
                        </div>
                        <div>
                            <span class="detail-label">利用経路：</span>
                            {route}
                        </div>
                        <div>
                            <span class="detail-label">列車の行先：</span>
                            {train_destination}
                        </div>
                        <div>
                            <span class="detail-label">乗り入れ：</span>
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
    "家賃目安は住宅・土地統計調査の市区町村別1㎡当たり家賃を"
    "25㎡に換算した参考値です。"
)
st.caption(
    "東京都交通局が公共交通オープンデータセンターを通じて提供する"
    "GTFSデータを加工して利用しています（CC BY 4.0）。"
)
st.caption(
    "所在地はGTFS座標と国土地理院の情報を基に自治体単位で表示しています。"
)
