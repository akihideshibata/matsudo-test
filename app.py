import json
from pathlib import Path
import streamlit as st

# 保存済みの発車時刻を表示
data = json.loads(Path("departures.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="新橋駅 発車時刻", page_icon="🚇")
st.title(f'{data["station"]}駅 朝の発車時刻')
st.caption(f'データ取得：{data["fetched_at"]}')

for time in data["departures"]:
    with st.container(border=True):
        st.markdown(f"## {time}")

st.divider()
st.caption(
    "東京都交通局が公共交通オープンデータセンターを通じて提供する"
    "GTFSデータを加工して利用しています（CC BY 4.0）。"
)
