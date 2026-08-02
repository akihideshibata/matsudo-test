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
st.set_page_config(page_title="生活圏同心円", page_icon="🚇", layout="wide",
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
        route_counts = defaultdict(int)
        for row in same_station:
            route_counts[(row["minutes"], row["route"])] += 1
        for row in same_station:
            if len(times) == 1:
                label = row["name"]
            elif row["minutes"] == times[0]:
                label = f'{row["name"]}（速）'
            elif row["minutes"] == times[-1]:
                label = row["name"]
            else:
                label = f'{row["name"]}（{row["minutes"]}分便）'
            # 同じ分数を複数路線が結ぶ場合もカード名を一意にする。
            if sum(x["minutes"] == row["minutes"] for x in same_station) > 1:
                label += f'・{row["route"]}'
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
    for point in points:
        dark, pale = line_style(point["route"])
        href = f'?{base_query}&life_pick={quote(card_id(point))}'
        labels.append(f'''<a class="map-card" href="{href}" title="{escape(point['route'])}"
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
.page-title{font-size:clamp(1.35rem,2.5vw,2rem);font-weight:900;letter-spacing:-.04em;margin:.2rem 0}
.life-map{position:relative;width:min(92vw,920px);height:min(92vw,920px);margin:1rem auto 2rem;
 overflow:hidden;border-radius:24px;background:radial-gradient(circle,#fff 0,#fafcff 72%,#f5f8fc 100%)}
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
.map-card strong{display:block;max-width:140px;overflow:hidden;text-overflow:ellipsis;font-size:.7rem}
.map-card span{font-size:.63rem;font-weight:750;opacity:.72;margin-top:.13rem}
.reverse-time{font-size:clamp(1.25rem,2.3vw,1.8rem);font-weight:950;white-space:nowrap}
.reverse-route{padding:.55rem .7rem;border-left:6px solid var(--line);border-radius:9px;background:var(--pale);
 font-size:.8rem;font-weight:850;line-height:1.35}.reverse-route small{font-weight:650;opacity:.72}
@media(max-width:700px){.life-map{width:96vw;height:96vw;margin-left:calc(50% - 48vw)}
 .map-card{min-width:54px;max-width:105px;padding:.25rem .3rem .23rem .42rem;border-left-width:4px}
 .map-card strong{max-width:94px;font-size:.57rem}.map-card span{font-size:.52rem}.life-home{font-size:.62rem}}
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
    """元の入口である、到着時刻から逆算する直通通勤検索を描画する。"""
    stations = sorted(station_info, key=lambda name: ("・".join(station_info[name]["routes"]), name))
    destination_col, time_col, filter_col = st.columns([2.5, 1.05, .55])
    with destination_col:
        destination = st.selectbox("勤務先・目的駅", stations, index=None,
            placeholder="神保町（駅名・路線で検索）",
            format_func=lambda name: f'{"・".join(station_info[name]["routes"])}｜{name}')
    destination = destination or ("神保町" if "神保町" in station_info else stations[0])
    with time_col:
        arrival_time = st.time_input("到着時刻", value=time(8), step=60)
    target, target_minute = arrival_time.strftime("%H:%M"), minute(arrival_time.strftime("%H:%M"))
    destination_options = {destination: 0}
    with filter_col:
        with st.popover("⚙ 条件", width="stretch"):
            show_under_10 = st.checkbox("10分未満も表示", value=False)
            selected_bands = st.multiselect("所要時間", ["15分以内", "30分以内", "45分以内", "60分以内", "60分超"],
                                            default=["15分以内", "30分以内", "45分以内", "60分以内"])
            keyword = st.text_input("駅名検索")

    st.markdown(f'<div class="page-title">{escape(destination)}に{target}までに着くには？</div>',
                unsafe_allow_html=True)
    st.caption(f'平日・直通のみ｜対象 {escape(service_dates.get("weekday", ""))}')
    if config.get("jr_enabled"):
        st.info("JR東日本の公共交通オープンデータチャレンジ2026限定データを利用しています。")

    rows = reverse_commute("weekday", destination_options, target_minute)
    rows = [row for row in rows if time_band(row["minutes"]) in selected_bands and
            (show_under_10 or row["minutes"] >= 10) and
            (not keyword.strip() or keyword.strip() in row["name"])]
    if not rows:
        st.info("条件に一致する直通列車がありません。")
        return

    for no, row in enumerate(rows):
        accent, background = line_style(row["route"])
        cols = st.columns([2.1, 1.35, 2.25, 1.05, .7], vertical_alignment="center")
        with cols[0]:
            # 駅名自体を押すと生活圏へ移動する。
            if st.button(row["name"], key=f'live_{no}_{row["name"]}', width="stretch"):
                open_life_station(row["name"])
            st.caption(row["location"])
        cols[1].markdown(f'<div class="reverse-time">{clock(row["departure"])}発</div>', unsafe_allow_html=True)
        cols[2].markdown(f'<div class="reverse-route" style="--line:{accent};--pale:{background}">'
                         f'{escape(row["route"])}・直通<br><small>{escape(row["arrival_station"])} '
                         f'{clock(row["arrival"])}着</small></div>', unsafe_allow_html=True)
        cols[3].markdown(f'家賃<br>**{rent_man(row["rent"])}**')
        with cols[4]:
            with st.popover("i"):
                st.write(f'乗車時間：{row["ride"]}分')
                st.write(f'徒歩を含む所要時間：{row["minutes"]}分')
                st.write(f'運行事業者：{row["operator"] or "情報なし"}')
                st.write(f'列車の行先：{row["train_destination"] or "情報なし"}')
        st.divider()

    with st.expander("検索結果を表で確認する"):
        output = pd.DataFrame([{"駅名": r["name"], "所在地": r["location"],
            "出発": clock(r["departure"]), "到着駅": r["arrival_station"],
            "到着": clock(r["arrival"]), "乗車時間": r["ride"],
            "所要時間": r["minutes"], "経路": r["route"]} for r in rows])
        st.dataframe(output, width="stretch", hide_index=True)
        st.download_button("CSVで保存", output.to_csv(index=False).encode("utf-8-sig"),
                           f"{destination}_{target.replace(':', '')}_direct.csv", "text/csv")
    if sources:
        st.caption("データ提供元：" + "、".join(dict.fromkeys(
            source.get("name", "") for source in sources if source.get("name"))))


# クエリに中心駅がある場合だけ生活圏を表示し、それ以外は逆算通勤を表示する。
home = st.query_params.get("life_station")
if home in station_info:
    render_life_screen(home)
else:
    render_reverse_commute()
