import gzip, json, math
from collections import defaultdict
from datetime import time
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st
import pandas as pd

# ============================================================
# 1. ページ・データ読込
# ============================================================
st.set_page_config(page_title="通勤時間と家賃で住む駅探し", page_icon="🚇", layout="wide",
                   initial_sidebar_state="collapsed")


@st.cache_data(show_spinner=False)
def load_json(path):
    """gzip / 通常JSONを読み込む。"""
    path = Path(path)
    if not path.exists():
        return {}
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as file:
            return json.load(file)
    return json.loads(path.read_text(encoding="utf-8"))


def merge_data(parts):
    """通常データとJRデータを駅名単位で統合する。"""
    stations = {}
    timetables = {"weekday": [], "saturday": [], "sunday": []}
    service_dates, sources = {}, []
    for part in filter(None, parts):
        sources.extend(part.get("sources", []))
        service_dates.update(part.get("service_dates", {}))
        for day in timetables:
            timetables[day].extend(part.get("timetables", {}).get(day, []))
        for row in part.get("stations", []):
            name = row["name"]
            current = stations.setdefault(name, {"name": name, "routes": [],
                "operators": [], "location": "所在地未登録", "rent": None,
                "lat": None, "lon": None, "_coords": []})
            current["routes"] = sorted(set(current["routes"] + row.get("routes", [])))
            current["operators"] = sorted(set(current["operators"] + row.get("operators", [])))
            if row.get("location") not in (None, "", "所在地未登録"):
                current["location"] = row["location"]
            if row.get("rent_25sqm") is not None:
                current["rent"] = row["rent_25sqm"]
            if row.get("lat") is not None and row.get("lon") is not None:
                current["_coords"].append((float(row["lat"]), float(row["lon"])))
    for row in stations.values():
        if row["_coords"]:
            row["lat"] = sum(x[0] for x in row["_coords"]) / len(row["_coords"])
            row["lon"] = sum(x[1] for x in row["_coords"]) / len(row["_coords"])
        row.pop("_coords")
    return stations, timetables, service_dates, sources


config = load_json("build_config.json")
basic = load_json("direct_timetable_basic.json.gz")
challenge = load_json("direct_timetable_challenge.json.gz") if config.get("jr_enabled") else {}
station_info, timetables, service_dates, sources = merge_data([basic, challenge])
weekday_trips = timetables["weekday"]
st.session_state.setdefault("show_nearby", False)
if not station_info:
    st.error("時刻表データがありません。GitHub Actionsを実行してください。")
    st.stop()


# ============================================================
# 2. 路線色（既存の line_style と同じ濃色＋淡色）
# ============================================================
LINE_STYLES = {
    "浅草線": ("#e85298", "#fff2f7"), "三田線": ("#0079c2", "#edf8ff"),
    "新宿線": ("#6cbb5a", "#f1faef"), "大江戸線": ("#b6007a", "#fbf0f8"),
    "荒川線": ("#ee7b1a", "#fff8eb"), "日暮里・舎人": ("#9caeb7", "#f3f6f7"),
    "銀座線": ("#f39700", "#fff7e9"), "丸ノ内線": ("#e60012", "#fff1f2"),
    "日比谷線": ("#9caeb7", "#f4f6f7"), "東西線": ("#00a7db", "#edfaff"),
    "千代田線": ("#009944", "#edfaf2"), "有楽町線": ("#d7c447", "#fffced"),
    "半蔵門線": ("#9b7cb6", "#f8f3fb"), "南北線": ("#00ada9", "#effafa"),
    "副都心線": ("#bb641d", "#fff6ef"), "りんかい": ("#00a7e3", "#eefaff"),
    "つくばエクスプレス": ("#003894", "#eef4ff"),
    "多摩モノレール": ("#ff8a00", "#fff7ec"), "山手線": ("#9acd32", "#f5faec"),
    "京浜東北": ("#00b2e5", "#eefaff"), "根岸線": ("#00b2e5", "#eefaff"),
    "中央線快速": ("#f15a22", "#fff5ef"), "中央・総武": ("#ffd400", "#fffceb"),
    "総武線快速": ("#0067a5", "#eff7fc"), "横須賀線": ("#0067a5", "#eff7fc"),
    "埼京線": ("#00a65a", "#effaf4"), "川越線": ("#00a65a", "#effaf4"),
    "常磐線": ("#00a85a", "#effaf4"), "京葉線": ("#c9242f", "#fff1f2"),
    "武蔵野線": ("#f15a22", "#fff5ef"), "東海道線": ("#f68b1f", "#fff6ed"),
    "湘南新宿": ("#e87511", "#fff6ed"), "上野東京": ("#7a5c3e", "#f8f4ef"),
}


def line_style(route):
    """路線名の部分一致でカード色を返す。"""
    return next((style for name, style in LINE_STYLES.items() if name in str(route)),
                ("#667085", "#f8fafc"))


def distance_m(lat1, lon1, lat2, lon2):
    """緯度経度から2駅間の直線距離を計算する。"""
    radius = 6_371_000
    lat1, lat2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlat, dlon = lat2 - lat1, math.radians(float(lon2) - float(lon1))
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def estimated_walk_minutes(distance):
    """直線距離を経路距離へ補正し、徒歩分数を概算する。"""
    return max(1, math.ceil(float(distance) * 1.25 / 75))


def nearby_stations(destination, radius):
    """目的駅から指定半径内にある別名駅を抽出する。"""
    base = station_info[destination]
    if base["lat"] is None or base["lon"] is None:
        return []
    result = []
    for name, info in station_info.items():
        if name == destination or info["lat"] is None or info["lon"] is None:
            continue
        distance = round(distance_m(base["lat"], base["lon"], info["lat"], info["lon"]))
        if distance <= radius:
            result.append({"name": name, "distance": distance,
                           "walk": estimated_walk_minutes(distance)})
    return sorted(result, key=lambda row: (row["distance"], row["name"]))


def relative_rent(rent, base):
    if pd.isna(rent) or pd.isna(base) or not base:
        return None
    return round(float(rent) / float(base) * 100)


def rent_level(ratio):
    if pd.isna(ratio):
        return "不明"
    if ratio < 90:
        return "安い"
    return "同程度" if ratio <= 110 else "高い"


def compact_html(text):
    return " ".join(line.strip() for line in text.splitlines())


def station_label(name):
    routes = "・".join(station_info[name]["routes"])
    return f"{routes}｜{name}" if routes else name


def toggle_nearby():
    st.session_state.show_nearby = not st.session_state.show_nearby


def clock_html(text):
    """逆算通勤カード用の小さなアナログ時計を描画する。"""
    hour, minutes = map(int, text.split(":"))
    numbers = ""
    for number in range(1, 13):
        angle = math.radians(number * 30 - 90)
        x, y = 26 + 20 * math.cos(angle), 26 + 20 * math.sin(angle)
        numbers += f'<span class="clock-number" style="left:{x}px;top:{y}px">{number}</span>'
    return f'''<div class="clock">{numbers}<div class="hand hour-hand"
    style="transform:rotate({(hour % 12) * 30 + minutes * .5}deg)"></div>
    <div class="hand minute-hand" style="transform:rotate({minutes * 6}deg)"></div>
    <div class="clock-center"></div></div>'''


# ============================================================
# 3. 実乗車時間の計算
# ============================================================
def minute(value):
    """24時を超えるGTFS時刻にも対応して分へ直す。"""
    hour, minutes = map(int, str(value).split(":")[:2])
    return hour * 60 + minutes


@st.cache_resource(show_spinner="平日時刻表を索引化しています…")
def build_station_trip_index(trips):
    """駅ごとに、その駅へ停車する列車と停車位置だけを索引化する。"""
    index = defaultdict(list)
    for trip_no, trip in enumerate(trips):
        for stop_no, stop in enumerate(trip.get("stops", [])[:-1]):
            if len(stop) >= 3 and stop[0] and stop[2]:
                index[stop[0]].append((trip_no, stop_no))
    return dict(index)


trip_index = build_station_trip_index(weekday_trips)


@st.cache_data(show_spinner=False)
def direct_access(home):
    """待ち時間・発車時刻・運行間隔を使わず、直通の実乗車時間を列挙する。"""
    found = {}
    for trip_no, start_no in trip_index.get(home, []):
        trip, stops = weekday_trips[trip_no], weekday_trips[trip_no].get("stops", [])
        start = stops[start_no]
        try:
            departure = minute(start[2])
        except (ValueError, TypeError, IndexError):
            continue
        for stop in stops[start_no + 1:]:
            try:
                arrival = minute(stop[1])
            except (ValueError, TypeError, IndexError):
                continue
            minutes = arrival - departure
            if minutes <= 0:
                continue
            if minutes > 60:
                break
            destination, route = stop[0], trip.get("route", "路線情報なし")
            if destination == home or destination not in station_info:
                continue
            # 同じ駅・路線・実乗車時間の列車は1枚へ統合する。
            key = (destination, route, minutes)
            found.setdefault(key, {"name": destination, "route": route,
                "minutes": minutes, "operator": trip.get("operator", ""),
                "train_destination": trip.get("destination", "")})
    rows = list(found.values())
    # 同駅に複数時間があるとき、最短だけを（速）、最長を通常名にする。
    groups = defaultdict(list)
    for row in rows:
        groups[row["name"]].append(row)
    for same_station in groups.values():
        times = sorted(set(row["minutes"] for row in same_station))
        access_routes = len(set(row["route"] for row in same_station))
        for row in same_station:
            if len(times) == 1:
                label = row["name"]
            elif row["minutes"] == times[0]:
                label = f'{row["name"]}（速）'
            else:
                label = row["name"]
            # カード名は駅名か駅名（速）だけとし、分数便・路線名は付けない。
            row["label"] = label
            row["majority"] = len(station_info[row["name"]].get("routes", []))
            row["access_routes"] = access_routes
    return rows


def clock(value):
    """分を24時間表記へ戻す。"""
    return f"{value // 60 % 24:02d}:{value % 60:02d}"


def time_band(value):
    """逆算通勤の所要時間帯を返す。"""
    return next((f"{limit}分以内" for limit in (15, 30, 45, 60) if value <= limit), "60分超")


def rent_man(value):
    return f"{float(value) / 10000:.1f}万円" if pd.notna(value) else "情報なし"


@st.cache_data(show_spinner=False)
def reverse_commute(day, destinations, target_minute):
    """到着時刻から逆算し、各駅から乗れる最も遅い直通列車を選ぶ。"""
    latest = {}
    for trip in timetables.get(day, []):
        stops = trip.get("stops", [])
        for destination_no, destination_stop in enumerate(stops):
            if len(destination_stop) < 2 or destination_stop[0] not in destinations or not destination_stop[1]:
                continue
            walk = destinations[destination_stop[0]]
            arrival = minute(destination_stop[1])
            if arrival + walk > target_minute:
                continue
            for origin in stops[:destination_no]:
                if len(origin) < 3 or not origin[2] or origin[0] in destinations:
                    continue
                departure = minute(origin[2])
                if departure >= arrival:
                    continue
                info, name = station_info.get(origin[0], {}), origin[0]
                row = {"name": name, "location": info.get("location", "所在地未登録"),
                    "rent": info.get("rent"), "departure": departure, "arrival": arrival,
                    "arrival_station": destination_stop[0], "walk": walk,
                    "ride": arrival - departure, "minutes": arrival + walk - departure,
                    "route": trip.get("route", "路線情報なし"),
                    "operator": trip.get("operator", ""),
                    "train_destination": trip.get("destination", "")}
                current = latest.get(name)
                if current is None or departure > current["departure"] or (
                        departure == current["departure"] and row["minutes"] < current["minutes"]):
                    latest[name] = row
    return sorted(latest.values(), key=lambda row: row["departure"], reverse=True)


@st.cache_data(show_spinner=False)
def search_routes(day, destinations, target_minute):
    """正常版と同じ列名で、各出発駅の最遅直通便を検索する。"""
    latest = {}
    for row in reverse_commute(day, destinations, target_minute):
        info = station_info.get(row["name"], {})
        candidate = {
            "駅名": row["name"], "所在地": row["location"], "家賃": row["rent"],
            "出発": clock(row["departure"]), "到着": clock(row["arrival"]),
            "到着駅": row["arrival_station"], "徒歩時間": row["walk"],
            "目的地到着": clock(row["arrival"] + row["walk"]),
            "乗車時間": row["ride"], "所要時間": row["minutes"],
            "経路": row["route"], "事業者": row["operator"],
            "行先": row["train_destination"], "路線一覧": info.get("routes", []),
            "出発分": row["departure"],
        }
        latest[row["name"]] = candidate
    return sorted(latest.values(), key=lambda row: row["出発分"], reverse=True)


def day_text(result):
    if not result:
        return "該当する直通列車なし"
    walk = f'＋徒歩{result["徒歩時間"]}分' if result["徒歩時間"] else ""
    return f'{result["出発"]}発（{result["到着駅"]} {result["到着"]}着{walk}）'


def bearing(home, destination):
    """球面上の初期方位を、上が北・右が東のラジアン角で返す。"""
    base, target = station_info[home], station_info[destination]
    if None in (base["lat"], base["lon"], target["lat"], target["lon"]):
        return None
    lat1, lat2 = map(math.radians, (base["lat"], target["lat"]))
    dlon = math.radians(target["lon"] - base["lon"])
    return math.atan2(math.sin(dlon) * math.cos(lat2),
                      math.cos(lat1) * math.sin(lat2) -
                      math.sin(lat1) * math.cos(lat2) * math.cos(dlon))


def select_initial(rows, expanded):
    """主要駅を駅単位で先に確保し、残り枠へ別時間カードを追加する。"""
    bands = ((0, 15, 10), (15, 30, 12), (30, 45, 10), (45, 60, 8))
    shown, hidden = [], []
    for low, high, limit in bands:
        band = [r for r in rows if low < r["minutes"] <= high]
        if expanded:
            shown.extend(band)
            continue

        # 同じ駅の時間違いが表示枠を独占しないよう、まず各駅から1枚ずつ選ぶ。
        by_station = defaultdict(list)
        for row in band:
            by_station[row["name"]].append(row)
        representatives = []
        for station_rows in by_station.values():
            # 通常名のカードを優先し、なければ最短の実在時間を代表にする。
            representatives.append(min(station_rows, key=lambda r: (
                "（" in r["label"], r["minutes"], -r["access_routes"], r["route"])))

        # 乗入路線数、直通で利用できる路線数、所要時間の順で主要駅を決める。
        priority = lambda r: (-r["majority"], -r["access_routes"], r["minutes"], r["name"])
        representatives.sort(key=priority)
        selected = representatives[:limit]

        # 全主要駅の代表を確保した後、空き枠へ「速」など別時間カードを追加する。
        selected_ids = {id(row) for row in selected}
        variants = sorted((r for r in band if id(r) not in selected_ids), key=priority)
        selected.extend(variants[:max(0, limit - len(selected))])
        selected_ids = {id(row) for row in selected}
        shown.extend(selected)
        hidden.extend(r for r in band if id(r) not in selected_ids)
    return shown, hidden


def boxes_overlap(a, b):
    """カードを長方形として衝突判定する。"""
    return abs(a["x"] - b["x"]) < (a["w"] + b["w"]) / 2 and abs(a["y"] - b["y"]) < 5.2


def place_cards(home, rows, expanded=False):
    """時間半径を固定し、同一方角を扇状に広げて角度だけで衝突回避する。"""
    candidates = []
    for row in rows:
        angle = bearing(home, row["name"])
        if angle is not None:
            candidates.append({**row, "angle": angle,
                "sector": round(math.degrees(angle) / 8),
                "w": min(15.5, max(7.0, 4.5 + len(row["label"]) * 1.05))})
    # 主要駅から配置し、衝突時に東京・横浜などが後発カードへ負けないようにする。
    candidates.sort(key=lambda r: (-r["majority"], -r["access_routes"],
                                   r["minutes"], r["sector"], r["label"]))
    sector_count, placed, overflow = defaultdict(int), [], []
    # 実方位を壊さないよう、衝突回避は最大12度までに限定する。
    offsets = [0] + [sign * degree for degree in range(4, 13, 4) for sign in (1, -1)]
    for row in candidates:
        fan = sector_count[row["sector"]]
        sector_count[row["sector"]] += 1
        preferred = ([0, 4, -4, 8, -8, 12, -12][fan:fan + 1] or [0])
        attempts = preferred + [x for x in offsets if x not in preferred]
        radius = row["minutes"] / 60 * 46  # カード中心＝実乗車時間の半径
        accepted = None
        for offset in attempts:
            angle = row["angle"] + math.radians(offset)
            card = {**row, "x": 50 + math.sin(angle) * radius,
                    "y": 50 - math.cos(angle) * radius, "offset": offset}
            if 3.5 <= card["x"] <= 96.5 and 3.5 <= card["y"] <= 96.5 \
                    and not any(boxes_overlap(card, old) for old in placed):
                accepted = card
                break
        if accepted:
            placed.append(accepted)
        else:
            overflow.append(row)
    return placed, overflow


# ============================================================
# 4. 履歴・ダイアログ
# ============================================================
st.session_state.setdefault("life_history", [])
st.session_state.setdefault("expanded_homes", set())


def clear_pick():
    """外側クリック・×操作で選択を消し、次回の再表示を防ぐ。"""
    st.query_params.pop("life_pick", None)


def move_to_station(name):
    """現在駅を履歴へ積み、選択駅を新しい中心にする。"""
    current = st.query_params.get("life_station")
    if current and current != name:
        st.session_state.life_history.append(current)
    st.query_params["life_station"] = name
    st.query_params.pop("life_pick", None)
    st.rerun()


def go_back():
    """履歴があれば前駅へ、なければ逆算通勤画面へ戻る。"""
    if st.session_state.life_history:
        st.query_params["life_station"] = st.session_state.life_history.pop()
    else:
        st.query_params.pop("life_station", None)
    st.query_params.pop("life_pick", None)
    st.rerun()


@st.dialog("この駅を中心に表示しますか？", width="small", dismissible=True,
           on_dismiss=clear_pick)
def station_dialog(card):
    """同時に一つだけ開く、閉じられる駅確認ダイアログ。"""
    st.subheader(card["label"])
    st.write(f'{card["minutes"]}分・{card["route"]}')
    st.caption("待ち時間・発車時刻・運行間隔を含まない、直通列車の実乗車時間です。")
    left, right = st.columns(2)
    if left.button(f'{card["name"]}から見る', type="primary", width="stretch"):
        move_to_station(card["name"])
    if right.button("キャンセル", width="stretch"):
        clear_pick()
        st.rerun()


# ============================================================
# 5. 同心円画面
# ============================================================
def card_id(row):
    """クエリ文字列へ安全に載せるカード識別子。"""
    return json.dumps([row["name"], row["route"], row["minutes"]], ensure_ascii=False,
                      separators=(",", ":"))


def render_life_screen(home):
    rows = direct_access(home)
    expanded = home in st.session_state.expanded_homes
    selected, hidden_by_limit = select_initial(rows, expanded)
    points, hidden_by_collision = place_cards(home, selected, expanded)
    hidden_count = len(hidden_by_limit)

    top1, top2 = st.columns([1, 5])
    if top1.button("← 前の画面へ", width="stretch"):
        go_back()
    trail = st.session_state.life_history + [home]
    top2.caption(" ＞ ".join(trail[-6:]))
    st.markdown(f'<div class="page-title">{escape(home)}から広がる生活圏</div>',
                unsafe_allow_html=True)
    st.caption("直通列車に乗っている時間を、実際の方角と時間半径で表示します。")

    if hidden_count and not expanded:
        if st.button(f"ほか{hidden_count}件も表示", key=f"expand_{home}", width="content"):
            st.session_state.expanded_homes.add(home)
            st.rerun()
    elif expanded and st.button("表示を絞る", key=f"collapse_{home}", width="content"):
        st.session_state.expanded_homes.discard(home)
        st.rerun()

    rings = "".join(f'<div class="life-ring r{n}"><span>{n}分</span></div>'
                    for n in (15, 30, 45, 60))
    labels = []
    base_query = f"life_station={quote(home)}"
    for key in ("return_destination", "return_time"):
        value = st.query_params.get(key)
        if value:
            base_query += f"&amp;{key}={quote(value)}"
    for point in points:
        dark, pale = line_style(point["route"])
        href = f'?{base_query}&amp;life_pick={quote(card_id(point))}'
        labels.append(f'''<a class="map-card" href="{href}"
          data-route="{escape(point['route'], quote=True)}"
          style="left:{point['x']:.3f}%;top:{point['y']:.3f}%;--line:{dark};--pale:{pale}">
          <strong>{escape(point['label'])}</strong><span>{point['minutes']}分</span></a>''')
    html = f'<div class="life-map">{rings}<div class="life-home">{escape(home)}</div>{"".join(labels)}</div>'
    st.markdown(html, unsafe_allow_html=True)
    if not points:
        st.info("60分以内に表示できる直通駅がありません。")
    if hidden_by_collision:
        st.caption(f"重なりを避けきれない{len(hidden_by_collision)}件は省略しました。時間半径は動かしていません。")

    raw_pick = st.query_params.get("life_pick")
    if raw_pick:
        try:
            name, route, minutes = json.loads(raw_pick)
            picked = next((row for row in rows if row["name"] == name and
                           row["route"] == route and row["minutes"] == minutes), None)
            if picked:
                station_dialog(picked)
            else:
                clear_pick()
        except (ValueError, TypeError, json.JSONDecodeError):
            clear_pick()


# ============================================================
# 6. CSS
# ============================================================
st.markdown("""
<style>
.block-container{max-width:1240px;padding:2.5rem 1rem 3rem!important}
.selector-label{opacity:.68;font-size:.72rem;font-weight:750;margin-bottom:.16rem}
.heading-row{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin:.5rem 0}
.page-note{opacity:.58;font-size:.68rem;text-align:right;white-space:nowrap}
.challenge-notice{padding:.42rem .65rem;margin:.2rem 0 .55rem;border:1px solid #e5a00080;
 border-radius:9px;background:#fff8df;color:#694c00;font-size:.68rem}
.near-destination{padding:.6rem .72rem;margin:.35rem 0 .6rem;border:1px solid #98a2b360;
 border-radius:10px;background:rgba(128,128,128,.05)}
.near-destination-title{font-size:.76rem;font-weight:850;margin-bottom:.1rem}
.near-destination-note{font-size:.64rem;opacity:.65;margin-bottom:.35rem}
.st-key-nearby_toggle [data-testid="stHorizontalBlock"]{align-items:center!important}
.st-key-nearby_toggle [data-testid="stMarkdownContainer"],
.st-key-nearby_toggle [data-testid="stMarkdownContainer"] p{margin:0!important}
.nearby-row{display:flex;align-items:center;justify-content:space-between;height:34px;padding:0 .65rem;
 background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.35);border-radius:9px;font-size:.7rem}
.st-key-nearby_toggle div[data-testid="stButton"] button{height:34px!important;min-height:34px!important;
 padding:0 .6rem!important;font-size:.68rem!important;white-space:nowrap;border-radius:9px!important}
.station-card{position:relative;display:grid;grid-template-columns:minmax(145px,1fr) minmax(190px,1.1fr)
 minmax(180px,1fr) 42px;grid-template-areas:"station departure route actions" "location arrival rent actions";
 align-items:center;gap:.08rem clamp(.7rem,1.8vw,1.4rem);color:#283141!important;background:var(--card-bg)!important;
 border:1px solid #98a2b380;border-left:6px solid var(--line-color)!important;border-radius:12px;
 padding:.62rem .85rem;margin-bottom:.42rem;box-shadow:0 1px 3px #0000000b}
.station-card div,.station-card span,.station-card summary{color:#283141!important}
.station-name{grid-area:station;color:#283141!important;text-decoration:none!important;font-size:clamp(1.25rem,2.2vw,1.7rem);
 font-weight:900;line-height:1.05;letter-spacing:-.04em;overflow-wrap:anywhere}
.station-name:hover{text-decoration:underline!important;text-underline-offset:3px}
.location{grid-area:location;color:#667085!important;font-size:.68rem}
.departure-wrap{grid-area:departure;display:flex;align-items:center;gap:.55rem}
.departure{font-size:clamp(1.45rem,2.6vw,1.95rem);font-weight:950;letter-spacing:-.05em;white-space:nowrap}
.arrival{grid-area:arrival;color:#667085!important;font-size:.68rem;padding-left:58px;white-space:nowrap}
.route{grid-area:route;font-size:.81rem;font-weight:850;line-height:1.25}
.rent{grid-area:rent;color:#475467!important;font-size:.72rem;font-weight:800;white-space:nowrap}
.clock{position:relative;width:52px;height:52px;flex:0 0 52px;border:2px solid #344054;border-radius:50%;background:#fff}
.clock-number{position:absolute;width:10px;height:10px;margin:-5px;text-align:center;line-height:10px;font-size:6px;font-weight:750}
.hand{position:absolute;left:24px;bottom:25px;transform-origin:bottom center;background:#344054;border-radius:4px}
.hour-hand{width:4px;height:12px}.minute-hand{width:2px;height:18px}
.clock-center{position:absolute;left:21px;top:21px;width:6px;height:6px;border-radius:50%;background:#344054}
.actions-area{grid-area:actions;display:flex;align-items:center;justify-content:center}.details-area{text-align:center}
.station-card details{font-size:.68rem}.station-card summary{display:inline-flex;align-items:center;justify-content:center;
 width:28px;height:28px;border:1px solid #98a2b3;border-radius:50%;background:#ffffffb8;cursor:pointer;
 list-style:none;font-family:serif;font-size:.8rem;font-weight:900}.station-card summary::-webkit-details-marker{display:none}
.details-body{position:absolute;z-index:30;right:.8rem;top:3.2rem;width:min(390px,calc(100vw - 3rem));
 padding:.65rem .75rem;border:1px solid #d0d5dd;border-radius:9px;background:#fff;text-align:left;
 line-height:1.65;box-shadow:0 7px 20px #0002}.detail-label{font-weight:850}
.detail-divider{height:1px;background:#e4e7ec;margin:.35rem 0}.empty{padding:2rem;text-align:center;
 border:1px dashed rgba(128,128,128,.6);border-radius:12px}
.page-title{font-size:clamp(1.35rem,2.5vw,2rem);font-weight:900;letter-spacing:-.04em;margin:.2rem 0}
.life-map{position:relative;width:min(92vw,920px);height:min(92vw,920px);margin:1rem auto 2rem;
 overflow:visible;border-radius:24px;background:radial-gradient(circle,#fff 0,#fafcff 72%,#f5f8fc 100%)}
.life-ring{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);border:1px solid #98a2b355;
 border-radius:50%;pointer-events:none}.life-ring span{position:absolute;left:50%;top:-.65rem;transform:translateX(-50%);
 color:#667085;background:#fff;padding:0 .28rem;font-size:.68rem;font-weight:750;white-space:nowrap}
.r15{width:23%;height:23%}.r30{width:46%;height:46%}.r45{width:69%;height:69%}.r60{width:92%;height:92%}
.life-home{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:8;max-width:120px;
 padding:.48rem .7rem;border-radius:999px;background:#101828;color:#fff;font-size:.78rem;font-weight:900;
 text-align:center;box-shadow:0 5px 18px #10182833}
.map-card{position:absolute;z-index:5;transform:translate(-50%,-50%);display:flex;flex-direction:column;
 align-items:center;justify-content:center;min-width:70px;max-width:156px;padding:.34rem .5rem .3rem .62rem;
 border:1px solid #98a2b344;border-left:5px solid var(--line);border-radius:9px;background:var(--pale);
 color:#1d2939!important;text-decoration:none!important;line-height:1.12;text-align:center;white-space:nowrap;
 box-shadow:0 2px 8px #1018281c;transition:transform .12s,box-shadow .12s}
.map-card:hover{z-index:20;transform:translate(-50%,-50%) scale(1.06);box-shadow:0 6px 18px #10182830}
.map-card:hover::after{content:attr(data-route);position:absolute;left:50%;bottom:calc(100% + 7px);
 transform:translateX(-50%);z-index:40;width:max-content;max-width:230px;padding:.34rem .48rem;
 border-radius:7px;background:#101828;color:#fff;font-size:.61rem;font-weight:700;line-height:1.3;
 white-space:normal;box-shadow:0 4px 12px #10182838;pointer-events:none}
.map-card:hover::before{content:"";position:absolute;left:50%;bottom:calc(100% + 2px);transform:translateX(-50%);
 border:5px solid transparent;border-top-color:#101828;pointer-events:none}
.map-card strong{display:block;max-width:140px;overflow:hidden;text-overflow:ellipsis;font-size:.7rem}
.map-card span{font-size:.63rem;font-weight:750;opacity:.72;margin-top:.13rem}
.reverse-time{font-size:clamp(1.25rem,2.3vw,1.8rem);font-weight:950;white-space:nowrap}
.reverse-route{padding:.55rem .7rem;border-left:6px solid var(--line);border-radius:9px;background:var(--pale);
 font-size:.8rem;font-weight:850;line-height:1.35}.reverse-route small{font-weight:650;opacity:.72}
@media(max-width:700px){.life-map{width:96vw;height:96vw;margin-left:calc(50% - 48vw)}
 .map-card{min-width:54px;max-width:105px;padding:.25rem .3rem .23rem .42rem;border-left-width:4px}
 .map-card strong{max-width:94px;font-size:.57rem}.map-card span{font-size:.52rem}.life-home{font-size:.62rem}
 .block-container{padding:2.9rem .55rem 2.5rem!important}.selector-label{font-size:.59rem}
 .heading-row{display:block}.page-note{text-align:left;white-space:normal}.challenge-notice{font-size:.57rem}
 .station-card{grid-template-columns:minmax(0,1.2fr) minmax(100px,.88fr) minmax(112px,.9fr);
  grid-template-areas:"station departure rent" "location arrival route";gap:.1rem .32rem;border-left-width:5px!important;
  padding:.48rem .5rem}.station-name{font-size:1.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .location{font-size:.57rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.departure-wrap{display:block}
 .clock{display:none}.departure{font-size:1.25rem}.arrival{padding:0;font-size:.54rem}.rent{padding-right:22px;font-size:.58rem}
 .route{font-size:.57rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.actions-area{position:absolute;top:.31rem;right:.3rem}
 .station-card summary{width:20px;height:20px;font-size:.6rem}.details-body{position:relative;right:auto;top:auto;
  width:auto;margin-top:.35rem;box-shadow:none}}
</style>
""", unsafe_allow_html=True)


# ============================================================
# 7. 逆算通勤画面（生活圏への入口）
# ============================================================
def open_life_station(name):
    """逆算通勤から生活圏へ入り、生活圏内の履歴を初期化する。"""
    st.session_state.life_history = []
    st.query_params["life_station"] = name
    st.query_params.pop("life_pick", None)
    st.rerun()


def render_reverse_commute():
    """正常版の逆算通勤画面を、その構造と機能を保って描画する。"""
    stations = sorted(station_info, key=lambda name: ("・".join(station_info[name]["routes"]), name))
    # 生活圏から戻った新しいセッションでも、勤務先と到着時刻を復元する。
    return_destination = st.query_params.get("return_destination")
    return_time = st.query_params.get("return_time")
    if "commute_destination" not in st.session_state and return_destination in station_info:
        st.session_state.commute_destination = return_destination
    if "commute_arrival" not in st.session_state and return_time:
        try:
            st.session_state.commute_arrival = time.fromisoformat(return_time)
        except ValueError:
            pass
    destination_col, time_col, filter_col = st.columns([2.5, 1.05, .38])
    with destination_col:
        st.markdown('<div class="selector-label">勤務先・目的駅</div>', unsafe_allow_html=True)
        selected_destination = st.selectbox("勤務先・目的駅", stations, index=None,
            placeholder="神保町（駅名・路線で検索）", format_func=station_label,
            label_visibility="collapsed", key="commute_destination")
    destination = selected_destination or ("神保町" if "神保町" in station_info else stations[0])
    with time_col:
        st.markdown('<div class="selector-label">到着</div>', unsafe_allow_html=True)
        arrival_time = st.time_input("到着時刻", value=time(8), step=60,
                                     label_visibility="collapsed", key="commute_arrival")
    target, target_minute = arrival_time.strftime("%H:%M"), minute(arrival_time.strftime("%H:%M"))
    destination_rent, destination_options = station_info[destination]["rent"], {destination: 0}

    nearby_mode = st.toggle("近隣駅も到着候補に含める", value=False, key="commute_nearby")
    if nearby_mode:
        st.markdown('<div class="near-destination">', unsafe_allow_html=True)
        radius = st.select_slider("近隣駅として探す範囲", options=[300, 400, 500, 600, 800, 1000],
                                  value=500, format_func=lambda value: f"{value}m", key="commute_radius")
        candidates = nearby_stations(destination, radius)
        if not candidates:
            st.info("指定範囲内に、座標を確認できる別の駅はありません。")
        else:
            st.markdown(f'<div class="near-destination-title">近くの駅を{len(candidates)}駅見つけました</div>'
                '<div class="near-destination-note">使用する駅と、そこから目的地までの徒歩時間を調整できます。</div>',
                unsafe_allow_html=True)
            for candidate in candidates:
                name, distance, estimated = candidate["name"], candidate["distance"], candidate["walk"]
                key_base = f"{destination}_{radius}_{name}"
                use_col, walk_col = st.columns([3.2, 1.2], vertical_alignment="center")
                use_station = use_col.checkbox(f"{name}（直線約{distance}m）", value=True,
                                               key=f"use_{key_base}")
                walk = walk_col.number_input(f"{name}から目的地まで", 1, 30, estimated,
                    key=f"walk_{key_base}", label_visibility="collapsed")
                if use_station:
                    destination_options[name] = int(walk)
        st.markdown("</div>", unsafe_allow_html=True)

    weekday_df = pd.DataFrame(search_routes("weekday", destination_options, target_minute))
    saturday = {row["駅名"]: row for row in search_routes("saturday", destination_options, target_minute)}
    sunday = {row["駅名"]: row for row in search_routes("sunday", destination_options, target_minute)}
    bands = ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"]
    if not weekday_df.empty:
        weekday_df["時間圏"] = weekday_df["所要時間"].apply(time_band)
        weekday_df["相対家賃"] = weekday_df["家賃"].apply(lambda value: relative_rent(value, destination_rent))
        weekday_df["家賃区分"] = weekday_df["相対家賃"].apply(rent_level)

    with filter_col:
        st.markdown('<div class="selector-label">条件</div>', unsafe_allow_html=True)
        with st.popover("⚙"):
            st.checkbox("10分未満の出発駅も表示", key="show_nearby")
            rent_filter = st.radio("家賃", ["すべて", "安い", "同程度", "高い"], horizontal=True,
                                   key="commute_rent")
            route_options = sorted(weekday_df["経路"].dropna().unique()) if not weekday_df.empty else []
            if "commute_routes" in st.session_state:
                st.session_state.commute_routes = [route for route in st.session_state.commute_routes
                                                   if route in route_options]
            selected_routes = st.multiselect("利用路線", route_options, default=route_options,
                                             key="commute_routes")
            selected_bands = st.multiselect(f"{destination}までの所要時間", bands, default=bands,
                                            key="commute_bands")
            keyword = st.text_input("駅名検索", placeholder="例：浅草、新宿", key="commute_keyword")

    st.markdown(compact_html(f'''<div class="heading-row"><div class="page-title">{escape(destination)}に
        {target}までに着くには？</div><div class="page-note">平日・直通のみ｜対象
        {escape(service_dates.get("weekday", ""))}</div></div>'''), unsafe_allow_html=True)
    if len(destination_options) > 1:
        st.caption("到着候補：" + "、".join(destination_options) +
                   "。近隣駅は設定した徒歩時間を差し引いて検索しています。")
    if config.get("jr_enabled"):
        st.markdown('<div class="challenge-notice">JR東日本の公共交通オープンデータチャレンジ2026限定データを利用しています。</div>',
                    unsafe_allow_html=True)

    df = weekday_df.copy()
    if not df.empty:
        df = df[df["時間圏"].isin(selected_bands) & df["経路"].isin(selected_routes)]
        if rent_filter != "すべて":
            df = df[df["家賃区分"] == rent_filter]
        if keyword.strip():
            df = df[df["駅名"].str.contains(keyword.strip(), na=False, regex=False)]
    nearby_count = len(df[df["所要時間"] < 10]) if not df.empty else 0
    if not st.session_state.show_nearby and not df.empty:
        df = df[df["所要時間"] >= 10].copy()

    if nearby_count or st.session_state.show_nearby:
        with st.container(key="nearby_toggle"):
            notice_col, button_col = st.columns([5.4, 1], vertical_alignment="center")
            message = (f"<strong>近距離の出発駅も表示中</strong><span>10分未満の{nearby_count}駅を含む</span>"
                if st.session_state.show_nearby else
                f"<strong>少し離れた候補を優先して表示中</strong><span>10分未満の{nearby_count}駅を省略</span>")
            notice_col.markdown(compact_html(f'<div class="nearby-row">{message}</div>'),
                                unsafe_allow_html=True)
            button_col.button("隠す" if st.session_state.show_nearby else "表示",
                key="toggle_nearby_button", width="stretch", on_click=toggle_nearby)

    if df.empty:
        st.markdown('<div class="empty">条件に一致する直通列車がありません。</div>', unsafe_allow_html=True)
    else:
        for _, row in df.iterrows():
            raw_station = str(row["駅名"])
            station, location, route = map(escape, (raw_station, str(row["所在地"]), str(row["経路"])))
            operator, train_destination = escape(str(row["事業者"])), escape(str(row["行先"]))
            routes = escape(" ／ ".join(row["路線一覧"]))
            arrival_station, walk = escape(str(row["到着駅"])), int(row["徒歩時間"])
            accent, background = line_style(row["経路"])
            rent, ratio = row["家賃"], row["相対家賃"]
            sat, sun = saturday.get(raw_station), sunday.get(raw_station)
            ratio_text = f"{int(ratio)}%" if pd.notna(ratio) else "算出不可"
            candidate_rent = f"25㎡換算 約{rent_man(rent)}" if pd.notna(rent) else "情報なし"
            destination_rent_text = f"25㎡換算 約{rent_man(destination_rent)}" if pd.notna(destination_rent) else "情報なし"
            arrival_text = (f'{arrival_station} {row["到着"]}着 → 徒歩{walk}分 → '
                f'{escape(destination)} {row["目的地到着"]}' if walk else
                f'{escape(destination)} {row["到着"]}着')
            life_href = (f'?life_station={quote(raw_station)}&amp;return_destination={quote(destination)}'
                         f'&amp;return_time={quote(target)}')
            card = f'''<div class="station-card" style="--line-color:{accent};--card-bg:{background}">
            <a class="station-name" href="{life_href}" title="{station}の生活圏を見る">{station}</a>
            <div class="location">{location}</div><div class="departure-wrap">{clock_html(str(row["出発"]))}
            <div class="departure">{row["出発"]}発</div></div><div class="arrival">{arrival_text}</div>
            <div class="rent">家賃：{row["家賃区分"]}</div><div class="route">{route}・直通</div>
            <div class="actions-area"><div class="details-area"><details><summary>i</summary><div class="details-body">
            <div><span class="detail-label">所在地：</span>{location}</div>
            <div><span class="detail-label">乗り入れ路線：</span>{routes}</div>
            <div><span class="detail-label">運行事業者：</span>{operator or "情報なし"}</div><div class="detail-divider"></div>
            <div><span class="detail-label">家賃評価：</span>{row["家賃区分"]}</div>
            <div><span class="detail-label">相対家賃：</span>{ratio_text}</div>
            <div><span class="detail-label">{station}：</span>{candidate_rent}</div>
            <div><span class="detail-label">{escape(destination)}：</span>{destination_rent_text}</div>
            <div class="detail-divider"></div><div><span class="detail-label">平日：</span>{row["出発"]}発
            （{arrival_text}・{route}）</div><div><span class="detail-label">土曜：</span>{escape(day_text(sat))}</div>
            <div><span class="detail-label">日曜：</span>{escape(day_text(sun))}</div>
            <div><span class="detail-label">乗車時間：</span>{row["乗車時間"]}分</div>
            <div><span class="detail-label">徒歩を含む所要時間：</span>{row["所要時間"]}分</div>
            <div><span class="detail-label">列車の行先：</span>{train_destination}</div>
            </div></details></div></div></div>'''
            st.markdown(compact_html(card), unsafe_allow_html=True)

    with st.expander("検索結果を表で確認する"):
        if df.empty:
            st.info("表示できる検索結果がありません。")
        else:
            columns = ["駅名", "所在地", "家賃区分", "相対家賃", "家賃", "出発", "到着駅", "到着",
                       "徒歩時間", "目的地到着", "乗車時間", "所要時間", "経路", "事業者", "行先"]
            output = df[columns].copy()
            output["相対家賃"] = output["相対家賃"].apply(lambda value: f"{int(value)}%" if pd.notna(value) else "")
            output["家賃"] = output["家賃"].apply(lambda value: rent_man(value) if pd.notna(value) else "")
            st.dataframe(output, width="stretch", hide_index=True)
            st.download_button("CSVで保存", output.to_csv(index=False).encode("utf-8-sig"),
                               f"{destination}_{target.replace(':', '')}_direct.csv", "text/csv")

    basic_sources = [source["name"] for source in basic.get("sources", []) if source.get("name")]
    challenge_sources = [source["name"] for source in challenge.get("sources", []) if source.get("name")]
    st.caption("家賃は、目的駅比90%未満を「安い」、90〜110%を「同程度」、110%超を「高い」と表示しています。")
    st.caption("家賃目安は住宅・土地統計調査の市区町村別1㎡当たり家賃を25㎡に換算した参考値です。")
    st.caption(f'通常データ提供元：{"、".join(basic_sources)}。各提供データを加工して利用しています。')
    if challenge_sources:
        st.caption(f'チャレンジ限定データ提供元：{"、".join(challenge_sources)}。')


# クエリに中心駅がある場合だけ生活圏を表示し、それ以外は逆算通勤を表示する。
home = st.query_params.get("life_station")
if home in station_info:
    render_life_screen(home)
else:
    render_reverse_commute()
