import json
from pathlib import Path
import streamlit as st

data = json.loads(Path("direct_routes.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="新橋8時・直通版", page_icon="🚇", layout="wide")
st.title("新橋駅に8時までに着くには？")
st.caption(
    f'対象日：{data["service_date"]}｜乗換なしのみ｜'
    f'GTFS取得：{data["gtfs_fetched_at"]}'
)

query = st.text_input("駅名で絞り込み", placeholder="例：浅草")
rows = [x for x in data["routes"] if query in x["station"]]

for x in rows:
    with st.container(border=True):
        a, b, c = st.columns([2, 2, 4])
        a.subheader(f'{x["station"]}駅')
        b.markdown(f'## {x["departure"]}発')
        b.caption(f'新橋 {x["arrival"]}着')
        c.markdown(f'**{x["route"]}・乗換なし**')
        c.write(f'{x["destination"]}方面')
        c.caption(f'乗車時間 約{x["minutes"]}分')

st.divider()
st.caption(
    "東京都交通局が公共交通オープンデータセンターを通じて提供する"
    "GTFSデータを加工して利用しています（CC BY 4.0）。"
)
st.caption(
    "正確性・完全性は保証されません。表示内容について交通事業者へ"
    "直接問い合わせないでください。"
)
