"""site/data/site.json 생성 (정적 사이트가 읽는 데이터).

사용: python -m build.build_site
"""
from __future__ import annotations

import datetime as dt
import json
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


def build(days_ahead: int = 60) -> dict:
    u, stats = upcoming(days_ahead)
    ed = event_days()
    ed = ed[ed.date.isin(u.date)]
    days = []
    for _, r in u.iterrows():
        evs = ed[ed.date == r.date].sort_values("start_h")
        if not (r.offday or len(evs)):
            continue
        days.append({
            "date": r.date.strftime("%Y-%m-%d"),
            "weekday": "월화수목금토일"[r.date.dayofweek],
            "offday": r.offday, "holiday": r.holiday,
            "grade": r.grade, "basis": r.basis,
            "rain_pop": None if pd.isna(r.pop_max) else int(r.pop_max),
            "events": [{"title": e.title, "venue": VENUE_KO[e.venue], "venue_key": e.venue,
                        "start": _fmt_h(e.start_h)} for e in evs.itertuples()],
        })
    acc = json.loads((PROCESSED / "accessibility.json").read_text(encoding="utf-8"))
    st = acc["agency_static"]
    elev = [{"line": x["lineNm"], "station": x["stnNm"], "where": x.get("dtlPstn"),
             "exit": x.get("vcntEntrcNo")} for x in acc["elevators"] if "외부" in x["fcltNm"]]
    knto = acc.get("barrier_free_knto", {})
    data = {
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
