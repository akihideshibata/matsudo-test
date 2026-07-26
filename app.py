from datetime import time
from html import escape
from pathlib import Path
import json, math
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="逆算通勤｜直通版", page_icon="🚇",
    layout="wide", initial_sidebar_state="collapsed",
)

data = json.loads(Path("direct_timetable.json").read_text(encoding="utf-8"))
station_info = {
    x["name"]: {
        "routes": x.get("routes", []),
        "location": x.get("location", "所在地未登録"),
        "rent": x.get("rent_25sqm"),
    } for x in data["stations"]
}
timetables = data.get("timetables", {
    "weekday": data.get("trips", []), "saturday": [], "sunday": []
})
service_dates = data.get("service_dates", {"weekday": data.get("service_date", "")})
if "show_nearby" not in st.session_state: st.session_state.show_nearby = False

LINE_STYLES = {
    "浅草線": ("#e85298", "#fff2f7"), "三田線": ("#0079c2", "#edf8ff"),
    "新宿線": ("#6cbb5a", "#f1faef"), "大江戸線": ("#b6007a", "#fbf0f8"),
    "荒川線": ("#ee7b1a", "#fff8eb"),
    "日暮里・舎人ライナー": ("#9caeb7", "#f3f6f7"),
}
DEFAULT_STYLE = ("#667085", "#f8fafc")


# ============================================================
# 計算
# ============================================================
def minute(text):
    h, m = map(int, text.split(":"))
    return h * 60 + m


def clock(value): return f"{value // 60 % 24:02d}:{value % 60:02d}"


def time_band(minutes):
    return next((f"{x}分以内" for x in (15, 30, 45, 60) if minutes <= x), "60分超")


def rent_man(value):
    return f"{float(value) / 10000:.1f}万円" if pd.notna(value) else ""


def relative_rent(rent, base):
    return None if pd.isna(rent) or pd.isna(base) or not base else round(float(rent) / float(base) * 100)


def compact_html(text): return " ".join(x.strip() for x in text.splitlines())


def line_style(route):
    return next((v for k, v in LINE_STYLES.items() if k in route), DEFAULT_STYLE)


def station_label(name):
    return f"{'・'.join(station_info[name]['routes'])}｜{name}"


def show_nearby():
    # ボタンのコールバックで安全に状態変更
    st.session_state.show_nearby = True


def clock_html(text):
    hour, minutes = map(int, text.split(":"))
    numbers = ""
    for n in range(1, 13):
        angle = math.radians(n * 30 - 90)
        x, y = 26 + 20 * math.cos(angle), 26 + 20 * math.sin(angle)
        numbers += f'<span class="clock-number" style="left:{x}px;top:{y}px">{n}</span>'
    return f"""<div class="clock">{numbers}
    <div class="hand hour-hand" style="transform:rotate({(hour % 12) * 30 + minutes * .5}deg)"></div>
    <div class="hand minute-hand" style="transform:rotate({minutes * 6}deg)"></div>
    <div class="clock-center"></div></div>"""


def search_routes(trips, destination, target):
    target_min, latest = minute(target), {}

    for trip in trips:
        for destination_index, destination_stop in enumerate(trip["stops"]):
            if destination_stop[0] != destination: continue
            arrival = minute(destination_stop[1])
            if arrival > target_min: continue

            for origin in trip["stops"][:destination_index]:
                station, departure = origin[0], minute(origin[2])
                if station == destination or departure >= arrival: continue
                info = station_info.get(station, {})
                candidate = {
                    "駅名": station, "所在地": info.get("location", "所在地未登録"),
                    "家賃": info.get("rent"), "出発": clock(departure),
                    "到着": clock(arrival), "所要時間": arrival - departure,
                    "経路": trip["route"], "行先": trip["destination"],
                    "路線一覧": info.get("routes", [trip["route"]]),
                    "出発分": departure,
                }
                if station not in latest or departure > latest[station]["出発分"]:
                    latest[station] = candidate

    return sorted(latest.values(), key=lambda x: x["出発分"], reverse=True)


# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
.block-container{max-width:1240px;padding:3.25rem 1rem 3rem!important}
.selector-label{color:var(--text-color);opacity:.68;font-size:.72rem;font-weight:750;margin-bottom:.16rem}
.heading-row{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin:.5rem 0 .55rem}
.page-title{color:var(--text-color);font-size:clamp(1.25rem,2.3vw,1.85rem);font-weight:900;line-height:1.2;letter-spacing:-.04em}
.page-note{color:var(--text-color);opacity:.58;font-size:.68rem;text-align:right;white-space:nowrap}
.nearby-row{display:flex;align-items:center;justify-content:space-between;min-height:36px;padding:.35rem .65rem;color:var(--text-color);background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.35);border-radius:9px;font-size:.72rem}
.nearby-row strong{font-weight:850}
.station-card{position:relative;display:grid;grid-template-columns:minmax(145px,1fr) minmax(190px,1.1fr) minmax(180px,1fr) 42px;grid-template-areas:"station departure route info" "location arrival rent info";align-items:center;gap:.08rem clamp(.7rem,1.8vw,1.4rem);color:#283141!important;background:var(--card-bg)!important;border:1px solid #98a2b380;border-left:6px solid var(--line-color)!important;border-radius:12px;padding:.62rem .85rem;margin-bottom:.42rem;box-shadow:0 1px 3px #0000000b}
.station-card,.station-card div,.station-card span,.station-card summary{color:#283141!important}
.station-name{grid-area:station;font-size:clamp(1.25rem,2.2vw,1.7rem);font-weight:900;line-height:1.05;letter-spacing:-.04em;overflow-wrap:anywhere}
.location{grid-area:location;color:#667085!important;font-size:.68rem}
.departure-wrap{grid-area:departure;display:flex;align-items:center;gap:.55rem}
.departure{font-size:clamp(1.45rem,2.6vw,1.95rem);font-weight:950;letter-spacing:-.05em;white-space:nowrap}
.arrival{grid-area:arrival;color:#667085!important;font-size:.68rem;padding-left:58px;white-space:nowrap}
.route{grid-area:route;font-size:.81rem;font-weight:850;line-height:1.25}
.rent{grid-area:rent;color:#475467!important;font-size:.72rem;font-weight:800;white-space:nowrap}
.clock{position:relative;width:52px;height:52px;flex:0 0 52px;border:2px solid #344054;border-radius:50%;background:#fff}
.clock-number{position:absolute;width:10px;height:10px;margin:-5px;text-align:center;line-height:10px;font-size:6px;font-weight:750;color:#475467!important}
.hand{position:absolute;left:24px;bottom:25px;transform-origin:bottom center;background:#344054;border-radius:4px}
.hour-hand{width:4px;height:12px}.minute-hand{width:2px;height:18px}
.clock-center{position:absolute;left:21px;top:21px;width:6px;height:6px;border-radius:50%;background:#344054}
.details-area{grid-area:info;text-align:center}details{font-size:.68rem}
summary{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border:1px solid #98a2b3;border-radius:50%;background:#ffffffb8;cursor:pointer;list-style:none;font-family:serif;font-size:.8rem;font-weight:900}
summary::-webkit-details-marker{display:none}
.details-body{position:absolute;z-index:10;right:.8rem;top:3.2rem;width:min(370px,calc(100vw - 3rem));padding:.65rem .75rem;border:1px solid #d0d5dd;border-radius:9px;background:#fff;text-align:left;line-height:1.65;box-shadow:0 7px 20px #0002}
.details-body,.details-body div,.details-body span{color:#283141!important}.detail-label{font-weight:850}
.empty{color:var(--text-color);padding:2rem;text-align:center;border:1px dashed rgba(128,128,128,.6);border-radius:12px}
div[data-testid="stPopover"] button{min-height:38px!important;padding:.25rem!important}

@media(max-width:620px){
.block-container{padding:2.9rem .55rem 2.5rem!important}
div[data-testid="stHorizontalBlock"]{display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;gap:.3rem!important;align-items:flex-end!important}
div[data-testid="stHorizontalBlock"]>div{min-width:0!important}
.selector-label{font-size:.59rem;margin-bottom:.08rem}.heading-row{display:block;margin:.4rem 0 .45rem}.page-title{font-size:1rem}
.page-note{margin-top:.12rem;font-size:.56rem;text-align:left;white-space:normal}
.nearby-row{min-height:32px;padding:.28rem .5rem;font-size:.62rem}
.station-card{grid-template-columns:minmax(0,1.2fr) minmax(100px,.88fr) minmax(112px,.9fr);grid-template-areas:"station departure rent" "location arrival route";gap:.1rem .32rem;border-left-width:5px!important;border-radius:10px;padding:.48rem .5rem;margin-bottom:.34rem}
.station-name{font-size:1.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.location{font-size:.57rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.departure-wrap{display:block;text-align:left}.clock{display:none}.departure{font-size:1.25rem;line-height:1}
.arrival{padding:0;font-size:.54rem;text-align:left}.rent{position:relative;padding-right:22px;font-size:.58rem;text-align:left}
.route{font-size:.57rem;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.details-area{position:absolute;top:.31rem;right:.3rem}summary{width:20px;height:20px;font-size:.6rem}
.details-body{position:relative;right:auto;top:auto;width:auto;margin-top:.35rem;box-shadow:none}
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# 条件
# ============================================================
stations = sorted(station_info, key=lambda x: ("・".join(station_info[x]["routes"]), x))
destination_col, time_col, filter_col = st.columns([2.5, 1.05, .38])

with destination_col:
    st.markdown('<div class="selector-label">目的駅</div>', unsafe_allow_html=True)
    selected_destination = st.selectbox(
        "目的駅", stations, index=None,
        placeholder="神保町（駅名・路線で検索）",
        format_func=station_label, label_visibility="collapsed",
    )

destination = selected_destination or ("神保町" if "神保町" in station_info else stations[0])

with time_col:
    st.markdown('<div class="selector-label">到着</div>', unsafe_allow_html=True)
    arrival_time = st.time_input(
        "到着時刻", value=time(8), step=60, label_visibility="collapsed",
    )

target = arrival_time.strftime("%H:%M")
destination_rent = station_info.get(destination, {}).get("rent")
weekday_df = pd.DataFrame(search_routes(timetables["weekday"], destination, target))
saturday = {x["駅名"]: x for x in search_routes(timetables.get("saturday", []), destination, target)}
sunday = {x["駅名"]: x for x in search_routes(timetables.get("sunday", []), destination, target)}
bands = ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"]

if not weekday_df.empty:
    weekday_df["時間圏"] = weekday_df["所要時間"].apply(time_band)
    weekday_df["相対家賃"] = weekday_df["家賃"].apply(
        lambda x: relative_rent(x, destination_rent)
    )

with filter_col:
    st.markdown('<div class="selector-label">条件</div>', unsafe_allow_html=True)
    with st.popover("⚙"):
        st.checkbox("10分未満の駅も表示", key="show_nearby")
        rent_filter = st.radio(
            "相対家賃", ["すべて", "100%未満", "100%以上"], horizontal=True
        )
        route_options = sorted(weekday_df["経路"].unique()) if not weekday_df.empty else []
        route_choice = st.pills(
            "利用路線", route_options, default=route_options, selection_mode="multi"
        )
        selected_routes = route_choice or route_options
        selected_bands = st.multiselect(
            f"{destination}までの所要時間", bands, default=bands
        )
        keyword = st.text_input("駅名検索", placeholder="例：浅草、新宿")


# ============================================================
# 絞り込み
# ============================================================
st.markdown(compact_html(f"""
<div class="heading-row">
<div class="page-title">{escape(destination)}に{target}までに着くには？</div>
<div class="page-note">平日・直通のみ｜対象 {escape(service_dates.get("weekday", ""))}</div>
</div>"""), unsafe_allow_html=True)

df = weekday_df.copy()
if not df.empty:
    df = df[df["時間圏"].isin(selected_bands) & df["経路"].isin(selected_routes)]
    if rent_filter == "100%未満": df = df[df["相対家賃"] < 100]
    elif rent_filter == "100%以上": df = df[df["相対家賃"] >= 100]
    if keyword.strip():
        df = df[df["駅名"].str.contains(keyword.strip(), na=False, regex=False)]

nearby_count = len(df[df["所要時間"] < 10]) if not df.empty else 0
if not st.session_state.show_nearby and not df.empty:
    df = df[df["所要時間"] >= 10].copy()


# ============================================================
# 近距離駅通知
# ============================================================
if nearby_count and not st.session_state.show_nearby:
    notice_col, button_col = st.columns([5, 1])
    with notice_col:
        st.markdown(compact_html(f"""
        <div class="nearby-row">
        <strong>少し離れた候補を優先して表示中</strong>
        <span>10分未満の{nearby_count}駅を省略</span>
        </div>"""), unsafe_allow_html=True)
    with button_col:
        st.button(
            "表示する", key="show_nearby_button",
            use_container_width=True, on_click=show_nearby,
        )


# ============================================================
# カード
# ============================================================
if df.empty:
    st.markdown('<div class="empty">条件に一致する直通列車がありません。</div>',
                unsafe_allow_html=True)
else:
    for _, row in df.iterrows():
        station, location = escape(str(row["駅名"])), escape(str(row["所在地"]))
        route, lines = escape(str(row["経路"])), escape(" ／ ".join(row["路線一覧"]))
        accent, background = line_style(str(row["経路"]))
        rent, ratio = row["家賃"], row["相対家賃"]
        sat, sun = saturday.get(row["駅名"]), sunday.get(row["駅名"])

        rent_text = f"相対家賃 {int(ratio)}%" if pd.notna(ratio) else "相対家賃 不明"
        candidate_rent = f"25㎡換算 約{rent_man(rent)}" if pd.notna(rent) else "情報なし"
        base_rent = f"25㎡換算 約{rent_man(destination_rent)}" if pd.notna(destination_rent) else "情報なし"

        def holiday_text(result):
            return f'{result["出発"]}発（{result["到着"]}着）' if result else "該当する直通列車なし"

        card = f"""
        <div class="station-card" style="--line-color:{accent};--card-bg:{background}">
        <div class="station-name">{station}</div>
        <div class="location">{location}</div>
        <div class="departure-wrap">{clock_html(str(row["出発"]))}
        <div class="departure">{row["出発"]}発</div></div>
        <div class="arrival">{escape(destination)} {row["到着"]}着</div>
        <div class="rent">{rent_text}</div>
        <div class="route">{route}・直通</div>
        <div class="details-area"><details><summary>i</summary>
        <div class="details-body">
        <div><span class="detail-label">所在地：</span>{location}</div>
        <div><span class="detail-label">相対家賃：</span>{int(ratio) if pd.notna(ratio) else "算出不可"}%</div>
        <div><span class="detail-label">{station}の家賃目安：</span>{candidate_rent}</div>
        <div><span class="detail-label">{escape(destination)}の家賃目安：</span>{base_rent}</div>
        <div><span class="detail-label">平日：</span>{row["出発"]}発（{row["到着"]}着）</div>
        <div><span class="detail-label">土曜：</span>{holiday_text(sat)}</div>
        <div><span class="detail-label">日曜：</span>{holiday_text(sun)}</div>
        <div><span class="detail-label">所要時間：</span>{row["所要時間"]}分</div>
        <div><span class="detail-label">利用経路：</span>{route}</div>
        <div><span class="detail-label">列車の行先：</span>{escape(str(row["行先"]))}</div>
        <div><span class="detail-label">乗り入れ：</span>{lines}</div>
        </div></details></div></div>
        """
        st.markdown(compact_html(card), unsafe_allow_html=True)


# ============================================================
# 表・出典
# ============================================================
with st.expander("検索結果を表で確認する"):
    if df.empty:
        st.info("表示できる検索結果がありません。")
    else:
        output = df[[
            "駅名", "所在地", "相対家賃", "家賃",
            "出発", "到着", "所要時間", "経路", "行先",
        ]].copy()
        output["相対家賃"] = output["相対家賃"].apply(
            lambda x: f"{int(x)}%" if pd.notna(x) else ""
        )
        output["家賃"] = output["家賃"].apply(
            lambda x: rent_man(x) if pd.notna(x) else ""
        )
        st.dataframe(output, use_container_width=True, hide_index=True)
        st.download_button(
            "CSVで保存", output.to_csv(index=False).encode("utf-8-sig"),
            f"{destination}_{target.replace(':', '')}_direct.csv", "text/csv",
        )

st.caption("相対家賃は、目的駅が属する自治体の公的家賃目安を100%として算出しています。")
st.caption("家賃目安は住宅・土地統計調査の市区町村別1㎡当たり家賃を25㎡に換算した参考値です。")
st.caption("東京都交通局のGTFSデータを加工して利用しています（CC BY 4.0）。")
st.caption("所在地はGTFS座標と国土地理院の情報を基に自治体単位で表示しています。")
