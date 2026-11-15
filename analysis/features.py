"""일자별 달력·공연 특성 만들기.

- 공연 시작 시각 파싱 (홈페이지 'tm' 자유 형식 → 요일별 가장 이른 시작 시각)
- 일자별: 요일, 주말/공휴일, 공연장별 공연 여부, 동시 공연장 수, 가장 이른 시작 시각
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from olpark.common import PROCESSED

WD = "월화수목금토일"
CONCERT_VENUES = {"01": "olympic_hall", "02": "kspo_dome", "03": "handball", "06": "lawn88"}

_wd_re = re.compile(r"\(([월화수목금토일])\)|(?<![0-9가-힣])([월화수목금토일]{1,2})(?=[\s/,|]|오|[0-9]|$)")
_t_colon = re.compile(r"(\d{1,2}):(\d\d)")
_t_si = re.compile(r"(오전|오후)?\s*(\d{1,2})\s*시")
_t_pm = re.compile(r"(\d{1,2})\s*(PM|AM|pm|am)")


def _norm_hour(h: int, ampm: str | None) -> int:
    if ampm in ("오후", "PM", "pm") and h < 12:
        return h + 12
    if ampm in ("오전", "AM", "am"):
        return h
    return h + 12 if 1 <= h <= 9 else h  # "6시" 공연은 저녁 6시로 간주


def parse_start_times(tm: str) -> dict:
    """Return {weekday_index or None: earliest start hour (float)}."""
    if not isinstance(tm, str):
        return {}
    tokens = []
    for m in _wd_re.finditer(tm):
        tokens.append((m.start(), "wd", m.group(1) or m.group(2)))
    for m in _t_colon.finditer(tm):
        tokens.append((m.start(), "t", int(m.group(1)) + int(m.group(2)) / 60))
    for m in _t_si.finditer(tm):
        if _t_colon.match(tm, m.start(2)):
            continue
        tokens.append((m.start(), "t", float(_norm_hour(int(m.group(2)), m.group(1)))))
    for m in _t_pm.finditer(tm):
        tokens.append((m.start(), "t", float(_norm_hour(int(m.group(1)), m.group(2)))))
    tokens.sort()
    res: dict = {}
    pending: list = []
    last_was_time = False
    for _, kind, val in tokens:
        if kind == "wd":
            if last_was_time:
                pending = []
            pending += [WD.index(c) for c in val]
            last_was_time = False
        else:
            keys = pending or [None]
            for k in keys:
                res[k] = min(res.get(k, 99), val)
            last_was_time = True
    return res


def event_days(events: pd.DataFrame | None = None, max_run_days: int = 14) -> pd.DataFrame:
    """One row per (date, venue) for concert venues, with start hour."""
    if events is None:
        events = pd.read_csv(PROCESSED / "events_homepage.csv", dtype=str)
    ev = events[events.plcCd.isin(CONCERT_VENUES)].copy()
    ev["b"], ev["e"] = pd.to_datetime(ev.beginDt), pd.to_datetime(ev.endDt)
    ev = ev[(ev.e - ev.b).dt.days + 1 <= max_run_days]
    rows = []
    for _, r in ev.iterrows():
        st = parse_start_times(r.tm)
        for d in pd.date_range(r.b, r.e):
            h = st.get(d.dayofweek, st.get(None, min(st.values()) if st else np.nan))
            rows.append({"date": d.normalize(), "venue": CONCERT_VENUES[r.plcCd], "start_h": h,
                         "title": r.title, "evtSeq": r.evtSeq})
    return pd.DataFrame(rows)


def daily_calendar(start: str, end: str, events: pd.DataFrame | None = None) -> pd.DataFrame:
    days = pd.DataFrame({"date": pd.date_range(start, end)})
    days["dow"] = days.date.dt.dayofweek
    hol_f = PROCESSED / "holidays.csv"
    hol = set(pd.to_datetime(pd.read_csv(hol_f)["date"])) if hol_f.exists() else set()
    days["holiday"] = days.date.isin(hol)
    days["offday"] = (days.dow >= 5) | days.holiday
    ed = event_days(events)
    if len(ed):
        piv = ed.pivot_table(index="date", columns="venue", values="start_h", aggfunc="min")
        for v in CONCERT_VENUES.values():
            if v not in piv:
                piv[v] = np.nan
        days = days.merge(piv.reset_index(), on="date", how="left")
        for v in CONCERT_VENUES.values():
            days[f"ev_{v}"] = days[v].notna().astype(int)
        days["n_venues"] = days[[f"ev_{v}" for v in CONCERT_VENUES.values()]].sum(axis=1)
        days["first_start_h"] = days[list(CONCERT_VENUES.values())].min(axis=1)
        titles = ed.groupby("date")["title"].apply(lambda s: " / ".join(sorted(set(s))))
        days["titles"] = days.date.map(titles).fillna("")
        days = days.drop(columns=list(CONCERT_VENUES.values()))
    return days


if __name__ == "__main__":
    for s in ["(토) 18:00 / (일) 16:00", "2025년 1월 17일(금) 오후 8시 2025년 1월 18일(토) 오후 6시",
              "토일 18:00", "금 20시 / 토 18시 / 일 17시", "8월 22일(토) 1PM, 6PM / 8월 23일(일) 1PM, 6PM",
              "11:00", "2026년 12월 12일(토) 6시 / 2026년 12월 13() 5시"]:
        print(s, "->", parse_start_times(s))
    cal = daily_calendar("2024-07-01", "2024-07-31")
    print(cal[cal.n_venues > 0][["date", "dow", "n_venues", "first_start_h", "titles"]].to_string())
