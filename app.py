from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st


# =========================================================
# ページ設定
# =========================================================
st.set_page_config(
    page_title="松戸8時｜逆算通勤ランキング",
    page_icon="🚃",
    layout="wide",
)


# =========================================================
# 仮データ
# 注意：
# 現在は画面と並び順を確認するための仮データです。
# 実際の時刻・経路・住所は、後ほど経路検索APIなどに置き換えます。
# =========================================================
STATIONS = [
    {
        "station": "北千住",
        "prefecture": "東京都",
        "municipality": "足立区",
        "address": "東京都足立区千住旭町",
        "departure": "07:42",
        "arrival": "07:55",
        "duration": 13,
        "transfers": 0,
        "route": "JR常磐線",
        "line_count": 5,
        "lines": [
            "JR常磐線",
            "東京メトロ千代田線",
            "東京メトロ日比谷線",
            "東武スカイツリーライン",
            "つくばエクスプレス",
        ],
    },
    {
        "station": "日暮里",
        "prefecture": "東京都",
        "municipality": "荒川区",
        "address": "東京都荒川区西日暮里二丁目",
        "departure": "07:36",
        "arrival": "07:57",
        "duration": 21,
        "transfers": 0,
        "route": "JR常磐線",
        "line_count": 6,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR常磐線",
            "京成本線",
            "成田スカイアクセス線",
            "日暮里・舎人ライナー",
        ],
    },
    {
        "station": "上野",
        "prefecture": "東京都",
        "municipality": "台東区",
        "address": "東京都台東区上野七丁目",
        "departure": "07:34",
        "arrival": "07:57",
        "duration": 23,
        "transfers": 0,
        "route": "JR常磐線",
        "line_count": 8,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR宇都宮線",
            "JR高崎線",
            "JR常磐線",
            "東北・北海道新幹線",
            "東京メトロ銀座線",
            "東京メトロ日比谷線",
        ],
    },
    {
        "station": "西日暮里",
        "prefecture": "東京都",
        "municipality": "荒川区",
        "address": "東京都荒川区西日暮里五丁目",
        "departure": "07:32",
        "arrival": "07:57",
        "duration": 25,
        "transfers": 1,
        "route": "東京メトロ千代田線 → JR常磐線",
        "line_count": 4,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "東京メトロ千代田線",
            "日暮里・舎人ライナー",
        ],
    },
    {
        "station": "秋葉原",
        "prefecture": "東京都",
        "municipality": "千代田区",
        "address": "東京都千代田区外神田一丁目",
        "departure": "07:27",
        "arrival": "07:57",
        "duration": 30,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 5,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR中央・総武線",
            "東京メトロ日比谷線",
            "つくばエクスプレス",
        ],
    },
    {
        "station": "東京",
        "prefecture": "東京都",
        "municipality": "千代田区",
        "address": "東京都千代田区丸の内一丁目",
        "departure": "07:24",
        "arrival": "07:57",
        "duration": 33,
        "transfers": 0,
        "route": "JR上野東京ライン・常磐線直通",
        "line_count": 10,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR中央線",
            "JR東海道線",
            "JR宇都宮線",
            "JR高崎線",
            "JR横須賀線",
            "JR京葉線",
            "各新幹線",
            "東京メトロ丸ノ内線",
        ],
    },
    {
        "station": "神田",
        "prefecture": "東京都",
        "municipality": "千代田区",
        "address": "東京都千代田区鍛冶町二丁目",
        "departure": "07:23",
        "arrival": "07:57",
        "duration": 34,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 4,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR中央線",
            "東京メトロ銀座線",
        ],
    },
    {
        "station": "新橋",
        "prefecture": "東京都",
        "municipality": "港区",
        "address": "東京都港区新橋二丁目",
        "departure": "07:19",
        "arrival": "07:57",
        "duration": 38,
        "transfers": 0,
        "route": "JR上野東京ライン・常磐線直通",
        "line_count": 6,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR東海道線",
            "JR横須賀線",
            "東京メトロ銀座線",
            "都営浅草線",
        ],
    },
    {
        "station": "御茶ノ水",
        "prefecture": "東京都",
        "municipality": "千代田区",
        "address": "東京都千代田区神田駿河台二丁目",
        "departure": "07:18",
        "arrival": "07:57",
        "duration": 39,
        "transfers": 1,
        "route": "JR中央・総武線 → JR常磐線",
        "line_count": 3,
        "lines": [
            "JR中央線",
            "JR中央・総武線",
            "東京メトロ丸ノ内線",
        ],
    },
    {
        "station": "浜松町",
        "prefecture": "東京都",
        "municipality": "港区",
        "address": "東京都港区海岸一丁目",
        "departure": "07:15",
        "arrival": "07:57",
        "duration": 42,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 4,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "東京モノレール",
            "都営浅草線・大江戸線（大門駅）",
        ],
    },
    {
        "station": "日本橋",
        "prefecture": "東京都",
        "municipality": "中央区",
        "address": "東京都中央区日本橋一丁目",
        "departure": "07:14",
        "arrival": "07:57",
        "duration": 43,
        "transfers": 1,
        "route": "東京メトロ銀座線 → JR常磐線",
        "line_count": 3,
        "lines": [
            "東京メトロ銀座線",
            "東京メトロ東西線",
            "都営浅草線",
        ],
    },
    {
        "station": "品川",
        "prefecture": "東京都",
        "municipality": "港区",
        "address": "東京都港区高輪三丁目",
        "departure": "07:11",
        "arrival": "07:57",
        "duration": 46,
        "transfers": 0,
        "route": "JR上野東京ライン・常磐線直通",
        "line_count": 7,
        "lines": [
            "JR山手線",
            "JR京浜東北線",
            "JR東海道線",
            "JR横須賀線",
            "東海道新幹線",
            "京急本線",
            "成田方面特急",
        ],
    },
    {
        "station": "銀座",
        "prefecture": "東京都",
        "municipality": "中央区",
        "address": "東京都中央区銀座四丁目",
        "departure": "07:10",
        "arrival": "07:57",
        "duration": 47,
        "transfers": 1,
        "route": "東京メトロ銀座線 → JR常磐線",
        "line_count": 3,
        "lines": [
            "東京メトロ銀座線",
            "東京メトロ丸ノ内線",
            "東京メトロ日比谷線",
        ],
    },
    {
        "station": "大手町",
        "prefecture": "東京都",
        "municipality": "千代田区",
        "address": "東京都千代田区大手町一丁目",
        "departure": "07:09",
        "arrival": "07:57",
        "duration": 48,
        "transfers": 1,
        "route": "東京メトロ千代田線 → JR常磐線",
        "line_count": 5,
        "lines": [
            "東京メトロ丸ノ内線",
            "東京メトロ東西線",
            "東京メトロ千代田線",
            "東京メトロ半蔵門線",
            "都営三田線",
        ],
    },
    {
        "station": "飯田橋",
        "prefecture": "東京都",
        "municipality": "千代田区",
        "address": "東京都千代田区飯田橋四丁目",
        "departure": "07:08",
        "arrival": "07:57",
        "duration": 49,
        "transfers": 1,
        "route": "JR中央・総武線 → JR常磐線",
        "line_count": 5,
        "lines": [
            "JR中央・総武線",
            "東京メトロ東西線",
            "東京メトロ有楽町線",
            "東京メトロ南北線",
            "都営大江戸線",
        ],
    },
    {
        "station": "六本木",
        "prefecture": "東京都",
        "municipality": "港区",
        "address": "東京都港区六本木六丁目",
        "departure": "07:03",
        "arrival": "07:57",
        "duration": 54,
        "transfers": 2,
        "route": "東京メトロ日比谷線 → JR線 → JR常磐線",
        "line_count": 2,
        "lines": [
            "東京メトロ日比谷線",
            "都営大江戸線",
        ],
    },
    {
        "station": "新宿",
        "prefecture": "東京都",
        "municipality": "新宿区",
        "address": "東京都新宿区新宿三丁目",
        "departure": "07:01",
        "arrival": "07:57",
        "duration": 56,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 11,
        "lines": [
            "JR山手線",
            "JR中央線",
            "JR中央・総武線",
            "JR埼京線",
            "JR湘南新宿ライン",
            "小田急線",
            "京王線",
            "東京メトロ丸ノ内線",
            "都営新宿線",
            "都営大江戸線",
            "西武新宿線周辺",
        ],
    },
    {
        "station": "渋谷",
        "prefecture": "東京都",
        "municipality": "渋谷区",
        "address": "東京都渋谷区道玄坂一丁目",
        "departure": "06:55",
        "arrival": "07:57",
        "duration": 62,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 9,
        "lines": [
            "JR山手線",
            "JR埼京線",
            "JR湘南新宿ライン",
            "東急東横線",
            "東急田園都市線",
            "京王井の頭線",
            "東京メトロ銀座線",
            "東京メトロ半蔵門線",
            "東京メトロ副都心線",
        ],
    },
    {
        "station": "池袋",
        "prefecture": "東京都",
        "municipality": "豊島区",
        "address": "東京都豊島区南池袋一丁目",
        "departure": "06:54",
        "arrival": "07:57",
        "duration": 63,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 8,
        "lines": [
            "JR山手線",
            "JR埼京線",
            "JR湘南新宿ライン",
            "東武東上線",
            "西武池袋線",
            "東京メトロ丸ノ内線",
            "東京メトロ有楽町線",
            "東京メトロ副都心線",
        ],
    },
    {
        "station": "恵比寿",
        "prefecture": "東京都",
        "municipality": "渋谷区",
        "address": "東京都渋谷区恵比寿南一丁目",
        "departure": "06:52",
        "arrival": "07:57",
        "duration": 65,
        "transfers": 1,
        "route": "JR山手線 → JR常磐線",
        "line_count": 4,
        "lines": [
            "JR山手線",
            "JR埼京線",
            "JR湘南新宿ライン",
            "東京メトロ日比谷線",
        ],
    },
]


# =========================================================
# 補助関数
# =========================================================
def time_to_minutes(time_text: str) -> int:
    """HH:MM形式を、0時からの経過分へ変換する。"""
    parsed = datetime.strptime(time_text, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def get_time_band(duration: int) -> str:
    """
    所要時間を10分単位の圏内に分類する。
    例：13分 → 20分圏内
    """
    if duration <= 10:
        return "10分圏内"
    if duration <= 20:
        return "20分圏内"
    if duration <= 30:
        return "30分圏内"
    if duration <= 40:
        return "40分圏内"
    if duration <= 50:
        return "50分圏内"
    if duration <= 60:
        return "60分圏内"
    return "60分超"


def get_band_order(band: str) -> int:
    order = {
        "10分圏内": 10,
        "20分圏内": 20,
        "30分圏内": 30,
        "40分圏内": 40,
        "50分圏内": 50,
        "60分圏内": 60,
        "60分超": 999,
    }
    return order.get(band, 999)


def get_station_font_size(line_count: int) -> int:
    """
    乗り入れ路線数に応じて駅名の文字サイズを変更する。
    最小25px、最大43px。
    """
    return max(25, min(43, 23 + line_count * 2))


def get_transfer_text(transfers: int) -> str:
    if transfers == 0:
        return "乗換なし"
    return f"乗換{transfers}回"


def get_band_class(band: str) -> str:
    mapping = {
        "10分圏内": "band-10",
        "20分圏内": "band-20",
        "30分圏内": "band-30",
        "40分圏内": "band-40",
        "50分圏内": "band-50",
        "60分圏内": "band-60",
        "60分超": "band-over",
    }
    return mapping.get(band, "band-over")


# =========================================================
# DataFrame作成・ランキング計算
# =========================================================
df = pd.DataFrame(STATIONS)

df["departure_minutes"] = df["departure"].apply(time_to_minutes)
df["time_band"] = df["duration"].apply(get_time_band)
df["band_order"] = df["time_band"].apply(get_band_order)

# 出発時刻が遅い順
df = df.sort_values(
    by=["departure_minutes", "transfers", "duration"],
    ascending=[False, True, True],
).reset_index(drop=True)

df["rank"] = df.index + 1


# =========================================================
# CSS
# =========================================================
st.markdown(
    """
    <style>
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        .main-title {
            font-size: 3rem;
            font-weight: 850;
            line-height: 1.15;
            letter-spacing: -0.04em;
            margin-bottom: 0.3rem;
        }

        .main-subtitle {
            color: #667085;
            font-size: 1.05rem;
            margin-bottom: 1.5rem;
        }

        .notice-box {
            border: 1px solid #f2c94c;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            background: rgba(242, 201, 76, 0.10);
            margin-bottom: 1.5rem;
            line-height: 1.65;
        }

        .summary-box {
            border: 1px solid rgba(120, 120, 120, 0.22);
            border-radius: 14px;
            padding: 1rem 1.1rem;
            background: rgba(127, 127, 127, 0.04);
            height: 100%;
        }

        .summary-label {
            color: #667085;
            font-size: 0.8rem;
            margin-bottom: 0.25rem;
        }

        .summary-value {
            font-size: 1.45rem;
            font-weight: 800;
        }

        .band-heading {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            margin-top: 2.2rem;
            margin-bottom: 0.8rem;
        }

        .band-heading-line {
            flex: 1;
            height: 1px;
            background: rgba(120, 120, 120, 0.25);
        }

        .band-heading-text {
            font-size: 1.35rem;
            font-weight: 800;
            white-space: nowrap;
        }

        .band-heading-count {
            color: #667085;
            font-size: 0.9rem;
            font-weight: 500;
        }

        .station-card {
            position: relative;
            border: 1px solid rgba(120, 120, 120, 0.22);
            border-radius: 17px;
            padding: 1.2rem 1.35rem;
            margin-bottom: 0.85rem;
            background: rgba(127, 127, 127, 0.025);
            overflow: hidden;
        }

        .station-card:hover {
            border-color: rgba(80, 80, 80, 0.45);
            transform: translateY(-1px);
            transition: 0.15s ease-in-out;
        }

        .station-card::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 7px;
        }

        .band-10::before {
            background: #1570ef;
        }

        .band-20::before {
            background: #12b76a;
        }

        .band-30::before {
            background: #84cc16;
        }

        .band-40::before {
            background: #f79009;
        }

        .band-50::before {
            background: #f04438;
        }

        .band-60::before {
            background: #7a5af8;
        }

        .band-over::before {
            background: #667085;
        }

        .station-top-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1.5rem;
        }

        .station-main {
            min-width: 0;
            flex: 1;
        }

        .rank-label {
            color: #667085;
            font-size: 0.85rem;
            font-weight: 650;
            margin-bottom: 0.2rem;
        }

        .station-name-row {
            display: flex;
            align-items: baseline;
            gap: 0.75rem;
            flex-wrap: wrap;
        }

        .station-name {
            font-weight: 900;
            line-height: 1.05;
            letter-spacing: -0.035em;
        }

        .station-suffix {
            font-size: 1rem;
            font-weight: 750;
        }

        .municipality-badge {
            display: inline-block;
            padding: 0.25rem 0.55rem;
            border: 1px solid rgba(120, 120, 120, 0.26);
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
        }

        .address {
            color: #667085;
            font-size: 0.9rem;
            margin-top: 0.45rem;
        }

        .departure-box {
            text-align: right;
            flex-shrink: 0;
        }

        .departure-label {
            color: #667085;
            font-size: 0.8rem;
            margin-bottom: 0.05rem;
        }

        .departure-time {
            font-size: 2.25rem;
            line-height: 1;
            font-weight: 900;
            letter-spacing: -0.04em;
        }

        .arrival-time {
            color: #667085;
            font-size: 0.86rem;
            margin-top: 0.3rem;
        }

        .station-details {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin-top: 1rem;
        }

        .detail-chip {
            display: inline-block;
            border-radius: 8px;
            padding: 0.33rem 0.55rem;
            background: rgba(127, 127, 127, 0.09);
            font-size: 0.82rem;
            font-weight: 650;
        }

        .route-text {
            margin-top: 0.85rem;
            font-size: 0.92rem;
            line-height: 1.6;
        }

        .line-list {
            color: #667085;
            font-size: 0.82rem;
            line-height: 1.6;
            margin-top: 0.35rem;
        }

        .empty-box {
            border: 1px dashed rgba(120, 120, 120, 0.35);
            border-radius: 14px;
            padding: 2rem;
            text-align: center;
            color: #667085;
        }

        @media (max-width: 700px) {
            .main-title {
                font-size: 2.15rem;
            }

            .station-top-row {
                display: block;
            }

            .departure-box {
                text-align: left;
                margin-top: 1rem;
            }

            .departure-time {
                font-size: 1.9rem;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# ヘッダー
# =========================================================
st.markdown(
    """
    <div class="main-title">松戸駅に8時までに着くには？</div>
    <div class="main-subtitle">
        各駅から松戸駅へ向かう場合の「最も遅く出発できる時刻」をランキング表示
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="notice-box">
        <strong>現在は画面確認用の仮データです。</strong><br>
        出発時刻、到着時刻、経路、駅住所はまだ正式な交通データと接続していません。
        実際の利用前に、経路検索API等の情報へ置き換えます。
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# サイドバー・フィルター
# =========================================================
with st.sidebar:
    st.header("表示条件")

    selected_bands = st.multiselect(
        "所要時間",
        options=[
            "10分圏内",
            "20分圏内",
            "30分圏内",
            "40分圏内",
            "50分圏内",
            "60分圏内",
            "60分超",
        ],
        default=[
            "10分圏内",
            "20分圏内",
            "30分圏内",
            "40分圏内",
            "50分圏内",
            "60分圏内",
            "60分超",
        ],
    )

    max_transfers = st.slider(
        "許容する乗換回数",
        min_value=0,
        max_value=2,
        value=2,
        step=1,
    )

    selected_municipalities = st.multiselect(
        "東京都の区",
        options=sorted(df["municipality"].unique().tolist()),
        default=sorted(df["municipality"].unique().tolist()),
    )

    station_query = st.text_input(
        "駅名検索",
        placeholder="例：新橋、上野",
    )

    st.divider()

    st.caption(
        "駅名の大きさは、仮データ上の乗り入れ路線数に応じて変化します。"
    )


# =========================================================
# フィルター適用
# =========================================================
filtered_df = df[
    (df["time_band"].isin(selected_bands))
    & (df["transfers"] <= max_transfers)
    & (df["municipality"].isin(selected_municipalities))
].copy()

if station_query.strip():
    filtered_df = filtered_df[
        filtered_df["station"].str.contains(
            station_query.strip(),
            case=False,
            na=False,
        )
    ]

filtered_df = filtered_df.sort_values(
    by=["departure_minutes", "transfers", "duration"],
    ascending=[False, True, True],
).reset_index(drop=True)

# フィルター後も順位を振り直す
filtered_df["display_rank"] = filtered_df.index + 1


# =========================================================
# サマリー
# =========================================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-label">表示中の駅</div>
            <div class="summary-value">{len(filtered_df)}駅</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    latest_departure = (
        filtered_df.iloc[0]["departure"]
        if not filtered_df.empty
        else "—"
    )
    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-label">最も遅い出発</div>
            <div class="summary-value">{latest_departure}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    direct_count = int((filtered_df["transfers"] == 0).sum())
    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-label">乗換なし</div>
            <div class="summary-value">{direct_count}駅</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    median_duration = (
        f"{int(filtered_df['duration'].median())}分"
        if not filtered_df.empty
        else "—"
    )
    st.markdown(
        f"""
        <div class="summary-box">
            <div class="summary-label">所要時間中央値</div>
            <div class="summary-value">{median_duration}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 駅カード表示
# =========================================================
if filtered_df.empty:
    st.markdown(
        """
        <div class="empty-box">
            条件に一致する駅がありません。<br>
            左側の条件を変更してください。
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    bands_in_data = sorted(
        filtered_df["time_band"].unique(),
        key=get_band_order,
    )

    for band in bands_in_data:
        band_df = filtered_df[
            filtered_df["time_band"] == band
        ].copy()

        st.markdown(
            f"""
            <div class="band-heading">
                <div class="band-heading-text">
                    {escape(band)}
                    <span class="band-heading-count">
                        {len(band_df)}駅
                    </span>
                </div>
                <div class="band-heading-line"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for _, row in band_df.iterrows():
            font_size = get_station_font_size(int(row["line_count"]))
            card_class = get_band_class(row["time_band"])

            station_name = escape(str(row["station"]))
            municipality = escape(str(row["municipality"]))
            address = escape(str(row["address"]))
            departure = escape(str(row["departure"]))
            arrival = escape(str(row["arrival"]))
            route = escape(str(row["route"]))
            transfer_text = escape(
                get_transfer_text(int(row["transfers"]))
            )
            line_count = int(row["line_count"])
            duration = int(row["duration"])
            rank = int(row["display_rank"])

            lines_text = " ／ ".join(
                escape(str(line)) for line in row["lines"]
            )

            st.markdown(
                f"""
                <div class="station-card {card_class}">
                    <div class="station-top-row">
                        <div class="station-main">
                            <div class="rank-label">
                                RANK {rank}
                            </div>

                            <div class="station-name-row">
                                <div
                                    class="station-name"
                                    style="font-size: {font_size}px;"
                                >
                                    {station_name}
                                    <span class="station-suffix">駅</span>
                                </div>

                                <span class="municipality-badge">
                                    東京都 {municipality}
                                </span>
                            </div>

                            <div class="address">
                                {address}
                            </div>
                        </div>

                        <div class="departure-box">
                            <div class="departure-label">
                                最終出発時刻
                            </div>
                            <div class="departure-time">
                                {departure}
                            </div>
                            <div class="arrival-time">
                                松戸 {arrival}着
                            </div>
                        </div>
                    </div>

                    <div class="station-details">
                        <span class="detail-chip">
                            所要 {duration}分
                        </span>
                        <span class="detail-chip">
                            {transfer_text}
                        </span>
                        <span class="detail-chip">
                            {line_count}路線
                        </span>
                        <span class="detail-chip">
                            {escape(str(row["time_band"]))}
                        </span>
                    </div>

                    <div class="route-text">
                        <strong>経路：</strong>{route}
                    </div>

                    <div class="line-list">
                        <strong>乗り入れ：</strong>{lines_text}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# =========================================================
# データ一覧・ダウンロード
# =========================================================
st.divider()

with st.expander("仮データを表で確認する"):
    display_columns = [
        "rank",
        "station",
        "municipality",
        "address",
        "departure",
        "arrival",
        "duration",
        "time_band",
        "transfers",
        "route",
        "line_count",
    ]

    display_df = df[display_columns].rename(
        columns={
            "rank": "順位",
            "station": "駅",
            "municipality": "区",
            "address": "住所",
            "departure": "出発",
            "arrival": "松戸到着",
            "duration": "所要時間（分）",
            "time_band": "時間圏",
            "transfers": "乗換回数",
            "route": "経路",
            "line_count": "路線数",
        }
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    csv_data = display_df.to_csv(
        index=False,
    ).encode("utf-8-sig")

    st.download_button(
        label="仮データをCSVで保存",
        data=csv_data,
        file_name="matsudo_8am_sample.csv",
        mime="text/csv",
    )


# =========================================================
# フッター
# =========================================================
st.caption(
    "Matsudo 8:00 prototype｜時刻・経路・住所は現在すべて試作確認用です。"
)
