import argparse, gzip, json, math, os, sqlite3, tempfile
from collections import defaultdict
from pathlib import Path

OUT = Path("direct_access.sqlite")
METADATA_OUT = Path("access_metadata.json.gz")
VERSION = "1"
MAX_GAP = int(os.getenv("ACCESS_MAX_GAP", "2"))


def minute(value):
    hour, minutes = map(int, str(value).split(":")[:2])
    return hour * 60 + minutes


def load_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as file:
            return json.load(file)
    return json.loads(path.read_text(encoding="utf-8"))


def save_gzip(path, value):
    with gzip.open(path, "wt", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, separators=(",", ":"))


def read_sources(directory):
    """既存の公開JSONを統合し、駅座標と曜日別列車を返す。"""
    directory = Path(directory)
    config = load_json(directory / "build_config.json")
    paths = [directory / "direct_timetable_basic.json.gz"]
    challenge = directory / "direct_timetable_challenge.json.gz"
    if config.get("jr_enabled") and challenge.exists():
        paths.append(challenge)
    stations, parts, timetables = {}, [], {"weekday": [], "saturday": [], "sunday": []}
    for source_no, path in enumerate(paths):
        data = load_json(path)
        parts.append({key: value for key, value in data.items()
                      if key not in ("timetables", "trips")})
        for station in data.get("stations", []):
            if station.get("lat") is not None and station.get("lon") is not None:
                stations[station["name"]] = (float(station["lat"]), float(station["lon"]))
        for day in timetables:
            for trip_no, trip in enumerate(data.get("timetables", {}).get(day, [])):
                normalized = normalize_trip(trip, f"{day}:{source_no}:{trip_no}")
                if normalized:
                    timetables[day].append(normalized)
    return stations, timetables, paths, parts


def normalize_trip(raw, key):
    stops = []
    for stop in raw.get("stops", []):
        if len(stop) < 3 or not stop[0] or not (stop[1] or stop[2]):
            continue
        try:
            arrival, departure = minute(stop[1] or stop[2]), minute(stop[2] or stop[1])
        except (TypeError, ValueError):
            continue
        stops.append({"station": stop[0], "arrival": arrival, "departure": departure})
    if len(stops) < 2:
        return None
    return {"key": key, "route": str(raw.get("route", "路線情報なし")),
            "operator": str(raw.get("operator", "")),
            "headsign": str(raw.get("destination", "")), "stops": stops}


def create_schema(db):
    db.executescript("""
    PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY;
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE trip_stops(day TEXT NOT NULL,trip_key TEXT NOT NULL,route TEXT NOT NULL,
      operator TEXT NOT NULL,headsign TEXT NOT NULL,seq INTEGER NOT NULL,station TEXT NOT NULL,
      arrival INTEGER NOT NULL,departure INTEGER NOT NULL,PRIMARY KEY(trip_key,seq));
    CREATE INDEX idx_trip_station_arrival ON trip_stops(day,station,arrival);
    CREATE INDEX idx_trip_station_departure ON trip_stops(day,station,departure);
    CREATE INDEX idx_trip_sequence ON trip_stops(trip_key,seq);
    CREATE TABLE life_raw(origin TEXT NOT NULL,destination TEXT NOT NULL,route TEXT NOT NULL,
      direction INTEGER NOT NULL,minutes INTEGER NOT NULL,stop_count INTEGER NOT NULL,
      confidence TEXT NOT NULL,PRIMARY KEY(origin,destination,route,direction,minutes));
    """)


def insert_trips(db, timetables):
    rows = []
    for day, trips in timetables.items():
        for trip in trips:
            rows.extend((day, trip["key"], trip["route"], trip["operator"], trip["headsign"],
                         seq, stop["station"], stop["arrival"], stop["departure"])
                        for seq, stop in enumerate(trip["stops"]))
    db.executemany("INSERT INTO trip_stops VALUES(?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def connect_trips(trips):
    """同一路線の終着・始発が0〜2分で続くtripを一対一で接続する。"""
    starts = defaultdict(list)
    for no, trip in enumerate(trips):
        first = trip["stops"][0]
        starts[(trip["route"], first["station"])].append((first["departure"], no))
    edges = []
    for previous_no, previous in enumerate(trips):
        terminal = previous["stops"][-1]
        for departure, following_no in starts.get((previous["route"], terminal["station"]), []):
            following = trips[following_no]
            if following_no == previous_no:
                continue
            if previous["operator"] and following["operator"] and previous["operator"] != following["operator"]:
                continue
            gap = departure - terminal["arrival"]
            if 0 <= gap <= MAX_GAP:
                edges.append((gap, terminal["arrival"], previous_no, following_no))
    successor, predecessor = {}, {}
    for _, _, previous_no, following_no in sorted(edges):
        if previous_no not in successor and following_no not in predecessor:
            successor[previous_no], predecessor[following_no] = following_no, previous_no
    chains, seen = [], set()
    for start in [no for no in range(len(trips)) if no not in predecessor]:
        chain, current = [], start
        while current not in seen:
            seen.add(current); chain.append(current)
            if current not in successor:
                break
            current = successor[current]
        chains.append(chain)
    chains.extend([[no] for no in range(len(trips)) if no not in seen])
    return chains


def chain_stops(trips, chain):
    combined = []
    for piece, trip_no in enumerate(chain):
        stops = [{**stop, "piece": piece} for stop in trips[trip_no]["stops"]]
        if combined and combined[-1]["station"] == stops[0]["station"]:
            combined[-1]["departure"] = stops[0]["departure"]
            combined.extend(stops[1:])
        else:
            combined.extend(stops)
    return combined


def direction_sector(origin, following, coordinates):
    if origin not in coordinates or following not in coordinates:
        return 0
    lat1, lon1 = coordinates[origin]; lat2, lon2 = coordinates[following]
    dx = (lon2 - lon1) * math.cos(math.radians(lat1)); dy = lat2 - lat1
    return round((math.degrees(math.atan2(dx, dy)) % 360) / 45) % 8


def build_life_rows(db, trips, coordinates):
    sql = """INSERT INTO life_raw VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(origin,destination,route,direction,minutes) DO UPDATE SET
      stop_count=MIN(stop_count,excluded.stop_count),
      confidence=CASE WHEN confidence='exact' OR excluded.confidence='exact' THEN 'exact' ELSE 'estimated' END"""
    inserted, buffer = 0, []
    for chain in connect_trips(trips):
        stops, route = chain_stops(trips, chain), trips[chain[0]]["route"]
        for origin_no, origin in enumerate(stops[:-1]):
            following = stops[origin_no + 1]
            direction = direction_sector(origin["station"], following["station"], coordinates)
            for destination_no in range(origin_no + 1, len(stops)):
                destination = stops[destination_no]
                minutes = destination["arrival"] - origin["departure"]
                if minutes <= 0:
                    continue
                if minutes > 60:
                    break
                if destination["station"] == origin["station"]:
                    continue
                confidence = "exact" if origin["piece"] == destination["piece"] else "estimated"
                buffer.append((origin["station"], destination["station"], route, direction,
                               minutes, destination_no - origin_no, confidence))
                if len(buffer) >= 20_000:
                    db.executemany(sql, buffer); inserted += len(buffer); buffer.clear()
    if buffer:
        db.executemany(sql, buffer); inserted += len(buffer)
    db.executescript("""
    CREATE TABLE life_access AS
    WITH direction_min AS (
      SELECT origin,destination,route,direction,MIN(minutes) AS min_minutes FROM life_raw
      GROUP BY origin,destination,route,direction),
    ranked AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY origin,destination,route
      ORDER BY min_minutes,direction) AS rank FROM direction_min)
    SELECT raw.origin,raw.destination,raw.route,raw.minutes,raw.stop_count,raw.confidence
    FROM life_raw raw JOIN ranked best USING(origin,destination,route,direction) WHERE best.rank=1;
    CREATE UNIQUE INDEX idx_life_unique ON life_access(origin,destination,route,minutes);
    CREATE INDEX idx_life_origin ON life_access(origin,minutes);
    DROP TABLE life_raw;
    """)
    return inserted, db.execute("SELECT COUNT(*) FROM life_access").fetchone()[0]


def build(directory=".", output=OUT):
    directory, output = Path(directory), Path(output)
    coordinates, timetables, paths, parts = read_sources(directory)
    if not paths or not timetables["weekday"]:
        raise RuntimeError("公開時刻表JSONが見つからないか、平日列車がありません")
    temporary = output.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(temporary) as db:
        create_schema(db)
        stop_count = insert_trips(db, timetables)
        raw_count, life_count = build_life_rows(db, timetables["weekday"], coordinates)
        db.executemany("INSERT INTO metadata VALUES(?,?)", [
            ("version", VERSION), ("max_gap", str(MAX_GAP)),
            ("source_files", ",".join(path.name for path in paths)),
            ("trip_count", str(sum(map(len, timetables.values())))),
            ("stop_count", str(stop_count)), ("life_count", str(life_count))])
        db.commit(); db.execute("VACUUM")
    temporary.replace(output)
    save_gzip(output.parent / METADATA_OUT.name, {"parts": parts})
    print(f"生成完了: {output} / 停車{stop_count:,}件 / 生活圏{life_count:,}件（候補{raw_count:,}件）")
    return output


def self_test():
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        positions = {"浜松町": (35.65,139.75), "品川": (35.62,139.74),
            "大崎": (35.61,139.72), "目黒": (35.63,139.71), "恵比寿": (35.65,139.71),
            "東京": (35.68,139.77), "池袋": (35.73,139.71)}
        stations = [{"name": name, "lat": lat, "lon": lon}
                    for name, (lat, lon) in positions.items()]
        trips = [
            {"operator": "JR", "route": "山手線", "stops": [["浜松町","10:00","10:00"],
             ["品川","10:07","10:08"],["大崎","10:10","10:10"]]},
            {"operator": "JR", "route": "山手線", "stops": [["大崎","10:10","10:10"],
             ["目黒","10:13","10:13"],["恵比寿","10:16","10:16"]]},
            {"operator": "JR", "route": "山手線", "stops": [["浜松町","10:00","10:00"],
             ["東京","10:08","10:08"],["池袋","10:30","10:30"],["恵比寿","10:49","10:49"]]},
        ]
        data = {"stations": stations, "timetables": {"weekday": trips, "saturday": [], "sunday": []}}
        save_gzip(folder / "direct_timetable_basic.json.gz", data)
        (folder / "build_config.json").write_text('{"jr_enabled":false}')
        output = build(folder, folder / "test.sqlite")
        assert (folder / METADATA_OUT.name).exists()
        with sqlite3.connect(output) as db:
            values = [row[0] for row in db.execute("SELECT minutes FROM life_access WHERE origin='浜松町' AND destination='恵比寿'")]
        assert 16 in values and 49 not in values, values
        print("SELF TEST: OK / 浜松町→恵比寿 16分、反対回り49分を除外")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default=".")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else build(args.directory, args.output)
