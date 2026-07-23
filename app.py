from html import escape
from datetime import datetime

import pandas as pd
import streamlit as st


# ============================================================
# 1. ページ全体の設定
# ============================================================
st.set_page_config(
    page_title="松戸8時｜逆算通勤ランキング",
    page_icon="🚃",
    layout="wide",
)


# ============================================================
# 2. 仮の駅データ
#
# 順番：
# 駅名、区、市区町村以下の住所、出発、松戸到着、所要時間、
# 乗換回数、利用経路、乗り入れ路線
#
# 現段階では画面確認用の仮データ。
# 後ほど経路検索APIの結果に置き換える。
# ============================================================
STATION_DATA = [
    ("北千住", "足立区", "東京都足立区千住旭町", "07:42", "07:55", 13, 0,
     "JR常磐線", "JR常磐線|千代田線|日比谷線|東武線|つくばエクスプレス"),
    ("日暮里", "荒川区", "東京都荒川区西日暮里二丁目", "07:36", "07:57", 21, 0,
     "JR常磐線", "山手線|京浜東北線|常磐線|京成本線|成田スカイアクセス|舎人ライナー"),
    ("上野", "台東区", "東京都台東区上野七丁目", "07:34", "07:57", 23, 0,
     "JR常磐線", "山手線|京浜東北線|常磐線|宇都宮線|高崎線|新幹線|銀座線|日比谷線"),
    ("西日暮里", "荒川区", "東京都荒川区西日暮里五丁目", "07:32", "07:57", 25, 1,
     "千代田線 → JR常磐線", "山手線|京浜東北線|千代田線|舎人ライナー"),
    ("秋葉原", "千代田区", "東京都千代田区外神田一丁目", "07:27", "07:57", 30, 1,
     "JR山手線 → JR常磐線", "山手線|京浜東北線|中央・総武線|日比谷線|つくばエクスプレス"),
    ("東京", "千代田区", "東京都千代田区丸の内一丁目", "07:24", "07:57", 33, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|中央線|東海道線|宇都宮線|高崎線|横須賀線|京葉線|新幹線|丸ノ内線"),
    ("神田", "千代田区", "東京都千代田区鍛冶町二丁目", "07:23", "07:57", 34, 1,
     "JR山手線 → JR常磐線", "山手線|京浜東北線|中央線|銀座線"),
    ("新橋", "港区", "東京都港区新橋二丁目", "07:19", "07:57", 38, 0,
     "上野東京ライン・常磐線直通", "山手線|京浜東北線|東海道線|横須賀線|銀座線|浅草線"),
    ("御茶ノ水", "千代田区", "東京都千代田区神田駿河台二丁目", "07:18", "07:57", 39, 1,
     "中央・総武線 → JR常磐線", "中央線|中央・総武線|丸ノ内線"),
    ("浜松町", "港区", "東京都港区海岸一丁目", "07:15", "07:57", 42, 1,
     "JR山手線 → JR常磐線", "山手線|京浜東北線|東京モノレール|浅草線・大江戸線"),
    ("日本橋", "中央区", "東京都中央区日本橋一丁目", "07:14", "07:57", 43, 1,
     "銀座線 → JR常磐線", "銀座線|東西線|浅草線"),
    ("品川", "港区", "東京都港区高輪三丁目", "07:11", "07:57", 46, 0,
     "上野東京ライン・常磐線直通",
     "山手線|京浜東北線|東海道線|横須賀線|東海道新幹線|京急本線|成田方面特急"),
    ("銀座", "中央区", "東京都中央区銀座四丁目", "07:10", "07:57", 47, 1,
     "銀座線 → JR常磐線", "銀座線|丸ノ内線|日比谷線"),
    ("大手町", "千代田区", "東京都千代田区大手町一丁目", "07:09", "07:57", 48, 1,
     "千代田線 → JR常磐線", "丸ノ内線|東西線|千代田線|半蔵門線|三田線"),
    ("飯田橋", "千代田区", "東京都千代田区飯田橋四丁目", "07:08", "07:57", 49, 1,
     "中央・総武線 → JR常磐線", "中央・総武線|東西線|有楽町線|南北線|大江戸線"),
    ("六本木", "港区", "東京都港区六本木六丁目", "07:03", "07:57", 54, 2,
     "日比谷線 → JR線 → JR常磐線", "日比谷線|大江戸線"),
    ("新宿", "新宿区", "東京都新宿区新宿三丁目", "07:01", "07:57", 56, 1,
     "JR山手線 → JR常磐線",
     "山手線|中央線|総武線|埼京線|湘南新宿ライン|小田急線|京王線|丸ノ内線|新宿線|大江戸線"),
    ("渋谷", "渋谷区", "東京都渋谷区道玄坂一丁目", "06:55", "07:57", 62, 1,
     "JR山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東横線|田園都市線|井の頭線|銀座線|半蔵門線|副都心線"),
    ("池袋", "豊島区", "東京都豊島区南池袋一丁目", "06:54", "07:57", 63, 1,
     "JR山手線 → JR常磐線",
     "山手線|埼京線|湘南新宿ライン|東上線|池袋線|丸ノ内線|有楽町線|副都心線"),
    ("恵比寿", "渋谷区", "東京都渋谷区恵比寿南一丁目", "06:52", "07:57", 65, 1,
     "JR山手線 → JR常磐線", "山手線|埼京線|湘南新宿ライン|日比谷線"),
]


# ============================================================
# 3. データ加工用の関数
# ============================================================
def time_minutes(text):
    """時刻を並べ替え用の分数に変換する。"""
    time = datetime.strptime(text, "%H:%M")
    return time.hour * 60 + time.minute


def time_band(minutes):
    """所要時間を10分単位の時間圏に分類する。"""
    if minutes <= 10:
        return "10分圏内"
    if minutes <= 20:
        return "20分圏内"
    if minutes <= 30:
        return "30分圏内"
    if minutes <= 40:
        return "40分圏内"
    if minutes <= 50:
        return "50分圏内"
    if minutes <= 60:
        return "60分圏内"
    return "60分超"


def station_font_size(line_count):
    """路線数が多い駅ほど駅名を大きくする。"""
    return min(44, 25 + line_count * 2)


def compact_html(text):
    """
    HTMLの改行と行頭空白を除去する。
    MarkdownがHTMLをコードブロックと誤認するのを防ぐ。
    """
    return " ".join(line.strip() for line in text.splitlines())


# ============================================================
# 4. 表形式へ変換し、ランキングに必要な列を追加
# ============================================================
columns = [
    "駅名", "区", "住所", "出発", "到着", "所要時間",
    "乗換回数", "経路", "路線文字列",
]

df = pd.DataFrame(STATION_DATA, columns=columns)
df["路線一覧"] = df["路線文字列"].str.split("|")
df["路線数"] = df["路線一覧"].str.len()
df["時間圏"] = df["所要時間"].apply(time_band)
df["出発分"] = df["出発"].apply(time_minutes)

# 出発時刻が遅い順。同時刻なら乗換が少ない駅を上位にする。
df = df.sort_values(
    ["出発分", "乗換回数", "所要時間"],
    ascending=[False, True, True],
).reset_index(drop=True)


# ============================================================
# 5. 画面デザイン
# ============================================================
st.markdown(
    """
    <style>
    .block-container{max-width:1120px;padding-top:2rem}
    .title{font-size:2.8rem;font-weight:900;letter-spacing:-.05em}
    .subtitle{color:#667085;margin:.4rem 0 1.4rem}
    .notice{padding:.9rem 1rem;border:1px solid #f2c94c;
        border-radius:12px;background:#fff9df;margin-bottom:1.5rem}
    .band-title{font-size:1.45rem;font-weight:850;margin:2.2rem 0 .8rem;
        border-bottom:1px solid #d0d5dd;padding-bottom:.45rem}
    .band-count{font-size:.85rem;color:#667085;font-weight:500}
    .card{border:1px solid #d0d5dd;border-radius:16px;padding:1.2rem 1.3rem;
        margin-bottom:.9rem;background:#fff;box-shadow:0 1px 3px #0000000d}
    .top{display:flex;justify-content:space-between;gap:1rem}
    .rank{font-size:.78rem;color:#667085;font-weight:750}
    .name-row{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap}
    .name{font-weight:900;line-height:1.1;letter-spacing:-.04em}
    .ward{padding:.25rem .55rem;border:1px solid #d0d5dd;
        border-radius:999px;font-size:.78rem;font-weight:700}
    .address{font-size:.88rem;color:#667085;margin-top:.4rem}
    .time-box{text-align:right;white-space:nowrap}
    .time-label{font-size:.78rem;color:#667085}
    .time{font-size:2.15rem;font-weight:900;line-height:1}
    .arrival{font-size:.82rem;color:#667085;margin-top:.3rem}
    .chips{display:flex;gap:.45rem;flex-wrap:wrap;margin-top:1rem}
    .chip{padding:.3rem .55rem;border-radius:8px;background:#f2f4f7;
        font-size:.8rem;font-weight:650}
    .route{margin-top:.8rem;font-size:.9rem}
    .lines{margin-top:.35rem;color:#667085;font-size:.8rem;line-height:1.6}
    .empty{padding:2rem;text-align:center;border:1px dashed #98a2b3;
        border-radius:14px;color:#667085}
    @media(max-width:700px){
        .title{font-size:2rem}.top{display:block}
        .time-box{text-align:left;margin-top:1rem}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 6. タイトルと注意書き
# ============================================================
st.markdown(
    compact_html(
        """
        <div class="title">松戸駅に8時までに着くには？</div>
        <div class="subtitle">
            各駅から最も遅く出発できる時刻をランキング表示
        </div>
        <div class="notice">
            <strong>現在は画面確認用の仮データです。</strong>
            時刻・経路・住所は今後、正式なデータへ置き換えます。
        </div>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# 7. 左側の絞り込みメニュー
# ============================================================
all_bands = [
    "10分圏内", "20分圏内", "30分圏内", "40分圏内",
    "50分圏内", "60分圏内", "60分超",
]

with st.sidebar:
    st.header("表示条件")

    selected_bands = st.multiselect(
        "所要時間",
        all_bands,
        default=all_bands,
    )

    max_transfers = st.slider(
        "許容する乗換回数",
        min_value=0,
        max_value=2,
        value=2,
    )

    wards = sorted(df["区"].unique())
    selected_wards = st.multiselect(
        "東京都の区",
        wards,
        default=wards,
    )

    keyword = st.text_input(
        "駅名検索",
        placeholder="例：新橋、上野",
    )

    st.caption("駅名は、乗り入れ路線が多いほど大きく表示されます。")


# ============================================================
# 8. 選択された条件でデータを絞り込む
# ============================================================
filtered = df[
    df["時間圏"].isin(selected_bands)
    & (df["乗換回数"] <= max_transfers)
    & df["区"].isin(selected_wards)
].copy()

if keyword.strip():
    filtered = filtered[
        filtered["駅名"].str.contains(keyword.strip(), na=False)
    ]

filtered = filtered.reset_index(drop=True)
filtered["表示順位"] = filtered.index + 1


# ============================================================
# 9. 絞り込み結果の概要
# ============================================================
col1, col2, col3 = st.columns(3)

col1.metric("表示中", f"{len(filtered)}駅")
col2.metric(
    "最も遅い出発",
    filtered.iloc[0]["出発"] if len(filtered) else "—",
)
col3.metric(
    "乗換なし",
    f"{int((filtered['乗換回数'] == 0).sum())}駅",
)


# ============================================================
# 10. 時間圏ごとに駅カードを表示
# ============================================================
if filtered.empty:
    st.markdown(
        '<div class="empty">条件に一致する駅がありません。</div>',
        unsafe_allow_html=True,
    )

for band in all_bands:
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
        ward = escape(row["区"])
        address = escape(row["住所"])
        route = escape(row["経路"])
        lines = " ／ ".join(escape(x) for x in row["路線一覧"])
        transfer = "乗換なし" if row["乗換回数"] == 0 \
            else f"乗換{row['乗換回数']}回"
        font_size = station_font_size(row["路線数"])

        # HTMLを作り、compact_htmlで1行化してから表示する。
        card = f"""
        <div class="card">
            <div class="top">
                <div>
                    <div class="rank">RANK {row["表示順位"]}</div>
                    <div class="name-row">
                        <div class="name" style="font-size:{font_size}px">
                            {station}<span style="font-size:16px">駅</span>
                        </div>
                        <span class="ward">東京都 {ward}</span>
                    </div>
                    <div class="address">{address}</div>
                </div>
                <div class="time-box">
                    <div class="time-label">最終出発時刻</div>
                    <div class="time">{row["出発"]}</div>
                    <div class="arrival">松戸 {row["到着"]}着</div>
                </div>
            </div>
            <div class="chips">
                <span class="chip">所要 {row["所要時間"]}分</span>
                <span class="chip">{transfer}</span>
                <span class="chip">{row["路線数"]}路線</span>
                <span class="chip">{row["時間圏"]}</span>
            </div>
            <div class="route"><strong>経路：</strong>{route}</div>
            <div class="lines"><strong>乗り入れ：</strong>{lines}</div>
        </div>
        """

        st.markdown(
            compact_html(card),
            unsafe_allow_html=True,
        )


# ============================================================
# 11. 元データを表で確認・CSV保存
# ============================================================
with st.expander("仮データを表で確認する"):
    output_columns = [
        "駅名", "区", "住所", "出発", "到着", "所要時間",
        "時間圏", "乗換回数", "経路", "路線数",
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
# 12. ページ最下部
# ============================================================
st.caption(
    "Matsudo 8:00 prototype｜現在の時刻・経路は画面確認用の仮データです。"
)
