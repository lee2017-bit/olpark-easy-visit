"""다가오는 날의 '만차 위험' — 2025 실제 기록에서 같은 조건의 만차 비율을 그대로 보여줌.

회귀 모델(analysis.full_predict)은 표본(104일)이 적어 공연 없는 주말 등에서 왜곡이 생겨,
사이트에는 '2025년 같은 조건 N일 중 M일 만차' 형태의 경험 비율을 씁니다.

조건: 주말·공휴일 여부 × 공연 여부 × 봄(3~6월) 여부 × (3일 이내면) 비 예보
등급: 만차 비율 ≥70% 높음, 35~70% 보통, <35% 낮음
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from analysis.features import daily_calendar
from olpark.common import PROCESSED

VENUE_KO = {"olympic_hall": "올림픽홀", "kspo_dome": "KSPO DOME", "handball": "티켓링크 라이브 아레나(핸드볼경기장)",
            "lawn88": "88잔디마당"}


def grade(rate: float) -> str:
    return "높음" if rate >= 0.70 else ("보통" if rate >= 0.35 else "낮음")


def history() -> pd.DataFrame:
    d = pd.read_csv(PROCESSED / "full_predict_days.csv", parse_dates=["date"])
    d["spring"] = d.date.dt.month.between(3, 6)
    d["has_event"] = d.n_venues > 0
    return d


def _rate(h: pd.DataFrame, **cond) -> tuple[int, int]:
    m = pd.Series(True, index=h.index)
    for k, v in cond.items():
        m &= h[k] == v
    s = h[m]
    return int(s.y.sum()), int(len(s))


def _forecast_rain() -> dict:
    f = PROCESSED / "weather_forecast.csv"
    if not f.exists():
        return {}
    w = pd.read_csv(f, dtype=str)
    w["POP"] = pd.to_numeric(w.get("POP"), errors="coerce")
    g = w.groupby("fcstDate").POP.max()
    return {pd.Timestamp(k): int(v) for k, v in g.items() if pd.notna(v)}


def upcoming(days_ahead: int = 60, today: dt.date | None = None) -> tuple[pd.DataFrame, dict]:
    today = today or dt.date.today()
    h = history()
    full = h[h.y == 1]
    stats = {"first_full_h_median": float(full.first_full_h.median()),
             "share_full_before_show": float((full.first_full_h < full.first_start_h).mean()),
             "period": "2025-02-12~2025-12-31", "offdays": int(len(h)), "full_days": int(h.y.sum())}
    cal = daily_calendar(today.isoformat(), (today + dt.timedelta(days=days_ahead)).isoformat())
    pop = _forecast_rain()
    out = []
    for _, r in cal.iterrows():
        spring = 3 <= r.date.month <= 6
        has_event = (r.get("n_venues") or 0) > 0
        rec = {"date": r.date, "offday": bool(r.offday), "holiday": bool(r.holiday), "spring": spring,
               "n_venues": int(r.get("n_venues") or 0), "pop_max": pop.get(r.date)}
        if not r.offday:
            m, n = 2, 219
            rec.update(grade="낮음", basis=f"2025년 평일 {n}일 중 {m}일만 만차 기록", m=m, n=n)
        elif not has_event:
            m, n = _rate(h, has_event=False)
            rec.update(grade="낮음", basis=f"2025년 공연 없는 주말·공휴일 {n}일(대부분 명절·공휴일)은 모두 만차 기록 없음 — 표본이 적어 참고용",
                       m=m, n=n)
        else:
            rain = None if rec["pop_max"] is None else rec["pop_max"] >= 60
            if rain is None:
                m, n = _rate(h, has_event=True, spring=spring)
                cond = f"{'봄(3~6월)' if spring else '7~2월'} 공연 있는 주말·공휴일"
            else:
                m, n = _rate(h, has_event=True, spring=spring, rain=int(rain))
                cond = f"{'봄(3~6월)' if spring else '7~2월'} 공연 있는 주말·공휴일, {'비 온' if rain else '비 안 온'} 날"
            rec.update(grade=grade(m / n if n else 0), basis=f"2025년 {cond} {n}일 중 {m}일 만차", m=m, n=n)
        out.append(rec)
    return pd.DataFrame(out), stats


if __name__ == "__main__":
    u, stats = upcoming()
    print(stats)
    print(u[u.offday | (u.n_venues > 0)][["date", "offday", "n_venues", "pop_max", "grade", "basis"]].to_string())
