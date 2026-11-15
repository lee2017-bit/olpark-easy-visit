"""site/data/site.json 생성 (정적 사이트가 읽는 데이터).

사용: python -m build.build_site
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd

from analysis.features import event_days
from analysis.risk import VENUE_KO, upcoming
from olpark.common import PROCESSED, ROOT

SITE = ROOT / "site"
KST = dt.timezone(dt.timedelta(hours=9))

VENUE_ACCESS = {  # 기관 주차 안내·공지 기준
    "kspo_dome": {"lot": "P5 (북2문·동2문·남2문)", "disabled_spaces": 10, "walk": "주차장에서 1분"},
    "olympic_hall": {"lot": "P2·올림픽홀 지하 (동2문)", "disabled_spaces": 5, "walk": "1~2분"},
    "handball": {"lot": "P6 (동2문·남2문)", "disabled_spaces": 3, "walk": "1~2분"},
    "lawn88": {"lot": "동2문 쪽 주차장", "disabled_spaces": None, "walk": "공지에 지정 장애인 주차 구역 없음"},
}


def _fmt_h(h) -> str | None:
    if h is None or pd.isna(h):
        return None
    return f"{int(h):02d}:{int(round((h % 1) * 60)):02d}"


def access_tips(grade: str, offday: bool, evs: pd.DataFrame, elev_text: str, full_h: float) -> list[str]:
    """그날 교통약자·동행자에게 보여줄 짧은 안내 문장들."""
    tips = []
    if grade == "높음":
        tips.append(f"자가용은 권하지 않습니다. 비슷한 조건의 날에는 대개 {int(full_h)}시 전후부터 주차장이 찼습니다.")
    elif grade == "보통" and offday:
        tips.append(f"자가용이라면 {int(full_h)}시 이전 도착을 권합니다. 이후에는 장애인 구역까지 들어가기 어려울 수 있습니다.")
    else:
        tips.append("평일이라 주차 여유가 있는 편입니다." if not offday else "공연이 없는 날이라 비교적 여유가 있을 것으로 보입니다(기록 적음).")
    seen = set()
    for e in evs.itertuples():
        if e.venue in seen:
            continue
        seen.add(e.venue)
        v = VENUE_ACCESS[e.venue]
        spaces = f"장애인 주차 {v['disabled_spaces']}면" if v["disabled_spaces"] else "지정 장애인 주차 안내 없음"
        start = f" {_fmt_h(e.start_h)}" if _fmt_h(e.start_h) else ""
        tips.append(f"{VENUE_KO[e.venue]}{start}: 가까운 주차장 {v['lot']}, {spaces}")
    tips.append(f"지하철 엘리베이터 출구: {elev_text}")
    if any((h or 0) >= 16 for h in evs.start_h.tolist()):
        tips.append("공원 휠체어 대여는 19시에 끝나고 3시간 한도라 저녁 공연 중에는 쓰기 어렵습니다. 개인 휠체어를 권합니다.")
    return tips


def _km(a, b) -> float:
    """두 지점 직선거리(km, 구면 근사)."""
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def map_points(elev: list[dict]) -> dict | None:
    """지도용 좌표: 공연장(OSM)과, 서울교통공사 데이터에서 엘리베이터가 있는 출구(OSM 출구 좌표)."""
    f = ROOT / "data" / "static" / "map_points.json"
    if not f.exists():
        return None
    mp = json.loads(f.read_text(encoding="utf-8"))
    exits = []
    for e in elev:
        hit = [x for x in mp["exits"] if x["station"] == e["station"] and x["exit"] == str(e["exit"])]
        if hit:
            exits.append({"line": e["line"], "station": e["station"], "exit": str(e["exit"]),
                          "lat": hit[0]["lat"], "lon": hit[0]["lon"], "osm": hit[0]["osm"]})
    venues = []
    for k, v in mp["venues"].items():
        near = min(exits, key=lambda x: _km(v, x)) if exits else None
        venues.append({"key": k, "name": VENUE_KO[k], "lat": v["lat"], "lon": v["lon"], "osm": v["osm"],
                       **VENUE_ACCESS[k],
                       "nearest_elevator": None if not near else
                       {"label": f"{near['line']} {near['station']}역 {near['exit']}번", "km": round(_km(v, near), 1)}})
    return {"venues": venues, "elevator_exits": exits, "attribution": mp["attribution"]}


def build(days_ahead: int = 60) -> dict:
    u, stats = upcoming(days_ahead)
    ed = event_days()
    ed = ed[ed.date.isin(u.date)]
    acc0 = json.loads((PROCESSED / "accessibility.json").read_text(encoding="utf-8"))
    elev_text = ", ".join(f"{x['lineNm']} {x['stnNm']}역 {x.get('vcntEntrcNo')}번"
                          for x in acc0["elevators"] if "외부" in x["fcltNm"]) or "정보 없음"
    days = []
    for _, r in u.iterrows():
        evs = ed[ed.date == r.date].sort_values("start_h")
        if not (r.offday or len(evs)):
            continue
        full_h = int(stats["first_full_h_median"])
        car = "avoid" if r.grade == "높음" else ("early" if (r.grade == "보통" and r.offday) else "ok")
        days.append({
            "date": r.date.strftime("%Y-%m-%d"),
            "weekday": "월화수목금토일"[r.date.dayofweek],
            "offday": r.offday, "holiday": r.holiday,
            "grade": r.grade, "basis": r.basis, "m": int(r.m), "n": int(r.n),
            "car": car, "arrive_by": full_h if car != "ok" else None,
            "evening": any((h or 0) >= 16 for h in evs.start_h.tolist()),
            "rain_pop": None if pd.isna(r.pop_max) else int(r.pop_max),
            "events": [{"title": e.title, "venue": VENUE_KO[e.venue], "venue_key": e.venue,
                        "start": _fmt_h(e.start_h)} for e in evs.itertuples()],
            "tips": access_tips(r.grade, r.offday, evs, elev_text, stats["first_full_h_median"]),
        })
    acc = json.loads((PROCESSED / "accessibility.json").read_text(encoding="utf-8"))
    st = acc["agency_static"]
    elev = [{"line": x["lineNm"], "station": x["stnNm"], "where": x.get("dtlPstn"),
             "exit": x.get("vcntEntrcNo")} for x in acc["elevators"] if "외부" in x["fcltNm"]]
    knto = acc.get("barrier_free_knto", {})
    data = {
        "map": map_points(elev),
        "generated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
        "days": days,
        "access": {
            "subway_elevators": elev,
            "subway_note": "9호선(올림픽공원역·한성백제역)은 운영사가 달라 이 데이터에 없습니다.",
            "park_exit_guidance": st["subway_exit_guidance"]["text"],
            "wheelchair_rental": st["wheelchair_rental"],
            "wheelchair_entry_route": st["wheelchair_entry_route"]["text"],
            "disabled_parking_total_agency": sum(st["disabled_parking_by_spot"]["spots"].values()),
            "disabled_parking_knto": knto.get("parking"),
            "restroom_knto": knto.get("restroom"),
            "stroller_knto": knto.get("stroller"),
            "venues": {VENUE_KO[k]: v for k, v in VENUE_ACCESS.items()},
        },
        "sources": [
            {"name": "한국체육산업개발 주차장 혼잡도 정보 (공공데이터포털)", "url": "https://www.data.go.kr/data/15164156/fileData.do"},
            {"name": "한국체육산업개발 올림픽공원 공연정보 (문화공공데이터광장)", "url": "https://www.data.go.kr/data/3037877/openapi.do"},
            {"name": "올림픽공원 홈페이지 공연 일정·주차 안내·편의시설", "url": "https://www.ksponco.or.kr/olympicpark/"},
            {"name": "서울교통공사 교통약자이용정보", "url": "https://www.data.go.kr/data/15143843/openapi.do"},
            {"name": "한국관광공사 무장애 여행 정보", "url": "https://www.data.go.kr/"},
            {"name": "기상청 단기예보·ASOS, 한국천문연구원 특일 정보", "url": "https://www.data.go.kr/"},
            {"name": "지도·위치: © OpenStreetMap 기여자 (ODbL)", "url": "https://www.openstreetmap.org/copyright"},
        ],
    }
    out = SITE / "data" / "site.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    d = build()
    print("days:", len(d["days"]), "| generated:", d["generated_at"])
    print(json.dumps(d["days"][:2], ensure_ascii=False, indent=1)[:1200])
