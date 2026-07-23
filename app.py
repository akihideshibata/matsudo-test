import json
from pathlib import Path
import streamlit as st

# 保存済みJSONだけを読み、閲覧時には交通APIを呼ばない
data = json.loads(Path("routes.json").read_text())
st.set_page_config(page_title="松戸8時", page_icon="🚃", layout="wide")
st.title("松戸駅に8時までに着くには？")
st.caption(f'検索日：{data["searched_date"]}｜{data["version"]}')

for x in data["routes"]:
    transfer = "乗換なし" if not x["transfers"] else \
        f'{"・".join(x["transfer_stations"])}で乗換'
    with st.container(border=True):
        a, b, c = st.columns([2, 2, 3])
        a.subheader(f'{x["station"]}駅')
        b.markdown(f'## {x["departure"]}発')
        b.caption(f'松戸 {x["arrival"]}着')
        c.markdown(f'**{transfer}**')
        c.write(" → ".join(x["route"]))
        c.caption(f'所要 {x["minutes"]}分')
