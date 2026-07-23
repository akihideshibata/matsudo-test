from datetime import datetime
from html import escape

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
# 経路、乗り入れ路線を保持する。
# 現在の時刻・経路は表示確認用の仮データ。
# ============================================================
DATA = [
    ("北千住", "東京都", "足立区", "07:42", "07:55", 13, 0,
     "JR常磐線",
     "JR常磐線|千代田線|日比谷線|東武線|つくばエクスプレス"),
    ("日暮里", "東京都", "荒川区", "07:36", "07:57", 21, 0,
     "JR常磐線",
     "山手線|京浜東北線|常磐線|京成本線|成田スカイアクセス|舎人ライナー"),
    ("上野", "東京都", "台東区", "07:34", "07:57", 23, 0,
     "JR常磐線",
     "山手線|京浜東北線|常磐線|宇都宮線|高崎線|新幹線|銀座線|日比谷線"),
    ("西日暮里", "東京都", "荒川区", "07:32", "07:57", 25, 1,
     "千代田線 → JR常磐線",
     "山手線|京浜東北線|千代田線|舎人ライナー"),
    ("秋葉原", "東京都", "千代田区", "07:27", "07:57", 30, 1,
     "JR山手線 → JR常磐線",
     "山手線|京浜東北線|中央・総武線|日比谷線|つくばエクスプレス"),
    ("東京", "東京都", "千代田区", "07:24", "07:57", 33, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|中央線|東海道線|宇都宮線|高崎線|横須賀線|京葉線|新幹線|丸ノ内線"),
    ("神田", "東京都", "千代田区", "07:23", "07:57", 34, 1,
     "JR山手線 → JR常磐線",
     "山手線|京浜東北線|中央線|銀座線"),
    ("新橋", "東京都", "港区", "07:19", "07:57", 38, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|東海道線|横須賀線|銀座線|浅草線"),
    ("御茶ノ水", "東京都", "千代田区", "07:18", "07:57", 39, 1,
     "中央・総武線 → JR常磐線",
     "中央線|中央・総武線|丸ノ内線"),
    ("浜松町", "東京都", "港区", "07:15", "07:57", 42, 1,
     "JR山手線 → JR常磐線",
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
     "日比谷線 → JR線 → JR常磐線",
     "日比谷線|大江戸線"),
    ("新宿", "東京都", "新宿区", "07:01", "07:57", 56, 1,
     "JR山手線 → JR常磐線",
     "山手線|中央線|総武線|埼京線|湘南新宿ライン|小田急線|京王線|丸ノ内線|新宿線|大江戸線"),
    ("渋谷", "東京都", "渋谷区", "06:55", "07:57", 62, 1,
     "JR山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東横線|田園都市線|井の頭線|銀座線|半蔵門線|副都心線"),
    ("池袋", "東京都", "豊島区", "06:54", "07:57", 63, 1,
     "JR山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東上線|池袋線|丸ノ内線|有楽町線|副都心線"),
    ("恵比寿", "東京都", "渋谷区", "06:52", "07:57", 65, 1,
     "JR山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|日比谷線"),
    ("柏", "千葉県", "柏市", "07:39", "07:48", 9, 0,
     "JR常磐線",
     "JR常磐線|東武アーバンパークライン"),
    ("流山おおたかの森", "千葉県", "流山市", "07:30", "07:55", 25, 1,
     "つくばエクスプレス → JR常磐線",
     "つくばエクスプレス|東武アーバンパークライン"),
]


# ============================================================
# 3. データ加工用関数
# ============================================================
def to_minutes(text):
    """HH:MMを並べ替え用の分数へ変換する。"""
    value = datetime.strptime(text, "%H:%M")
    return value.hour * 60 + value.minute


def time_band(minutes):
    """所要時間を15分刻みで分類する。"""
    if minutes <= 15:
        return "15分以内"
    if minutes <= 30:
        return "30分以内"
    if minutes <= 45:
        return "45分以内"
    if minutes <= 60:
        return "60分以内"
    return "60分超"


def clock_angles(text):
    """アナログ時計の短針・長針の角度を返す。"""
    hour, minute = map(int, text.split(":"))
    return (hour % 12) * 30 + minute * 0.5, minute * 6


def station_font(line_count):
    """乗り入れ路線数に応じて駅名を少し大きくする。"""
    return min(36, 23 + line_count)


def compact_html(text):
    """HTMLを1行化し、コードブロック化を防ぐ。"""
    return " ".join(line.strip() for line in text.splitlines())


# ============================================================
# 4. DataFrame作成
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

# 遅く出発できる順。同時刻なら乗換回数と所要時間で並べる。
df = df.sort_values(
    ["出発分", "乗換回数", "所要時間"],
    ascending=[False, True, True],
).reset_index(drop=True)


# ============================================================
# 5. デザイン
# ============================================================
st.markdown(
    """
    <style>
    .block-container{max-width:1280px;padding-top:1.5rem}
    .page-title{font-size:2.5rem;font-weight:900;letter-spacing:-.05em}
    .subtitle{color:#667085;margin:.25rem 0 1rem}
    .notice{padding:.7rem .9rem;border:1px solid #f2c94c;border-radius:10px;
        background:#fff9df;margin-bottom:1.1rem;font-size:.88rem}
    .band-title{font-size:1.35rem;font-weight:850;margin:1.7rem 0 .65rem;
        border-bottom:1px solid #d0d5dd;padding-bottom:.35rem}
    .band-count{font-size:.8rem;color:#667085;font-weight:500}
    .station-card{border:1px solid #d0d5dd;border-radius:15px;padding:1rem;
        margin-bottom:.8rem;background:#fff;box-shadow:0 1px 3px #0000000b;
        min-height:260px}
    .station-head{display:flex;justify-content:space-between;gap:.8rem}
    .station-name{font-weight:900;line-height:1.05;letter-spacing:-.04em}
    .station-suffix{font-size:14px}
    .location{color:#667085;font-size:.82rem;margin-top:.35rem}
    .clock-time{display:flex;align-items:center;gap:.65rem;white-space:nowrap}
    .digital{text-align:right}
    .digital-label{font-size:.7rem;color:#667085}
    .digital-time{font-size:1.65rem;font-weight:900;line-height:1}
    .arrival{font-size:.72rem;color:#667085;margin-top:.2rem}
    .clock{position:relative;width:54px;height:54px;border:3px solid #344054;
        border-radius:50%;background:white;flex-shrink:0}
    .clock:after{content:"";position:absolute;width:6px;height:6px;
        background:#344054;border-radius:50%;left:21px;top:21px}
    .hand{position:absolute;left:24px;bottom:24px;transform-origin:bottom center;
        background:#344054;border-radius:5px}
    .hour-hand{width:4px;height:15px}
    .minute-hand{width:2px;height:20px}
    .duration-row{display:flex;align-items:baseline;gap:.35rem;margin-top:.85rem}
    .duration-number{font-size:2.15rem;font-weight:900;letter-spacing:-.05em}
    .duration-label{font-size:.85rem;color:#667085;font-weight:700}
    .chips{display:flex;gap:.35rem;flex-wrap:wrap;margin:.55rem 0}
    .chip{padding:.25rem .48rem;border-radius:7px;background:#f2f4f7;
        font-size:.75rem;font-weight:700}
    .route{font-size:.83rem;line-height:1.45;margin-top:.45rem}
    .lines{font-size:.75rem;color:#667085;line-height:1.4;margin-top:.35rem}
    .empty{padding:2rem;text-align:center;border:1px dashed #98a2b3;
        border-radius:14px;color:#667085}
    @media(max-width:800px){
        .page-title{font-size:2rem}
        .station-card{min-height:0}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 6. タイトル
# ============================================================
st.markdown(
    compact_html(
        """
        <div class="page-title">松戸駅に8時までに着くには？</div>
        <div class="subtitle">
            各駅から最も遅く出発できる時刻を一覧表示
        </div>
        <div class="notice">
            <strong>現在は画面確認用の仮データです。</strong>
            時刻・経路は今後、正式な交通データへ置き換えます。
        </div>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# 7. 左側の検索条件
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

    st.caption("駅名は乗り入れ路線数が多いほど大きく表示されます。")


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


# ============================================================
# 9. 概要
# ============================================================
col1, col2, col3 = st.columns(3)
col1.metric("表示中", f"{len(filtered)}駅")
col2.metric(
    "最も遅い出発",
    filtered.iloc[0]["出発"] if not filtered.empty else "—",
)
col3.metric(
    "乗換なし",
    f"{int((filtered['乗換回数'] == 0).sum())}駅",
)


# ============================================================
# 10. 時間圏ごとに、駅を横2列で表示
# ============================================================
if filtered.empty:
    st.markdown(
        '<div class="empty">条件に一致する駅がありません。</div>',
        unsafe_allow_html=True,
    )

for band in bands:
    band_df = filtered[filtered["時間圏"] == band].reset_index(drop=True)

    if band_df.empty:
        continue

    st.markdown(
        f'<div class="band-title">{band} '
        f'<span class="band-count">{len(band_df)}駅</span></div>',
        unsafe_allow_html=True,
    )

    # 2駅ずつ横に並べ、スクロール量を減らす。
    for start in range(0, len(band_df), 2):
        columns_ui = st.columns(2, gap="medium")

        for offset, column in enumerate(columns_ui):
            index = start + offset
            if index >= len(band_df):
                continue

            row = band_df.iloc[index]
            hour_angle, minute_angle = clock_angles(row["出発"])
            station = escape(row["駅名"])
            location = escape(f'{row["都道府県"]}{row["市区"]}')
            route = escape(row["経路"])
            lines = " ／ ".join(escape(x) for x in row["路線一覧"])
            transfer = (
                "乗換なし"
                if row["乗換回数"] == 0
                else f'乗換{row["乗換回数"]}回'
            )
            font_size = station_font(row["路線数"])

            card = f"""
            <div class="station-card">
                <div class="station-head">
                    <div>
                        <div class="station-name" style="font-size:{font_size}px">
                            {station}<span class="station-suffix">駅</span>
                        </div>
                        <div class="location">{location}</div>
                    </div>

                    <div class="clock-time">
                        <div class="clock">
                            <div class="hand hour-hand"
                                style="transform:rotate({hour_angle}deg)"></div>
                            <div class="hand minute-hand"
                                style="transform:rotate({minute_angle}deg)"></div>
                        </div>
                        <div class="digital">
                            <div class="digital-label">最終出発</div>
                            <div class="digital-time">{row["出発"]}</div>
                            <div class="arrival">松戸 {row["到着"]}着</div>
                        </div>
                    </div>
                </div>

                <div class="duration-row">
                    <span class="duration-number">{row["所要時間"]}</span>
                    <span class="duration-label">分</span>
                </div>

                <div class="chips">
                    <span class="chip">{transfer}</span>
                    <span class="chip">{row["路線数"]}路線</span>
                    <span class="chip">{row["時間圏"]}</span>
                </div>

                <div class="route"><strong>経路：</strong>{route}</div>
                <div class="lines"><strong>乗り入れ：</strong>{lines}</div>
            </div>
            """

            with column:
                st.markdown(
                    compact_html(card),
                    unsafe_allow_html=True,
                )


# ============================================================
# 11. データ確認とCSV保存
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
