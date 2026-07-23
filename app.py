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
)


# ============================================================
# 2. 仮データ
#
# 駅名、都道府県、市区、出発、到着、所要時間、乗換回数、
# 実際に使う経路、駅へ乗り入れる路線を保持する。
#
# 現在は表示確認用の仮データ。
# 将来は経路検索APIの結果に置き換える。
# ============================================================
DATA = [
    ("北千住", "東京都", "足立区", "07:42", "07:55", 13, 0,
     "JR常磐線",
     "JR常磐線|千代田線|日比谷線|東武線|つくばエクスプレス"),
    ("柏", "千葉県", "柏市", "07:39", "07:48", 9, 0,
     "JR常磐線",
     "JR常磐線|東武アーバンパークライン"),
    ("日暮里", "東京都", "荒川区", "07:36", "07:57", 21, 0,
     "JR常磐線",
     "山手線|京浜東北線|常磐線|京成本線|成田スカイアクセス|舎人ライナー"),
    ("上野", "東京都", "台東区", "07:34", "07:57", 23, 0,
     "JR常磐線",
     "山手線|京浜東北線|常磐線|宇都宮線|高崎線|新幹線|銀座線|日比谷線"),
    ("西日暮里", "東京都", "荒川区", "07:32", "07:57", 25, 1,
     "千代田線 → JR常磐線",
     "山手線|京浜東北線|千代田線|舎人ライナー"),
    ("流山おおたかの森", "千葉県", "流山市", "07:30", "07:55", 25, 1,
     "つくばエクスプレス → JR常磐線",
     "つくばエクスプレス|東武アーバンパークライン"),
    ("秋葉原", "東京都", "千代田区", "07:27", "07:57", 30, 1,
     "山手線 → JR常磐線",
     "山手線|京浜東北線|中央・総武線|日比谷線|つくばエクスプレス"),
    ("東京", "東京都", "千代田区", "07:24", "07:57", 33, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|中央線|東海道線|宇都宮線|高崎線|横須賀線|京葉線|新幹線|丸ノ内線"),
    ("神田", "東京都", "千代田区", "07:23", "07:57", 34, 1,
     "山手線 → JR常磐線",
     "山手線|京浜東北線|中央線|銀座線"),
    ("新橋", "東京都", "港区", "07:19", "07:57", 38, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|東海道線|横須賀線|銀座線|浅草線"),
    ("御茶ノ水", "東京都", "千代田区", "07:18", "07:57", 39, 1,
     "中央・総武線 → JR常磐線",
     "中央線|中央・総武線|丸ノ内線"),
    ("浜松町", "東京都", "港区", "07:15", "07:57", 42, 1,
     "山手線 → JR常磐線",
     "山手線|京浜東北線|東京モノレール|浅草線|大江戸線"),
    ("日本橋", "東京都", "中央区", "07:14", "07:57", 43, 1,
     "銀座線 → JR常磐線",
     "銀座線|東西線|浅草線"),
    ("品川", "東京都", "港区", "07:11", "07:57", 46, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|東海道線|横須賀線|東海道新幹線|京急本線"),
    ("銀座", "東京都", "中央区", "07:10", "07:57", 47, 1,
     "銀座線 → JR常磐線",
     "銀座線|丸ノ内線|日比谷線"),
    ("大手町", "東京都", "千代田区", "07:09", "07:57", 48, 1,
     "千代田線 → JR常磐線",
     "丸ノ内線|東西線|千代田線|半蔵門線|三田線"),
    ("飯田橋", "東京都", "千代田区", "07:08", "07:57", 49, 1,
     "中央・総武線 → JR常磐線",
     "中央・総武線|東西線|有楽町線|南北線|大江戸線"),
    ("六本木", "東京都", "港区", "07:03", "07:57", 54, 2,
     "日比谷線 → 山手線 → JR常磐線",
     "日比谷線|大江戸線"),
    ("新宿", "東京都", "新宿区", "07:01", "07:57", 56, 1,
     "山手線 → JR常磐線",
     "山手線|中央線|総武線|埼京線|湘南新宿ライン|小田急線|京王線|丸ノ内線|新宿線|大江戸線"),
    ("渋谷", "東京都", "渋谷区", "06:55", "07:57", 62, 1,
     "山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東横線|田園都市線|井の頭線|銀座線|半蔵門線|副都心線"),
    ("池袋", "東京都", "豊島区", "06:54", "07:57", 63, 1,
     "山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東上線|池袋線|丸ノ内線|有楽町線|副都心線"),
    ("恵比寿", "東京都", "渋谷区", "06:52", "07:57", 65, 1,
     "山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|日比谷線"),
]


# ============================================================
# 3. 路線ごとの淡い背景色
#
# 正式な交通事業者の色指定ではなく、試作画面用。
# カード背景なので、文字の視認性を保つ淡色にしている。
# ============================================================
LINE_COLORS = {
    "山手線": "#edf8df",
    "JR常磐線": "#e5f5e9",
    "常磐線": "#e5f5e9",
    "千代田線": "#e4f5ef",
    "日比谷線": "#f1f1f1",
    "銀座線": "#fff1d6",
    "丸ノ内線": "#fde8e8",
    "東西線": "#e2f2f8",
    "半蔵門線": "#eee8f8",
    "有楽町線": "#f5efd7",
    "南北線": "#e5f2ee",
    "大江戸線": "#f0e5f3",
    "浅草線": "#f7e6e8",
    "中央線": "#fff0dd",
    "中央・総武線": "#fff8d7",
    "京浜東北線": "#e2f3fa",
    "つくばエクスプレス": "#f1e7f6",
    "上野東京ライン": "#f5eadc",
    "東海道線": "#f5eadc",
    "京成本線": "#f5e7eb",
}
DEFAULT_COLOR = "#f5f7fa"


# ============================================================
# 4. データ加工用関数
# ============================================================
def to_minutes(text):
    """HH:MMを並べ替え用の分数へ変換する。"""
    value = datetime.strptime(text, "%H:%M")
    return value.hour * 60 + value.minute


def time_band(minutes):
    """松戸までの所要時間を15分刻みで分類する。"""
    if minutes <= 15:
        return "15分以内"
    if minutes <= 30:
        return "30分以内"
    if minutes <= 45:
        return "45分以内"
    if minutes <= 60:
        return "60分以内"
    return "60分超"


def compact_html(text):
    """HTMLを1行化し、コードブロックとしての誤表示を防ぐ。"""
    return " ".join(line.strip() for line in text.splitlines())


def station_font(line_count):
    """乗り入れ路線数が多い駅を少し大きく表示する。"""
    return min(34, 25 + line_count * 0.9)


def route_parts(route):
    """経路を矢印で分割し、重複を除く。"""
    parts = [x.strip() for x in route.replace("・常磐線直通", "").split("→")]
    return list(dict.fromkeys(parts))


def line_color(line):
    """路線名に含まれるキーワードから背景色を選ぶ。"""
    for key, color in LINE_COLORS.items():
        if key in line:
            return color
    return DEFAULT_COLOR


def card_background(route):
    """
    利用路線に応じたカード背景を生成する。
    1路線なら単色、複数なら左上から右下へ斜めに分割する。
    """
    colors = [line_color(x) for x in route_parts(route)]
    colors = list(dict.fromkeys(colors))

    if len(colors) == 1:
        return colors[0]

    if len(colors) == 2:
        return (
            f"linear-gradient(135deg,"
            f"{colors[0]} 0%,{colors[0]} 49%,"
            f"{colors[1]} 51%,{colors[1]} 100%)"
        )

    # 3路線以上は斜めに3分割する。
    colors = colors[:3]
    return (
        f"linear-gradient(135deg,"
        f"{colors[0]} 0%,{colors[0]} 32%,"
        f"{colors[1]} 34%,{colors[1]} 65%,"
        f"{colors[2]} 67%,{colors[2]} 100%)"
    )


def clock_html(time_text):
    """数字付きアナログ時計のHTMLを作る。"""
    hour, minute = map(int, time_text.split(":"))
    hour_angle = (hour % 12) * 30 + minute * 0.5
    minute_angle = minute * 6

    numbers = ""
    center, radius = 35, 27

    for number in range(1, 13):
        angle = math.radians(number * 30 - 90)
        x = center + radius * math.cos(angle)
        y = center + radius * math.sin(angle)
        numbers += (
            f'<span class="clock-number" '
            f'style="left:{x}px;top:{y}px">{number}</span>'
        )

    return f"""
    <div class="clock">
        {numbers}
        <div class="clock-hand hour-hand"
             style="transform:rotate({hour_angle}deg)"></div>
        <div class="clock-hand minute-hand"
             style="transform:rotate({minute_angle}deg)"></div>
        <div class="clock-center"></div>
    </div>
    """


# ============================================================
# 5. DataFrame作成
# ============================================================
columns = [
    "駅名", "都道府県", "市区", "出発", "到着", "所要時間",
    "乗換回数", "経路", "路線文字列",
]

df = pd.DataFrame(DATA, columns=columns)
df["路線一覧"] = df["路線文字列"].str.split("|")
df["路線数"] = df["路線一覧"].str.len()
df["時間圏"] = df["所要時間"].apply(time_band)
df["出発分"] = df["出発"].apply(to_minutes)

# 出発できる時刻が遅い順に並べる。
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
    .block-container{
        max-width:1180px;
        padding-top:1.5rem;
        padding-bottom:4rem
    }
    .page-title{
        font-size:2.5rem;
        font-weight:900;
        letter-spacing:-.05em
    }
    .subtitle{
        color:#667085;
        margin:.3rem 0 1rem
    }
    .notice{
        padding:.7rem .9rem;
        border:1px solid #f2c94c;
        border-radius:10px;
        background:#fff9df;
        margin-bottom:1rem;
        font-size:.86rem
    }
    .band-title{
        font-size:1.35rem;
        font-weight:850;
        margin:1.6rem 0 .6rem;
        border-bottom:1px solid #d0d5dd;
        padding-bottom:.35rem
    }
    .band-count{
        color:#667085;
        font-size:.8rem;
        font-weight:500
    }

    /* 横長カード全体 */
    .station-card{
        display:grid;
        grid-template-columns:minmax(210px,1.15fr) 210px 130px minmax(260px,1.4fr);
        align-items:center;
        gap:1rem;
        border:1px solid rgba(152,162,179,.55);
        border-radius:15px;
        padding:.9rem 1.05rem;
        margin-bottom:.65rem;
        min-height:118px;
        box-shadow:0 1px 3px #0000000b
    }

    /* 駅情報 */
    .station-name{
        font-weight:900;
        line-height:1.05;
        letter-spacing:-.04em;
        white-space:nowrap
    }
    .station-suffix{
        font-size:14px;
        margin-left:2px
    }
    .location{
        color:#667085;
        font-size:.82rem;
        margin-top:.35rem
    }

    /* 乗車時刻 */
    .departure-area{
        display:flex;
        align-items:center;
        gap:.7rem
    }
    .departure-copy{
        line-height:1.3
    }
    .departure-time{
        font-size:1.9rem;
        font-weight:900;
        letter-spacing:-.04em;
        white-space:nowrap
    }
    .departure-sentence{
        font-size:.78rem;
        color:#475467;
        font-weight:700
    }
    .arrival{
        font-size:.75rem;
        color:#667085;
        margin-top:.2rem
    }

    /* 数字付きアナログ時計 */
    .clock{
        position:relative;
        width:70px;
        height:70px;
        border:2px solid #344054;
        border-radius:50%;
        background:rgba(255,255,255,.78);
        flex:0 0 70px
    }
    .clock-number{
        position:absolute;
        width:14px;
        height:14px;
        margin-left:-7px;
        margin-top:-7px;
        text-align:center;
        line-height:14px;
        font-size:8px;
        font-weight:750;
        color:#475467
    }
    .clock-hand{
        position:absolute;
        left:33px;
        bottom:34px;
        transform-origin:bottom center;
        background:#344054;
        border-radius:4px
    }
    .hour-hand{
        width:4px;
        height:17px
    }
    .minute-hand{
        width:2px;
        height:24px
    }
    .clock-center{
        position:absolute;
        left:31px;
        top:31px;
        width:6px;
        height:6px;
        border-radius:50%;
        background:#344054
    }

    /* 所要時間 */
    .duration-area{
        border-left:1px solid rgba(152,162,179,.55);
        border-right:1px solid rgba(152,162,179,.55);
        text-align:center;
        padding:0 .8rem
    }
    .duration-number{
        font-size:2.35rem;
        font-weight:900;
        line-height:1;
        letter-spacing:-.06em
    }
    .duration-unit{
        font-size:.9rem;
        font-weight:750;
        margin-left:.2rem
    }
    .duration-label{
        display:block;
        color:#667085;
        font-size:.7rem;
        margin-top:.25rem
    }

    /* 経路情報 */
    .route-main{
        font-size:.9rem;
        font-weight:750;
        line-height:1.45
    }
    .route-arrow{
        color:#667085;
        padding:0 .2rem
    }
    .route-meta{
        display:flex;
        gap:.35rem;
        flex-wrap:wrap;
        margin-top:.45rem
    }
    .chip{
        padding:.23rem .45rem;
        border-radius:7px;
        background:rgba(255,255,255,.68);
        border:1px solid rgba(208,213,221,.7);
        font-size:.7rem;
        font-weight:700
    }
    .all-lines{
        color:#667085;
        font-size:.7rem;
        margin-top:.4rem;
        line-height:1.35
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
            grid-template-columns:1fr 1fr;
            gap:.8rem
        }
        .duration-area{
            border-left:0;
            border-right:0;
            text-align:left;
            padding:0
        }
    }

    @media(max-width:600px){
        .page-title{font-size:2rem}
        .station-card{display:block}
        .departure-area,.duration-area,.route-area{margin-top:.8rem}
        .duration-area{text-align:left}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 7. タイトル
# ============================================================
st.markdown(
    compact_html(
        """
        <div class="page-title">松戸駅に8時までに着くには？</div>
        <div class="subtitle">
            どの駅で、何時の電車に乗れば間に合うか
        </div>
        <div class="notice">
            <strong>現在は画面確認用の仮データです。</strong>
            時刻と経路は今後、正式な交通データへ置き換えます。
        </div>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# 8. 左側の検索条件
# ============================================================
bands = ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"]

with st.sidebar:
    st.header("表示条件")

    selected_bands = st.multiselect(
        "松戸までの所要時間",
        bands,
        default=bands,
    )

    transfer_label = st.radio(
        "乗換条件",
        ["乗換なし", "1回まで", "2回まで"],
        index=2,
    )
    max_transfers = {
        "乗換なし": 0,
        "1回まで": 1,
        "2回まで": 2,
    }[transfer_label]

    prefectures = sorted(df["都道府県"].unique())
    selected_prefectures = st.multiselect(
        "都道府県",
        prefectures,
        default=prefectures,
    )

    areas = sorted(df["市区"].unique())
    selected_areas = st.multiselect(
        "区・市",
        areas,
        default=areas,
    )

    keyword = st.text_input(
        "駅名検索",
        placeholder="例：新橋、上野",
    )

    st.caption(
        "カードの淡い背景色は、利用する路線を表す試作表示です。"
    )


# ============================================================
# 9. 条件に応じて駅を絞り込む
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


# ============================================================
# 10. 駅カードを上から下へ1列表示
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
        lines = " ／ ".join(escape(x) for x in row["路線一覧"])
        transfer = (
            "乗換なし"
            if row["乗換回数"] == 0
            else f'乗換{row["乗換回数"]}回'
        )

        # 経路の矢印ごとに改めてHTML表示する。
        route_display = (
            escape(row["経路"])
            .replace(
                " → ",
                '<span class="route-arrow">→</span>',
            )
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
                    <div class="arrival">
                        松戸駅 {row["到着"]}着
                    </div>
                </div>
            </div>

            <div class="duration-area">
                <span class="duration-number">
                    {row["所要時間"]}
                </span>
                <span class="duration-unit">分</span>
                <span class="duration-label">
                    電車・乗換の所要時間
                </span>
            </div>

            <div class="route-area">
                <div class="route-main">{route_display}</div>

                <div class="route-meta">
                    <span class="chip">{transfer}</span>
                    <span class="chip">{row["路線数"]}路線接続</span>
                    <span class="chip">{row["時間圏"]}</span>
                </div>

                <div class="all-lines">
                    駅の乗り入れ：{lines}
                </div>
            </div>
        </div>
        """

        st.markdown(
            compact_html(card),
            unsafe_allow_html=True,
        )


# ============================================================
# 11. 仮データ確認・CSV保存
# ============================================================
with st.expander("仮データを表で確認する"):
    output_columns = [
        "駅名", "都道府県", "市区", "出発", "到着",
        "所要時間", "時間圏", "乗換回数", "経路", "路線数",
    ]
    output = df[output_columns]

    st.dataframe(
        output,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "CSVで保存",
        output.to_csv(index=False).encode("utf-8-sig"),
        "matsudo_8am_sample.csv",
        "text/csv",
    )


# ============================================================
# 12. フッター
# ============================================================
st.caption(
    "Matsudo 8:00 prototype｜現在の時刻と経路は表示確認用の仮データです。"
)
