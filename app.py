import streamlit as st

st.set_page_config(
    page_title="松戸8時テスト",
    page_icon="🚃",
)

st.title("松戸8時テスト")

st.write("これは初めて公開したWebアプリです。")

station = st.selectbox(
    "出発駅を選んでください",
    ["東京", "新橋", "上野", "浜松町"],
)

sample_times = {
    "東京": "7:20",
    "新橋": "7:17",
    "上野": "7:35",
    "浜松町": "7:14",
}

if st.button("調べる"):
    st.success(
        f"{station}駅を {sample_times[station]} ごろ出発すると、"
        "松戸駅に8時までに到着する想定です。"
    )
