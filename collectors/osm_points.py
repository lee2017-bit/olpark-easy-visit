"""지도에 찍을 위치(공연장·지하철 출구) 좌표를 OpenStreetMap에서 받아 data/static/map_points.json에 저장.

좌표는 추정하지 않고 OSM 요소(id)의 실제 좌표만 씁니다. 위치가 바뀔 일이 드물어 자동 갱신에는 넣지 않았고,
필요할 때 한 번 실행합니다. 주차장은 기관 번호(P5 등)와 OSM 이름이 맞지 않아 지도에 찍지 않습니다.

사용: python -m collectors.osm_points
데이터: © OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright)
"""
import datetime as dt
import json
import time
import urllib.parse
import urllib.request

from olpark.common import ROOT

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]

VENUES = {  # 공연장 키 → OSM way id
    "kspo_dome": 75956855,     # 올림픽체조경기장 (KSPO DOME)
    "olympic_hall": 75956846,  # 올림픽홀
    "handball": 75956853,      # SK올림픽핸드볼경기장 (티켓링크 라이브 아레나)
    "lawn88": 469354406,       # 88잔디마당
}
EXITS = {  # (역, 출구 번호) → OSM node id (railway=subway_entrance)
    ("올림픽공원", "1"): 3401446008, ("올림픽공원", "2"): 3401446010,
    ("올림픽공원", "3"): 3401446009, ("올림픽공원", "4"): 8227072104,
    ("몽촌토성", "1"): 5873076167, ("몽촌토성", "2"): 3401171485, ("몽촌토성", "3"): 3401171486,
    ("몽촌토성", "4"): 3401171487, ("몽촌토성", "5"): 3401171488,
    ("한성백제", "1"): 6102706379, ("한성백제", "2"): 6102706378,
    ("한성백제", "3"): 6102706377, ("한성백제", "4"): 6102706376,
}
OUT = ROOT / "data" / "static" / "map_points.json"


def overpass(query: str) -> dict:
    last = None
    for attempt in range(4):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(url + "?" + urllib.parse.urlencode({"data": query}),
                                             headers={"User-Agent": "olpark-easy-visit (open-source; github)"})
                return json.loads(urllib.request.urlopen(req, timeout=90).read())
            except Exception as e:  # 미러가 자주 바빠서 번갈아 재시도
                last = e
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Overpass 실패: {last}")


def main():
    ways = ",".join(str(i) for i in VENUES.values())
    nodes = ",".join(str(i) for i in EXITS.values())
    d = overpass(f"[out:json][timeout:60];(way(id:{ways});node(id:{nodes}););out center tags;")
    by = {(e["type"], e["id"]): e for e in d["elements"]}

    def pos(kind, i):
        e = by.get((kind, i))
        if not e:
            raise SystemExit(f"OSM {kind} {i} 없음")
        c = e.get("center", e)
        return round(c["lat"], 6), round(c["lon"], 6), e.get("tags", {})

    venues = {}
    for k, i in VENUES.items():
        lat, lon, t = pos("way", i)
        venues[k] = {"lat": lat, "lon": lon, "osm": f"way/{i}", "osm_name": t.get("name")}
    exits = []
    for (stn, ref), i in EXITS.items():
        lat, lon, t = pos("node", i)
        if t.get("ref") != ref:
            raise SystemExit(f"출구 번호 불일치: {stn} {ref} vs OSM {t.get('ref')}")
        exits.append({"station": stn, "exit": ref, "lat": lat, "lon": lon, "osm": f"node/{i}"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetched": dt.date.today().isoformat(),
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "venues": venues, "exits": exits}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", OUT, "| 공연장", len(venues), "| 출구", len(exits))


if __name__ == "__main__":
    main()
