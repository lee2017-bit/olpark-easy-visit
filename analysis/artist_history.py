"""공연 제목 → 가수(대표 키워드) 추출, 올림픽공원 과거 공연 이력 매칭.

가설: 오래전부터 올림픽공원에서 공연해 온 가수(데뷔·활동 기간이 긴 가수)는 관객 연령대가 높아
자가용 이용이 많고, 그래서 주차 수요가 크다 (예: 2024-07 SG워너비 공연일 이용률 99%).
출연자 필드가 비어 있어서 제목의 앞쪽 핵심 단어로 근사합니다(오차 있음).

이력 출처: 기관 공연정보 API(KSCperf, 2014~2024) + 홈페이지 공연 일정(2024~2026)
"""
from __future__ import annotations

import re

import pandas as pd

from olpark.common import PROCESSED

STOP = set("""
CONCERT CONCERTS TOUR WORLD ASIA ASIAN ENCORE IN SEOUL LIVE FAN FANMEETING MEETING FANCON SPECIAL
THE OF AND A AN SHOW SOLO FINAL NATIONWIDE ANNIVERSARY OFFICIAL FESTIVAL GLOBAL NEW YEAR YEARS
콘서트 전국투어 투어 서울 앙코르 단독 팬미팅 팬콘서트 공연 서울공연 내한공연 내한 월드투어 아시아투어 스페셜
""".split())
YEAR = re.compile(r"(19|20)\d{2}")


def artist_key(title: str) -> str | None:
    if not isinstance(title, str):
        return None
    t = re.sub(r"[〈《<\[［(（「『‘'\"“].*?[〉》>\]］)）」』’'\"”]", " ", title)
    t = re.sub(r"(19|20)\d{2}(-\d{2})?", " ", t)
    t = re.sub(r"[:：\-–|/,·.!?~＆&]", " ", t)
    for tok in t.split():
        u = tok.upper().strip("’'s")
        u = re.sub(r"(의|와|과|님)$", "", u)
        if len(u) >= 2 and u not in STOP and not u.isdigit() and not re.fullmatch(r"\d+(ST|ND|RD|TH)", u):
            return u
    return None


def _year_of(row) -> int | None:
    for field in ("temporalCoverage", "title"):
        m = YEAR.search(str(row.get(field, "")))
        if m:
            return int(m.group(0))
    return None


def history_table() -> pd.DataFrame:
    api = pd.read_csv(PROCESSED / "events_api.csv")
    api["year"] = api.apply(_year_of, axis=1)
    api["src"] = "api"
    hp = pd.read_csv(PROCESSED / "events_homepage.csv", dtype=str)
    hp["year"] = pd.to_datetime(hp.beginDt).dt.year
    hp["src"] = "homepage"
    h = pd.concat([api[["title", "year", "src"]], hp[["title", "year", "src"]]], ignore_index=True)
    h["key"] = h.title.map(artist_key)
    return h.dropna(subset=["key", "year"]).drop_duplicates(["title", "year"])


def features_for(titles: pd.Series, years: pd.Series, hist: pd.DataFrame | None = None) -> pd.DataFrame:
    hist = history_table() if hist is None else hist
    out = []
    for title, year in zip(titles, years):
        k = artist_key(title)
        prev = hist[(hist.key == k) & (hist.year < year)] if k else hist.iloc[0:0]
        out.append({"artist_key": k, "prev_shows": len(prev),
                    "first_year": int(prev.year.min()) if len(prev) else None,
                    "years_active_at_venue": int(year - prev.year.min()) if len(prev) else 0})
    return pd.DataFrame(out, index=titles.index)


if __name__ == "__main__":
    hist = history_table()
    print("history rows:", len(hist), "years:", hist.year.min(), "~", hist.year.max())
    ev = pd.read_csv(PROCESSED / "events_homepage.csv", dtype=str)
    ev = ev[ev.plcCd.isin(["01", "02", "03", "06"])]
    ev["year"] = pd.to_datetime(ev.beginDt).dt.year
    f = features_for(ev.title, ev.year, hist)
    x = pd.concat([ev[["beginDt", "title"]], f], axis=1)
    print(x[x.beginDt.str.startswith("2024-07")].to_string())
    print("matched share (prev_shows>0):", round((x.prev_shows > 0).mean(), 2))
    print(x.sort_values("years_active_at_venue", ascending=False).head(15)[["beginDt", "title", "artist_key", "prev_shows", "first_year"]].to_string())
