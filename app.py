import json
from pathlib import Path
import streamlit as st

# 自動生成された時刻表を読み込む
data = json.loads(Path("departures.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="新橋駅 朝の時刻表", page_icon="🚇", layout="wide")
st.title(f'{data["station"]}駅 朝の発車時刻')
st.caption(f'対象日：{data["service_date"]}｜取得日時：{data["fetched_at"]}')

# 時間帯を選択
hours = sorted({x["time"][:2] for x in data["departures"]})
hour = st.segmented_control("時間帯", hours, default=hours[0])
rows = [x for x in data["departures"] if x["time"].startswith(hour)]

for x in rows:
    with st.container(border=True):
        a, b = st.columns([1, 4])
        a.markdown(f'## {x["time"]}')
        b.markdown(f'**{x["route"]}**')
        b.caption(f'{x["destination"]}方面')

st.divider()
st.caption(
    "東京都交通局が公共交通オープンデータセンターを通じて提供する"
    "GTFSデータを加工して利用しています（CC BY 4.0）。"
)
st.caption(
    "表示内容の正確性・完全性は保証されません。"
    "表示内容について交通事業者へ直接問い合わせないでください。"
)
