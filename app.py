from datetime import datetime
from html import escape
import math

import pandas as pd
import streamlit as st


# ============================================================
# 1. ページ設定
# ============================================================
st.set_page_config(
    page_title="松戸8時｜逆算通勤",
    page_icon="🚃",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# 2. 仮データ
#
# 駅名、都道府県、市区、出発、到着、所要時間、乗換回数、
# 乗換駅、利用経路、駅へ乗り入れる路線
#
# 現在は画面確認用。後ほど交通APIへ置き換える。
# ============================================================
DATA = [
    ("北千住", "東京都", "足立区", "07:42", "07:55", 13, 0, "なし",
     "JR常磐線", "JR常磐線|千代田線|日比谷線|東武線|つくばエクスプレス"),
    ("柏", "千葉県", "柏市", "07:39", "07:48", 9, 0, "なし",
     "JR常磐線", "JR常磐線|東武アーバンパークライン"),
    ("日暮里", "東京都", "荒川区", "07:36", "07:57", 21, 0, "なし",
     "JR常磐線", "山手線|京浜東北線|常磐線|京成本線|成田スカイアクセス|舎人ライナー"),
    ("上野", "東京都", "台東区", "07:34", "07:57", 23, 0, "なし",
     "JR常磐線", "山手線|京浜東北線|常磐線|宇都宮線|高崎線|新幹線|銀座線|日比谷線"),
    ("西日暮里", "東京都", "荒川区", "07:32", "07:57", 25, 1, "北千住",
     "千代田線 → JR常磐線", "山手線|京浜東北線|千代田線|舎人ライナー"),
    ("流山おおたかの森", "千葉県", "流山市", "07:30", "07:55", 25, 1, "南流山",
     "つくばエクスプレス → JR武蔵野線 → JR常磐線",
     "つくばエクスプレス|東武アーバンパークライン"),
    ("秋葉原", "東京都", "千代田区", "07:27", "07:57", 30, 1, "上野",
     "山手線 → JR常磐線",
     "山手線|京浜東北線|中央・総武線|日比谷線|つくばエクスプレス"),
    ("東京", "東京都", "千代田区", "07:24", "07:57", 33, 0, "なし",
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|中央線|東海道線|宇都宮線|高崎線|横須賀線|京葉線|新幹線|丸ノ内線"),
    ("神田", "東京都", "千代田区", "07:23", "07:57", 34, 1, "上野",
     "山手線 → JR常磐線", "山手線|京浜東北線|中央線|銀座線"),
    ("新橋", "東京都", "港区", "07:19", "07:57", 38, 0, "なし",
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|東海道線|横須賀線|銀座線|浅草線"),
    ("御茶ノ水", "東京都", "千代田区", "07:18", "07:57", 39, 1, "秋葉原",
     "中央・総武線 → JR常磐線", "中央線|中央・総武線|丸ノ内線"),
    ("浜松町", "東京都", "港区", "07:15", "07:57", 42, 1, "上野",
     "山手線 → JR常磐線", "山手線|京浜東北線|東京モノレール|浅草線|大江戸線"),
    ("日本橋", "東京都", "中央区", "07:14", "07:57", 43, 1, "上野",
     "銀座線 → JR常磐線", "銀座線|東西線|浅草線"),
    ("品川", "東京都", "港区", "07:11", "07:57", 46, 0, "なし",
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|東海道線|横須賀線|東海道新幹線|京急本線"),
    ("銀座", "東京都", "中央区", "07:10", "07:57", 47, 1, "上野",
     "銀座線 → JR常磐線", "銀座線|丸ノ内線|日比谷線"),
    ("大手町", "東京都", "千代田区", "07:09", "07:57", 48, 1, "北千住",
     "千代田線 → JR常磐線", "丸ノ内線|東西線|千代田線|半蔵門線|三田線"),
    ("飯田橋", "東京都", "千代田区", "07:08", "07:57", 49, 1, "西日暮里",
     "東西線 → JR常磐線", "中央・総武線|東西線|有楽町線|南北線|大江戸線"),
    ("六本木", "東京都", "港区", "07:03", "07:57", 54, 2, "日比谷・北千住",
     "日比谷線 → 千代田線 → JR常磐線", "日比谷線|大江戸線"),
    ("新宿", "東京都", "新宿区", "07:01", "07:57", 56, 1, "日暮里",
     "山手線 → JR常磐線",
     "山手線|中央線|総武線|埼京線|湘南新宿ライン|小田急線|京王線|丸ノ内線|新宿線|大江戸線"),
    ("渋谷", "東京都", "渋谷区", "06:55", "07:57", 62, 1, "日暮里",
     "山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東横線|田園都市線|井の頭線|銀座線|半蔵門線|副都心線"),
    ("池袋", "東京都", "豊島区", "06:54", "07:57", 63, 1, "日暮里",
     "山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東上線|池袋線|丸ノ内線|有楽町線|副都心線"),
    ("恵比寿", "東京都", "渋谷区", "06:52", "07:57", 65, 1, "日暮里",
     "山手線 → JR常磐線", "山手線|埼京線|湘南新宿ライン|日比谷線"),
]


# ============================================================
# 3. 路線ごとの背景色
#
# 公式のラインカラーそのものではなく、
# 視認性を保つため白に近づけた試作用の淡色。
# ============================================================
LINE_COLORS = {
    "山手線": "#f5faed", "JR常磐線": "#eef9f1", "常磐線": "#eef9f1",
    "千代田線": "#eef9f6", "日比谷線": "#f7f7f7", "銀座線": "#fff8e9",
    "丸ノ内線": "#fff2f2", "東西線": "#edf8fc", "半蔵門線": "#f5f1fa",
    "有楽町線": "#faf7e9", "南北線": "#eff8f5", "大江戸線": "#f8f0fa",
    "浅草線": "#fbf1f2", "中央線": "#fff6e9", "中央・総武線": "#fffbea",
    "京浜東北線": "#edf8fc", "つくばエクスプレス": "#f7f0fa",
    "上野東京ライン": "#faf3eb", "東海道線": "#faf3eb",
}
DEFAULT_COLOR = "#f8fafc"


# ============================================================
# 4. データ加工・HTML作成用関数
# ============================================================
def to_minutes(text):
    """HH:MMを並べ替え用の分数に変換する。"""
    value = datetime.strptime(text, "%H:%M")
    return value.hour * 60 + value.minute


def time_band(minutes):
    """所要時間を15分刻みで分類する。"""
    return next(
        (f"{limit}分以内" for limit in (15, 30, 45, 60) if minutes <= limit),
        "60分超",
    )


def compact_html(text):
    """HTMLを1行化し、コードブロック化を防ぐ。"""
    return " ".join(line.strip() for line in text.splitlines())


def line_color(line):
    """路線名に対応する淡色を返す。"""
    return next(
        (color for name, color in LINE_COLORS.items() if name in line),
        DEFAULT_COLOR,
    )


def route_parts(route):
    """経路を分割し、重複する路線を除外する。"""
    text = route.replace("・常磐線直通", " → JR常磐線")
    return list(dict.fromkeys(part.strip() for part in text.split("→")))


def card_background(route):
    """利用路線に応じて単色または斜め分割背景を作る。"""
    colors = list(dict.fromkeys(line_color(x) for x in route_parts(route)))[:3]
    if len(colors) == 1:
        return colors[0]
    stops = 100 / len(colors)
    sections = []
    for i, color in enumerate(colors):
        sections += [f"{color} {i * stops:.0f}%", f"{color} {(i + 1) * stops:.0f}%"]
    return f"linear-gradient(135deg,{','.join(sections)})"


def station_font(line_count):
    """路線数が多い駅を少し大きく表示する。"""
    return min(33, 24 + line_count * .8)


def clock_html(text):
    """1〜12の数字を付けたアナログ時計を作る。"""
    hour, minute = map(int, text.split(":"))
    hour_angle, minute_angle = (hour % 12) * 30 + minute * .5, minute * 6
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


# ============================================================
# 5. DataFrame作成
# ============================================================
COLUMNS = [
    "駅名", "都道府県", "市区", "出発", "到着", "所要時間",
    "乗換回数", "乗換駅", "経路", "路線文字列",
]

df = pd.DataFrame(DATA, columns=COLUMNS)
df["路線一覧"] = df["路線文字列"].str.split("|")
df["路線数"] = df["路線一覧"].str.len()
df["時間圏"] = df["所要時間"].apply(time_band)
df["出発分"] = df["出発"].apply(to_minutes)
df = df.sort_values(
    ["出発分", "乗換回数", "所要時間"],
    ascending=[False, True, True],
).reset_index(drop=True)


# ============================================================
# 6. 画面デザイン
# ============================================================
st.markdown(
    """
    <style>
    .block-container{max-width:1180px;padding:1.3rem 1.2rem 4rem}
    .page-title{font-size:clamp(1.8rem,4vw,2.5rem);font-weight:900;letter-spacing:-.05em}
    .subtitle{color:#667085;margin:.25rem 0 1rem}
    .notice{padding:.65rem .85rem;border:1px solid #f2c94c;border-radius:10px;
        background:#fff9df;margin:.7rem 0 1rem;font-size:.84rem}
    .toolbar{display:flex;align-items:center;gap:.6rem;margin:.5rem 0}
    .result-count{font-size:.82rem;color:#667085}
    .band-title{font-size:1.3rem;font-weight:850;margin:1.5rem 0 .55rem;
        border-bottom:1px solid #d0d5dd;padding-bottom:.3rem}
    .band-count{color:#667085;font-size:.78rem;font-weight:500}

    /* 横長カード。幅が足りない場合は自動的に項目を折り返す */
    .station-card{display:grid;
        grid-template-columns:minmax(145px,1fr) minmax(220px,1.25fr)
        minmax(105px,.55fr) minmax(210px,1.25fr);
        align-items:center;gap:clamp(.55rem,1.4vw,1rem);
        border:1px solid rgba(152,162,179,.5);border-radius:14px;
        padding:.8rem clamp(.75rem,1.5vw,1rem);margin-bottom:.6rem;
        min-width:0;box-shadow:0 1px 3px #0000000b;overflow:hidden}
    .station-area,.departure-area,.duration-area,.route-area{min-width:0}
    .station-name{font-weight:900;line-height:1.05;letter-spacing:-.04em;
        overflow-wrap:anywhere}
    .station-suffix{font-size:13px;margin-left:2px}
    .location{color:#667085;font-size:.78rem;margin-top:.3rem}

    .departure-area{display:flex;align-items:center;gap:.6rem}
    .departure-copy{min-width:0}
    .departure-sentence{font-size:.73rem;color:#475467;font-weight:750;
        line-height:1.25}
    .departure-time{font-size:clamp(1.45rem,2.5vw,1.9rem);
        font-weight:900;line-height:1;letter-spacing:-.04em}
    .arrival{font-size:.72rem;color:#667085;margin-top:.2rem;white-space:nowrap}

    .clock{position:relative;width:62px;height:62px;border:2px solid #344054;
        border-radius:50%;background:#ffffffc9;flex:0 0 62px}
    .clock-number{position:absolute;width:12px;height:12px;margin:-6px;
        text-align:center;line-height:12px;font-size:7px;font-weight:750;color:#475467}
    .hand{position:absolute;left:29px;bottom:30px;transform-origin:bottom center;
        background:#344054;border-radius:4px}
    .hour-hand{width:4px;height:15px}.minute-hand{width:2px;height:21px}
    .clock-center{position:absolute;left:27px;top:27px;width:6px;height:6px;
        border-radius:50%;background:#344054}

    .duration-area{border-left:1px solid #98a2b380;border-right:1px solid #98a2b380;
        text-align:center;padding:0 .55rem}
    .duration-number{font-size:clamp(1.8rem,3vw,2.35rem);font-weight:900;
        line-height:1;letter-spacing:-.06em}
    .duration-unit{font-size:.85rem;font-weight:750}
    .duration-label{display:block;color:#667085;font-size:.66rem;margin-top:.2rem}

    .route-main{font-size:.86rem;font-weight:800;line-height:1.35;overflow-wrap:anywhere}
    .route-meta{display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.35rem}
    .chip{padding:.2rem .4rem;border-radius:7px;background:#ffffffa8;
        border:1px solid #d0d5ddaa;font-size:.67rem;font-weight:700}
    .line-tooltip{cursor:help}
    .transfer{color:#667085;font-size:.7rem;margin-top:.35rem;overflow-wrap:anywhere}
    .empty{padding:2rem;text-align:center;border:1px dashed #98a2b3;
        border-radius:14px;color:#667085}

    /* 中程度の画面では経路を2段目へ回す */
    @media(max-width:1050px){
        .station-card{grid-template-columns:minmax(140px,.8fr)
            minmax(210px,1.15fr) minmax(100px,.55fr)}
        .route-area{grid-column:1/-1;border-top:1px solid #98a2b34d;
            padding-top:.55rem}
    }

    /* 狭い画面では2列にして、カード外へのはみ出しを防ぐ */
    @media(max-width:700px){
        .station-card{grid-template-columns:minmax(0,1fr) minmax(0,1.15fr)}
        .duration-area{border:0;text-align:left;padding:0}
        .route-area{grid-column:1/-1}
        .clock{width:54px;height:54px;flex-basis:54px}
        .clock-number{display:none}
        .hand{left:25px;bottom:26px}
        .hour-hand{height:13px}.minute-hand{height:18px}
        .clock-center{left:23px;top:23px}
    }

    @media(max-width:460px){
        .station-card{display:block}
        .departure-area,.duration-area,.route-area{margin-top:.65rem}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 7. タイトルと絞り込みボタン
# ============================================================
st.markdown(
    compact_html(
        """
        <div class="page-title">松戸駅に8時までに着くには？</div>
        <div class="subtitle">どの駅で、何時の電車に乗れば間に合うか</div>
        """
    ),
    unsafe_allow_html=True,
)

bands = ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"]

# ボタンを押したときだけ絞り込み条件を表示する。
with st.popover("⚙️ 絞り込み条件", use_container_width=False):
    selected_bands = st.multiselect("松戸までの所要時間", bands, default=bands)
    transfer_label = st.radio(
        "乗換条件", ["乗換なし", "1回まで", "2回まで"],
        index=2, horizontal=True,
    )
    selected_prefectures = st.multiselect(
        "都道府県", sorted(df["都道府県"].unique()),
        default=sorted(df["都道府県"].unique()),
    )
    selected_areas = st.multiselect(
        "区・市", sorted(df["市区"].unique()),
        default=sorted(df["市区"].unique()),
    )
    keyword = st.text_input("駅名検索", placeholder="例：新橋、上野")

max_transfers = {"乗換なし": 0, "1回まで": 1, "2回まで": 2}[transfer_label]

st.markdown(
    """
    <div class="notice">
        <strong>現在は画面確認用の仮データです。</strong>
        時刻と経路は今後、正式な交通データへ置き換えます。
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 8. 絞り込み
# ============================================================
filtered = df[
    df["時間圏"].isin(selected_bands)
    & (df["乗換回数"] <= max_transfers)
    & df["都道府県"].isin(selected_prefectures)
    & df["市区"].isin(selected_areas)
].copy()

if keyword.strip():
    filtered = filtered[
        filtered["駅名"].str.contains(keyword.strip(), na=False)
    ]

filtered = filtered.reset_index(drop=True)
st.caption(f"{len(filtered)}駅を表示中")


# ============================================================
# 9. 駅カード表示
# ============================================================
if filtered.empty:
    st.markdown(
        '<div class="empty">条件に一致する駅がありません。</div>',
        unsafe_allow_html=True,
    )

for band in bands:
    band_df = filtered[filtered["時間圏"] == band]
    if band_df.empty:
        continue

    st.markdown(
        f'<div class="band-title">{band} '
        f'<span class="band-count">{len(band_df)}駅</span></div>',
        unsafe_allow_html=True,
    )

    for _, row in band_df.iterrows():
        station = escape(row["駅名"])
        location = escape(f'{row["都道府県"]}{row["市区"]}')
        route = escape(row["経路"]).replace(
            " → ", '<span style="color:#667085"> → </span>'
        )
        transfer = (
            "乗換なし"
            if row["乗換回数"] == 0
            else f'{escape(row["乗換駅"])}で乗換'
        )
        all_lines = escape("／".join(row["路線一覧"]))
        tooltip = escape(
            f'{row["路線数"]}路線が接続：{"、".join(row["路線一覧"])}',
            quote=True,
        )

        card = f"""
        <div class="station-card"
             style="background:{card_background(row['経路'])}">

            <div class="station-area">
                <div class="station-name"
                     style="font-size:{station_font(row['路線数'])}px">
                    {station}<span class="station-suffix">駅</span>
                </div>
                <div class="location">{location}</div>
            </div>

            <div class="departure-area">
                {clock_html(row["出発"])}
                <div class="departure-copy">
                    <div class="departure-sentence">
                        この電車に乗れば間に合う
                    </div>
                    <div class="departure-time">{row["出発"]}</div>
                    <div class="arrival">松戸駅 {row["到着"]}着</div>
                </div>
            </div>

            <div class="duration-area">
                <span class="duration-number">{row["所要時間"]}</span>
                <span class="duration-unit">分</span>
                <span class="duration-label">電車・乗換の所要時間</span>
            </div>

            <div class="route-area">
                <div class="route-main">{route}</div>
                <div class="route-meta">
                    <span class="chip">{transfer}</span>
                    <span class="chip line-tooltip"
                          title="{tooltip}">
                        {row["路線数"]}路線接続 ⓘ
                    </span>
                </div>
                <div class="transfer">
                    {transfer if row["乗換回数"] else "松戸まで乗換なし"}
                </div>
            </div>
        </div>
        """

        st.markdown(compact_html(card), unsafe_allow_html=True)


# ============================================================
# 10. データ確認・CSV保存
# ============================================================
with st.expander("仮データを表で確認する"):
    output = df[
        ["駅名", "都道府県", "市区", "出発", "到着", "所要時間",
         "乗換回数", "乗換駅", "経路", "路線数"]
    ]
    st.dataframe(output, use_container_width=True, hide_index=True)
    st.download_button(
        "CSVで保存",
        output.to_csv(index=False).encode("utf-8-sig"),
        "matsudo_8am_sample.csv",
        "text/csv",
    )

st.caption("Matsudo 8:00 prototype｜時刻と経路は表示確認用の仮データです。")
