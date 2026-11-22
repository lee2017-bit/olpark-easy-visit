"""site/data/site.json 생성 (정적 사이트가 읽는 데이터).

구성: 공연 있는 날마다 공연 목록 + 여정 단계(예매 → 가는 길 → 주차 → 공원 안 → 공연장 안 → 집에 갈 때)별 안내.
- 늘 같은 안내: data/static/access_guide.json (공식 페이지·공공데이터·기사·후기, 출처 표시)
- 그날·그 공연에 따라 바뀌는 안내: 아래 day_items()에서 공연정보·지하철 엘리베이터·2025 입출차·장애인콜택시 자료로 계산
사용: python -m build.build_site
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re

import pandas as pd

from analysis.calltaxi_wait import run as calltaxi_run
from analysis.features import parse_start_times
from analysis.risk import upcoming
from build import posters
from olpark.common import PROCESSED, ROOT

SITE = ROOT / "site"
STATIC = ROOT / "data" / "static"
KST = dt.timezone(dt.timedelta(hours=9))
VENUE_BY_CODE = {"01": "olympic_hall", "02": "kspo_dome", "03": "handball", "04": "woori_art_hall",
                 "06": "lawn88", "07": "muse_live"}
CALLTAXI_VENUES = {"kspo_dome", "handball", "olympic_hall"}  # 행정동 오륜동, analysis.calltaxi_wait 기준
PARKING_PAGE = "https://www.ksponco.or.kr/online/main/parking.do"


def _fmt_h(h) -> str | None:
    if h is None or pd.isna(h):
        return None
    m = int(round(h * 60)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def run_minutes(nd) -> int | None:
    """'총 130분', '약 120분 (인터미션 20분)', '120' → 분."""
    if not isinstance(nd, str):
        return None
    m = re.search(r"(\d{2,3})\s*분", nd) or re.fullmatch(r"\s*(\d{2,3})\s*", nd)
    return int(m.group(1)) if m else None


def vendor_of(link, guide: dict) -> dict | None:
    if not isinstance(link, str):
        return None
    for k, v in guide["ticketing"].items():
        if any(s in link for s in v["match"]):
            return {"key": k, **{x: v.get(x) for x in ("name", "phone", "hours", "how", "src", "kind", "url")}}
    return None


def site_events(start: dt.date, end: dt.date, guide: dict) -> pd.DataFrame:
    """공연장 6곳의 공연을 날짜별 한 줄로 (오래 하는 공연 포함). 시작 시각은 그 요일의 가장 이른 회차."""
    ev = pd.read_csv(PROCESSED / "events_homepage.csv", dtype=str)
    ev = ev[ev.plcCd.isin(VENUE_BY_CODE)]
    rows = []
    for r in ev.itertuples():
        b, e = pd.Timestamp(r.beginDt).date(), pd.Timestamp(r.endDt).date()
        if e < start or b > end:
            continue
        st = parse_start_times(r.tm)
        for d in pd.date_range(max(b, start), min(e, end)):
            h = st.get(d.dayofweek, st.get(None, min(st.values()) if st else None))
            if st and d.dayofweek not in st and None not in st and (e - b).days > 6:
                continue  # 오래 하는 공연에서 시간표에 없는 요일(휴관일)은 뺌
            rows.append({"date": d.normalize(), "venue": VENUE_BY_CODE[r.plcCd], "start_h": h, "title": r.title,
                         "tm": r.tm, "run": run_minutes(r.ndTm) or 0, "age": r.seeAge, "inquiry": r.nqry,
                         "link": r.evtLink, "vendor": vendor_of(r.evtLink, guide), "seq": str(r.evtSeq),
                         "file": getattr(r, "fileNm", None)})
    return pd.DataFrame(rows)


def _km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def elevator_exits(acc: dict) -> list[dict]:
    """지상 엘리베이터가 있는 출구: 1~8호선은 서울교통공사 API, 9호선은 승강기 현황 파일."""
    out = [{"line": x["lineNm"], "station": x["stnNm"], "exit": str(x.get("vcntEntrcNo")), "where": x.get("dtlPstn"),
            "src": "서울교통공사 교통약자이용정보"} for x in acc["elevators"] if "외부" in x["fcltNm"]]
    f = STATIC / "line9_elevators.csv"
    if f.exists():
        for r in pd.read_csv(f).itertuples():
            m = re.match(r"(\d+)번 출구", str(r._5))
            if m:
                out.append({"line": "9호선", "station": str(r.역명).replace("(9)", ""), "exit": m.group(1),
                            "where": str(r.설치위치), "src": "9호선 2·3단계 승강기 현황"})
    mp = json.loads((STATIC / "map_points.json").read_text(encoding="utf-8"))
    for x in out:
        hit = [p for p in mp["exits"] if p["station"] == x["station"] and p["exit"] == x["exit"]]
        if hit:
            x.update(lat=hit[0]["lat"], lon=hit[0]["lon"], osm=hit[0]["osm"])
    return out


def exit_wave_stats() -> dict | None:
    f = PROCESSED / "exit_wave_2025.csv"
    if not f.exists():
        return None
    t = pd.read_csv(f)
    k = t[(t.kspo_dome == 1) & (t.first_start_h >= 16)]
    full = k[k.full_count]
    return {"n": int(len(k)), "q25": float(k.peak_after_start_h.quantile(.25)),
            "q75": float(k.peak_after_start_h.quantile(.75)), "median": float(k.peak_after_start_h.median()),
            "peak30": int(full.peak_30min.median()) if len(full) else None}


def calltaxi_stats() -> dict | None:
    try:
        t, n_show = calltaxi_run()
    except FileNotFoundError:
        return None
    o = t[t.출발동 == "오륜동"].set_index("밤")
    s, n = o.loc["공연 있는 밤"], o.loc["그 밖의 밤"]
    return {"median": round(float(s["대기 중앙값(분)"])), "p75": round(float(s["대기 상위 25%(분)"])),
            "cancel": round(float(s["취소 비율"]) * 100), "median_other": round(float(n["대기 중앙값(분)"])),
            "n": int(s["건수"]), "nights": int(n_show)}


def _hm(h: float) -> str:
    return f"{int(h)}시간" + (f" {int(round(h % 1 * 60))}분" if h % 1 else "")


def day_items(r, evs: pd.DataFrame, guide: dict, exits: list, venues_xy: dict, wave, taxi, today) -> dict:
    """그날·그 공연에 따라 바뀌는 안내. 각 항목에 venue가 있으면 그 공연장 공연을 고를 때만 보임."""
    G = guide["venues"]
    it = {k: [] for k in ("ticket", "go", "park", "inpark", "venue", "home")}
    # 「이 날 꼭 알아야 할 것」 후보: 판단을 바꾸는 것만, rank가 클수록 위. 브라우저가 실시간 항목과 합쳐 3개만 보여 줌.
    # group이 같으면 하나만, when="before"는 공연 당일이 지나면(당일 포함) 빠짐.
    must: list[dict] = []
    W, ALL_MOVE = ["wheel"], ["wheel", "stroller", "slow"]
    seen_v, seen_vendor = set(), set()
    for e in evs.itertuples():
        g = G[e.venue]
        vd = e.vendor if isinstance(e.vendor, dict) else None
        if vd and (vd["key"], e.venue) not in seen_vendor:
            seen_vendor.add((vd["key"], e.venue))
            it["ticket"].append({"venue": e.venue, "who": W, "kind": vd.get("kind"), "src": vd["src"], "url": vd.get("url"),
                                 "t": f"{vd['name']}: " + ("휠체어석 예매법 미공개" if vd.get("kind") == "gap" else "휠체어석 전화 예매"),
                                 "s": f"{g['short']} · {vd['how']} · 고객센터 {vd['phone']}" + (f" ({vd['hours']})" if vd.get("hours") else "")
                                      + (f" · 공연 문의 {e.inquiry}" if isinstance(e.inquiry, str) else "")})
            gap = vd.get("kind") == "gap"
            must.append({"rank": 70 if gap else 76, "group": "ticket", "when": "before", "who": W, "src": vd["src"],
                        "url": vd.get("url"), "kind": "gap" if gap else "warn", "venue": e.venue,
                        "t": f"{vd['name']} 휠체어석 예매법 미공개" if gap else "휠체어석은 전화로 예매",
                        "do": f"고객센터 {vd['phone']}에 문의" if gap else f"{vd['name']} {vd['phone']}",
                        "more": f"{g['short']} · {vd['how']}" + (f" · 상담 {vd['hours']}" if vd.get("hours") else "")})
        if e.venue in seen_v:
            continue
        seen_v.add(e.venue)
        if g.get("key"):
            inq = e.inquiry if isinstance(e.inquiry, str) else "공연 공지의 문의처"
            must.append({**g["key"], "group": f"venue:{e.venue}", "venue": e.venue,
                        "more": g["key"]["more"].replace("{inquiry}", inq)})
        # 가는 길: 가까운 엘리베이터 출구
        if e.venue in venues_xy:
            grp: dict = {}
            for x in (x for x in exits if "lat" in x):
                k = (x["line"], x["station"])
                grp.setdefault(k, []).append((round(_km(venues_xy[e.venue], x), 1), x["exit"]))
            near = sorted(grp.items(), key=lambda kv: min(kv[1]))[:2]
            if near:
                it["go"].append({"venue": e.venue, "who": ALL_MOVE, "src": "공공데이터", "kind": "tip",
                                 "t": "엘리베이터 출구: " + " · ".join(f"{ln} {'·'.join(sorted(n for _, n in v))}번" for (ln, st), v in near),
                                 "s": f"{g['short']}에서 가까운 순: " + ", ".join(f"{ln} {st}역 직선 {min(v)[0]}km" for (ln, st), v in near)
                                      + " (걷는 길은 더 길어요)"})
        if g.get("route_review"):
            it["go"].append({"venue": e.venue, "who": ["wheel"], **g["route_review"]})
        # 주차
        if g.get("lot"):
            spots = guide.get("_spots", {}).get(g.get("lot_key"))
            it["park"].append({"venue": e.venue, "who": ALL_MOVE, "src": "공식",
                               "url": "https://www.ksponco.or.kr/olympicpark/parkingInfo?mid=a20111000000",
                               "t": f"가까운 주차장 {g['lot']}" + (f" · 장애인 {spots}면" if spots else ""),
                               "s": f"{g['short']} 기준" + (f" · {g['lot_gates']}" if g.get("lot_gates") else "")
                                    + ("" if spots else " · 지정 장애인 주차 안내 없음")
                                    + (f" · 공연장까지 {g['walk']}" if g.get("walk") else "")})
        # 공연장 안
        for key, who in (("seats", W), ("view", W), ("entry", W), ("caption", ["hearing"]), ("notice", [])):
            if g.get(key):
                it["venue"].append({"venue": e.venue, "who": who, **g[key],
                                    "t": g[key]["t"]})
        bf = g.get("bf") or g.get("bf_text")
        if bf:
            it["venue"].append({"venue": e.venue, "who": ["wheel", "stroller", "slow", "vision"], "src": "공공데이터",
                                "url": "https://www.data.go.kr/data/15014781/fileData.do", "kind": None if g.get("bf") else "gap",
                                "t": f"무장애(BF) 인증: {bf.split(' (')[0]}" if g.get("bf") else "무장애(BF) 인증 없음",
                                "s": f"{g['short']} · 장애물 없는 생활환경(BF) 인증 " + (bf if g.get("bf") else "목록에 없음")})
    # 집에 갈 때: 끝나는 시각, 출차가 몰리는 때, 콜택시 대기, 늦은 출차
    late = False
    for e in evs.sort_values("start_h").itertuples():
        g = G[e.venue]
        if e.start_h is None or pd.isna(e.start_h):
            continue
        end_h = e.start_h + e.run / 60 if e.run else None
        if end_h:
            it["home"].append({"venue": e.venue, "who": [], "src": "공식",
                               "t": f"{_fmt_h(end_h)} 무렵 끝나요",
                               "s": f"{g['short']} {_fmt_h(e.start_h)} 시작 · 공연 {int(e.run)}분. 앙코르 등으로 늦어질 수 있어요. 그날 가장 이른 회차 기준"})
        if e.venue == "kspo_dome" and wave and e.start_h >= 16:
            a, b = e.start_h + wave["q25"], e.start_h + wave["q75"]
            late |= b >= 21.5
            it["home"].append({"venue": e.venue, "who": ALL_MOVE, "kind": "warn", "src": "분석",
                               "url": "https://www.data.go.kr/data/15159093/openapi.do",
                               "t": f"출차 혼잡 {_fmt_h(a)}~{_fmt_h(b)}",
                               "s": f"2025년 KSPO DOME 저녁 공연 {wave['n']}일, 시작 {_hm(wave['q25'])}~{_hm(wave['q75'])} 뒤에 "
                                    f"가장 많이 나갔어요" + (f" (가장 붐빈 30분에 약 {wave['peak30']}대)" if wave.get("peak30") else "")
                                    + ". 휠체어 승하차에 시간이 걸리면 이때를 피하세요"})
            must.append({"rank": 50, "group": "exit_peak", "who": ALL_MOVE, "src": "분석", "kind": "warn", "venue": e.venue,
                        "url": "https://www.data.go.kr/data/15159093/openapi.do",
                        "t": f"공연 뒤 출차 혼잡 {_fmt_h(a)}~{_fmt_h(b)}",
                        "do": "차로 왔다면 이 시간 피해서",
                        "more": f"2025년 KSPO DOME 저녁 공연 {wave['n']}일 기록. 휠체어 승하차에 시간이 걸리면 이때를 피하세요"})
        elif end_h:
            late |= end_h >= 21.5
    if taxi and any(v in CALLTAXI_VENUES and (h or 0) >= 16 for v, h in zip(evs.venue, evs.start_h)):
        it["home"].append({"who": ["wheel"], "kind": "warn", "src": "분석", "url": "https://www.data.go.kr/data/15115859/fileData.do",
                           "t": f"공연 뒤 콜택시 대기 {taxi['median']}분",
                           "s": f"중간값 (공연 없는 밤 {taxi['median_other']}분). 4건 중 1건은 {taxi['p75']}분 넘게 기다렸고 {taxi['cancel']}%는 취소됐어요 "
                                f"(2025년 탑승내역, 공연 있는 밤 20시 이후 공원 쪽 출발 {taxi['n']}건)"})
        must.append({"rank": 80, "group": "taxi", "who": ["wheel"], "src": "분석", "kind": "warn",
                    "url": "https://www.data.go.kr/data/15115859/fileData.do",
                    "t": f"공연 뒤 콜택시 대기 {taxi['median']}분",
                    "do": f"{taxi['cancel']}% 취소 · 귀가 방법 미리 정하기",
                    "more": f"2025년 공연 있는 밤 20시 이후 공원 쪽 출발 {taxi['n']}건의 중간값이에요 (공연 없는 밤 {taxi['median_other']}분). "
                            f"4건 중 1건은 {taxi['p75']}분 넘게 기다렸어요"})
    if late:
        it["home"].append({"who": [], "kind": "warn", "src": "공식",
                           "url": "https://www.ksponco.or.kr/olympicpark/menu.es?mid=a20101000000",
                           "t": "22:30 넘으면 동2문으로 출차",
                           "s": "북2문·남2문 출차는 22:30까지, 동2문은 24시간. 공원 안 걷기는 22:00까지(광장은 24:00까지)"})
        must.append({"rank": 74, "group": "late", "who": [], "src": "공식", "kind": "warn",
                    "url": "https://www.ksponco.or.kr/olympicpark/menu.es?mid=a20101000000",
                    "t": "북2·남2문 출차 22:30 마감",
                    "do": "늦으면 동2문(24시간)으로",
                    "more": "공원 안 걷기는 22:00까지(광장은 24:00까지)"})
    if any((h or 0) >= 16 for h in evs.start_h.fillna(0)):
        must.append({"rank": 70, "group": "rent", "who": ["wheel", "slow"], "src": "공식", "kind": "warn",
                    "url": "https://www.ksponco.or.kr/olympicpark/menu.es?mid=a20106010000",
                    "t": "공원 휠체어 대여 19시 마감",
                    "do": "개인 휠체어 챙기기",
                    "more": "한 번에 3시간이라 저녁 공연 중엔 반납할 수 없어요"})
    # 주차: 2025 기록과 기관 안내
    it["park"].append({"who": [], "src": "분석", "url": "https://www.data.go.kr/data/15164156/fileData.do",
                       "t": (f"평일 만차는 드물어요 ({int(r.m)}/{int(r.n)}일)" if not r.offday
                             else f"지난해 이맘때 {int(r.n)}일 중 {int(r.m)}일 만차" if r.n else "지난해 주차 기록"),
                       "s": r.basis})
    if r.offday and r.n and r.m / r.n >= 0.3:
        must.append({"rank": 56, "group": "full", "who": [], "src": "분석", "kind": "warn",
                    "url": "https://www.data.go.kr/data/15164156/fileData.do",
                    "t": f"주차장 찰 수 있어요 ({int(r.m)}/{int(r.n)}일)",
                    "do": "일찍 오거나 지하철로",
                    "more": f"2025년 {r.date.month}월 공연 있는 주말·공휴일 {int(r.n)}일 중 {int(r.m)}일 주차장이 찼어요. 출발 직전엔 「지금 주차장」을 보세요"})
    near_weekend = r.offday and (r.date.date() - today).days <= 7
    it["park"].append({"who": [], "kind": "tip", "src": "공식", "url": PARKING_PAGE,
                       "t": "실시간 주차는 맨 위 「지금 주차장」",
                       "s": ("기관 홈페이지 숫자를 그대로 불러와요. " +
                             ("이 날 기관 예상 이용률은 기관 홈페이지에서 날짜를 골라 볼 수 있어요" if near_weekend
                              else "기관 예상 이용률은 주말 공연일에, 며칠 전부터 나와요" if r.offday
                              else "기관 예상 이용률은 주말에만 나와요"))})
    if r.pop_max is not None and not pd.isna(r.pop_max) and r.pop_max >= 30:
        it["go"].append({"who": [], "kind": "tip", "src": "공공데이터",
                         "t": f"비 {int(r.pop_max)}%: 우비·휠체어 덮개",
                         "s": "티켓·굿즈 부스가 야외에 있었다는 후기가 있어요"})
        must.append({"rank": 62 if r.pop_max >= 60 else 52, "group": "rain", "who": [], "src": "공공데이터", "kind": "tip",
                    "url": "https://www.data.go.kr/data/15084084/openapi.do",
                    "t": f"비 예보 {int(r.pop_max)}%",
                    "do": "우비·휠체어 덮개 챙기기",
                    "more": "티켓·굿즈 부스가 야외에 있었다는 후기가 있어요"})
    return {k: v for k, v in it.items() if v}, sorted(must, key=lambda x: -x["rank"])


def build(days_ahead: int = 60) -> dict:
    guide = json.loads((STATIC / "access_guide.json").read_text(encoding="utf-8"))
    acc = json.loads((PROCESSED / "accessibility.json").read_text(encoding="utf-8"))
    guide["_spots"] = acc["agency_static"]["disabled_parking_by_spot"]["spots"]
    today = dt.datetime.now(KST).date()
    u, _ = upcoming(days_ahead, today)
    ev = site_events(today, today + dt.timedelta(days=days_ahead), guide)
    exits = elevator_exits(acc)
    mp = json.loads((STATIC / "map_points.json").read_text(encoding="utf-8"))
    venues_xy = mp["venues"]
    wave, taxi = exit_wave_stats(), calltaxi_stats()
    days = []
    for _, r in u.iterrows():
        evs = ev[ev.date == r.date].sort_values("start_h") if len(ev) else ev
        if not len(evs):
            continue
        days.append({
            "date": r.date.strftime("%Y-%m-%d"), "weekday": "월화수목금토일"[r.date.dayofweek],
            "offday": bool(r.offday), "holiday": bool(r.holiday),
            "shows": [{"title": e.title, "venue_key": e.venue, "venue": guide["venues"][e.venue]["short"],
                       "start": _fmt_h(e.start_h), "end": _fmt_h(e.start_h + e.run / 60) if e.run and e.start_h is not None
                       and not pd.isna(e.start_h) else None, "run": int(e.run) or None, "tm": e.tm, "age": e.age,
                       "inquiry": e.inquiry if isinstance(e.inquiry, str) else None, "link": e.link,
                       "vendor": (e.vendor or {}).get("name") if isinstance(e.vendor, dict) else None,
                       "poster": posters.thumb(e.seq, e.file), "page": posters.VIEW_URL.format(e.seq)} for e in evs.itertuples()],
        })
        days[-1]["items"], days[-1]["key"] = day_items(r, evs, guide, exits, venues_xy, wave, taxi, today)
    posters.prune({s["poster"].rsplit("/", 1)[1][:-4] for d in days for s in d["shows"] if s.get("poster")})
    steps = [{k: s[k] for k in ("key", "title", "icon", "items")} for s in guide["steps"]]
    map_venues = [{"key": k, "name": guide["venues"][k]["name"], "short": guide["venues"][k]["short"], **v}
                  for k, v in venues_xy.items() if k in guide["venues"]]
    data = {
        "generated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "who": guide["who"], "steps": steps, "gaps": guide["gaps"], "days": days, "live": guide["live"],
        "subway": {"exits": [{k: x.get(k) for k in ("line", "station", "exit", "where", "lat", "lon", "osm", "src")} for x in exits],
                   "park_guidance": guide["subway"]["park_guidance"]},
        "map": {"venues": map_venues, "attribution": mp["attribution"]},
        "sources": [
            {"name": "한국체육산업개발 올림픽공원 공연정보 (공연 일정·예매처·문의처)", "url": "https://www.data.go.kr/data/3037877/openapi.do"},
            {"name": "한국체육산업개발 입출차정보(전체구역) 2025 — 공연 뒤 출차 시각", "url": "https://www.data.go.kr/data/15159093/openapi.do"},
            {"name": "한국체육산업개발 주차장 혼잡도 정보", "url": "https://www.data.go.kr/data/15164156/fileData.do"},
            {"name": "올림픽공원 홈페이지 (공연장 좌석·주차·편의시설·공지)", "url": "https://www.ksponco.or.kr/olympicpark/"},
            {"name": "올림픽공원 실시간 주차대수·주차장 예상 이용률 (열 때마다 불러옴)", "url": PARKING_PAGE},
            {"name": "올림픽공원 올팍소식 공지 — 공사·통제 (열 때마다 불러옴)", "url": guide["live"]["notice_board"]},
            {"name": "서울교통공사 엘리베이터 가동현황 (10분마다 확인)", "url": "https://www.data.go.kr/data/15143843/openapi.do"},
            {"name": "서울교통공사 교통약자이용정보 (엘리베이터·충전기·화장실·안전발판)", "url": "https://www.data.go.kr/data/15143843/openapi.do"},
            {"name": "서울시메트로9호선 2·3단계 승강기 현황", "url": "https://www.data.go.kr/data/15118716/fileData.do"},
            {"name": "서울시설공단 장애인콜택시 탑승내역 2025", "url": "https://www.data.go.kr/data/15115859/fileData.do"},
            {"name": "장애물 없는 생활환경(BF) 인증 현황", "url": "https://www.data.go.kr/data/15014781/fileData.do"},
            {"name": "한국관광공사 무장애 여행 정보", "url": "https://www.data.go.kr/data/15101897/openapi.do"},
            {"name": "기상청 단기예보, 한국천문연구원 특일 정보", "url": "https://www.data.go.kr/"},
            {"name": "참고: 계단뿌셔클럽 공연장 접근성 후기, 비마이너 공연장 접근성 기사 (후기·기사로 표시)", "url": "https://web.staircrusher.club/bbucle-road/kspo-dome/"},
            {"name": "지도·위치: © OpenStreetMap 기여자 (ODbL)", "url": "https://www.openstreetmap.org/copyright"},
        ],
    }
    out = SITE / "data" / "site.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    d = build()
    print("days:", len(d["days"]), "| generated:", d["generated_at"], "| exits:", len(d["subway"]["exits"]))
    print(json.dumps(d["days"][:1], ensure_ascii=False, indent=1)[:3000])
