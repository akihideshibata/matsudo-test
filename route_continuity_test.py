import argparse, gzip, heapq, json
from collections import defaultdict
from itertools import count
from pathlib import Path


# ============================================================
# 1. データ読込・正規化
# ============================================================
def minute(value):
    """GTFSの24時超表記を含む時刻を分へ変換する。"""
    hour, minutes = map(int, str(value).split(":")[:2])
    return hour * 60 + minutes


def clock(value):
    return f"{value // 60:02d}:{value % 60:02d}"


def load_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as file:
            return json.load(file)
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_trips(raw_trips):
    """現在のJSONと将来メタデータを追加したJSONの両方を扱う。"""
    trips = []
    for no, raw in enumerate(raw_trips):
        stops = []
        for sequence, stop in enumerate(raw.get("stops", [])):
            if not stop or len(stop) < 2 or not stop[0]:
                continue
            arrival = stop[1] if len(stop) > 1 and stop[1] else None
            departure = stop[2] if len(stop) > 2 and stop[2] else None
            if not arrival and not departure:
                continue
            try:
                arrival_minute = minute(arrival or departure)
                departure_minute = minute(departure or arrival)
            except (TypeError, ValueError):
                continue
            stops.append({"name": stop[0], "arrival": arrival_minute,
                          "departure": departure_minute, "sequence": sequence})
        if len(stops) < 2:
            continue
        trips.append({
            "id": str(raw.get("trip_id") or raw.get("id") or f"trip_{no}"),
            "route": str(raw.get("route", "路線情報なし")),
            "operator": str(raw.get("operator", "")),
            "headsign": str(raw.get("destination") or raw.get("trip_headsign") or ""),
            "direction": raw.get("direction_id"),
            "block": raw.get("block_id"),
            "stops": stops,
        })
    return trips


def load_timetable(directory=".", day="weekday"):
    """アプリと同じ2つの生成済みJSONから指定曜日を読む。"""
    directory = Path(directory)
    names = ("direct_timetable_basic.json.gz", "direct_timetable_challenge.json.gz")
    files, raw_trips = [], []
    for name in names:
        path = directory / name
        if path.exists():
            files.append(str(path))
            raw_trips.extend(load_json(path).get("timetables", {}).get(day, []))
    return normalize_trips(raw_trips), files


# ============================================================
# 2. trip連結検索
# ============================================================
def compatible(previous, following, gap, require_block=False):
    """同じ車両と断定できるか、時刻上の継続候補かを判定する。"""
    if previous["route"] != following["route"]:
        return None
    if previous["operator"] and following["operator"] and previous["operator"] != following["operator"]:
        return None
    if previous["block"] not in (None, "") and following["block"] not in (None, ""):
        return "block_id一致" if previous["block"] == following["block"] else None
    if require_block:
        return None
    if previous["direction"] not in (None, "") and following["direction"] not in (None, "") \
            and previous["direction"] != following["direction"]:
        return None
    return f"推定接続（待機{gap}分）"


def find_best_path(trips, route, origin, destination, max_gap=5, max_boundaries=0,
                   require_block=False):
    """同一路線内で、同一tripまたは終端で連結した最短の実時刻経路を探す。"""
    route_trips = [(no, trip) for no, trip in enumerate(trips) if trip["route"] == route]
    starts, first_stop_index = [], defaultdict(list)
    for no, trip in route_trips:
        first = trip["stops"][0]
        first_stop_index[(trip["route"], first["name"])].append((no, trip))
        for stop_no, stop in enumerate(trip["stops"][:-1]):
            if stop["name"] == origin:
                starts.append((no, trip, stop_no, stop["departure"]))

    serial, queue, best = count(), [], None
    for trip_no, trip, stop_no, start_minute in starts:
        heapq.heappush(queue, (0, next(serial), trip_no, stop_no, 0, start_minute,
                               (), (), (trip["id"],)))
    visited = set()
    while queue:
        elapsed, _, trip_no, entry_no, boundaries, start_minute, segments, joins, used = heapq.heappop(queue)
        state = (trip_no, entry_no, boundaries, start_minute)
        if state in visited:
            continue
        visited.add(state)
        trip, entry = trips[trip_no], trips[trip_no]["stops"][entry_no]

        for stop in trip["stops"][entry_no + 1:]:
            if stop["name"] != destination:
                continue
            total = stop["arrival"] - start_minute
            if total <= 0:
                continue
            final_segment = {"trip_id": trip["id"], "route": trip["route"],
                "headsign": trip["headsign"], "from": entry["name"], "to": stop["name"],
                "departure": clock(entry["departure"]), "arrival": clock(stop["arrival"])}
            candidate = {"minutes": total, "boundaries": boundaries,
                         "segments": list(segments) + [final_segment], "joins": list(joins)}
            if best is None or (total, boundaries) < (best["minutes"], best["boundaries"]):
                best = candidate
            break

        if boundaries >= max_boundaries:
            continue
        terminal = trip["stops"][-1]
        segment = {"trip_id": trip["id"], "route": trip["route"],
            "headsign": trip["headsign"], "from": entry["name"], "to": terminal["name"],
            "departure": clock(entry["departure"]), "arrival": clock(terminal["arrival"])}
        key = (trip["route"], terminal["name"])
        for next_no, following in first_stop_index.get(key, []):
            if following["id"] in used:
                continue
            next_departure = following["stops"][0]["departure"]
            gap = next_departure - terminal["arrival"]
            if not 0 <= gap <= max_gap:
                continue
            kind = compatible(trip, following, gap, require_block)
            if not kind:
                continue
            new_elapsed = next_departure - start_minute
            heapq.heappush(queue, (new_elapsed, next(serial), next_no, 0, boundaries + 1,
                start_minute, segments + (segment,), joins + (kind,), used + (following["id"],)))
    return best


def path_rows(result):
    """画面とCLIで共通利用する見やすい行へ変換する。"""
    if not result:
        return []
    rows = []
    for no, segment in enumerate(result["segments"]):
        rows.append({"区間": no + 1, "trip_id": segment["trip_id"],
            "行先": segment["headsign"], "出発駅": segment["from"],
            "出発": segment["departure"], "到着駅": segment["to"],
            "到着": segment["arrival"],
            "次tripとの接続": result["joins"][no] if no < len(result["joins"]) else "－"})
    return rows


# ============================================================
# 3. 自己テスト
# ============================================================
def self_test():
    """trip境界をまたぐ短経路が、長い同一tripより優先されることを確認する。"""
    raw = [
        {"trip_id": "outer_a", "block_id": "loop_1", "route": "山手線", "operator": "JR",
         "destination": "大崎", "stops": [["浜松町", "10:00", "10:00"],
         ["品川", "10:07", "10:08"], ["大崎", "10:10", "10:10"]]},
        {"trip_id": "outer_b", "block_id": "loop_1", "route": "山手線", "operator": "JR",
         "destination": "池袋", "stops": [["大崎", "10:10", "10:10"],
         ["目黒", "10:13", "10:13"], ["恵比寿", "10:16", "10:16"]]},
        {"trip_id": "inner", "block_id": "loop_2", "route": "山手線", "operator": "JR",
         "destination": "大崎", "stops": [["浜松町", "10:00", "10:00"],
         ["東京", "10:08", "10:08"], ["池袋", "10:30", "10:30"],
         ["恵比寿", "10:49", "10:49"]]},
    ]
    trips = normalize_trips(raw)
    strict = find_best_path(trips, "山手線", "浜松町", "恵比寿", max_boundaries=0)
    joined = find_best_path(trips, "山手線", "浜松町", "恵比寿", max_boundaries=1,
                            require_block=True)
    assert strict and strict["minutes"] == 49, strict
    assert joined and joined["minutes"] == 16 and joined["joins"] == ["block_id一致"], joined
    print("SELF TEST: OK")
    print(f"同一tripのみ: {strict['minutes']}分 / trip連結: {joined['minutes']}分")


# ============================================================
# 4. Streamlit診断画面
# ============================================================
def run_streamlit():
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title="路線継続テスト", page_icon="🧪", layout="wide")
    st.title("路線継続テスト")
    st.caption("本番app.pyとupdate_routes.pyは変更せず、生成済み時刻表だけを診断します。")
    with st.sidebar:
        directory = st.text_input("JSONのあるフォルダ", ".")
        day = st.selectbox("曜日", ["weekday", "saturday", "sunday"],
                           format_func={"weekday": "平日", "saturday": "土曜", "sunday": "日曜"}.get)
        max_gap = st.slider("trip境界の最大待機時間", 0, 15, 5)
        max_boundaries = st.slider("連結するtrip境界数", 1, 3, 2)
        require_block = st.checkbox("block_id一致だけを許可", value=False)

    trips, files = load_timetable(directory, day)
    if not files:
        st.error("direct_timetable_basic.json.gz / challenge.json.gz が見つかりません。")
        st.code(f"streamlit run {Path(__file__).name}")
        st.stop()
    if not trips:
        st.error(f"{day}の有効な列車データがありません。")
        st.stop()
    st.success(f"{len(files)}ファイル・{len(trips):,}列車を読み込みました。")
    block_count = sum(trip["block"] not in (None, "") for trip in trips)
    direction_count = sum(trip["direction"] not in (None, "") for trip in trips)
    st.caption(f"block_idあり：{block_count:,}列車 ／ direction_idあり：{direction_count:,}列車")
    routes = sorted(set(trip["route"] for trip in trips))
    default_route = next((route for route in routes if "山手線" in route), routes[0])
    route = st.selectbox("路線", routes, index=routes.index(default_route), key="test_route")
    route_stations = sorted({stop["name"] for trip in trips if trip["route"] == route
                             for stop in trip["stops"]})
    # 路線変更時に前の路線の駅が選択欄へ残らないよう、駅の状態だけを初期化する。
    if st.session_state.get("_station_list_route") != route:
        st.session_state.pop("test_origin", None)
        st.session_state.pop("test_destination", None)
        st.session_state._station_list_route = route
    origin_default = route_stations.index("浜松町") if "浜松町" in route_stations else 0
    destination_default = route_stations.index("恵比寿") if "恵比寿" in route_stations else min(1, len(route_stations) - 1)
    left, right = st.columns(2)
    origin = left.selectbox("出発駅", route_stations, index=origin_default, key="test_origin")
    destination = right.selectbox("到着駅", route_stations, index=destination_default,
                                  key="test_destination")

    if origin == destination:
        st.warning("異なる駅を選択してください。")
        st.stop()
    strict = find_best_path(trips, route, origin, destination, max_boundaries=0)
    joined = find_best_path(trips, route, origin, destination, max_gap=max_gap,
                            max_boundaries=max_boundaries, require_block=require_block)
    col1, col2 = st.columns(2)
    col1.metric("同一trip内だけ", f"{strict['minutes']}分" if strict else "該当なし")
    col2.metric("trip連結を許可", f"{joined['minutes']}分" if joined else "該当なし",
                delta=(f"{joined['minutes'] - strict['minutes']}分" if strict and joined else None),
                delta_color="inverse")

    st.subheader("同一trip内の最短候補")
    st.dataframe(pd.DataFrame(path_rows(strict)), width="stretch", hide_index=True)
    st.subheader("trip連結後の最短候補")
    st.dataframe(pd.DataFrame(path_rows(joined)), width="stretch", hide_index=True)
    if joined and joined["joins"] and any(text.startswith("推定") for text in joined["joins"]):
        st.warning("block_idがないため、同じ車両の継続ではなく乗換を誤認している可能性があります。")
    elif joined and joined["joins"]:
        st.success("すべてのtrip境界でblock_idが一致しています。")
    st.caption("同じ路線でも反対方向や実際の乗換を接続しないか、表示された経路を確認してください。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args, _ = parser.parse_known_args()
    self_test() if args.self_test else run_streamlit()
