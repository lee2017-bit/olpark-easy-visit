"""다가오는 날의 '만차 위험' — 2025년 같은 달 실제 기록을 그대로 보여줌.

회귀 모델(analysis.full_predict)은 표본(104일)이 적어 공연 없는 주말 등에서 왜곡이 생겨,
사이트에는 '2025년 같은 달 N일 중 M일' 형태의 경험 비율을 씁니다.

조건: 주말·공휴일 여부 × 공연 여부 × 달(1~12월)
  - 근거 두 가지: 기관 「주차장 혼잡도 정보」 만차 기록, 2025 입출차 기록으로 다시 만든 주차대수(3개 문 합계 90% 도달)
  - 둘 중 높은 비율로 등급을 정함 (교통약자에게는 위험을 낮게 보는 쪽이 더 해롭기 때문)
  - 표본이 적은 달은 3일분만큼 연평균 쪽으로 당겨 계산
  - 비 예보는 등급에 넣지 않음 (2025 입출차 검증에서 비 온 날과 차이가 없었음: reports/hypotheses_2025_*.md)
등급: 비율 ≥70% 높음, 35~70% 보통, <35% 낮음
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


K_SHRINK = 3  # 표본이 적은 달은 이 일수만큼 연평균 쪽으로 당김
# 2025-01-01~02-11은 혼잡도 기록 전이라 휴일 정보가 없어 채움 (한국천문연구원 특일 정보 2025: 신정, 임시공휴일, 설날 연휴)
HOLIDAYS_2025_JAN = {"2025-01-01", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30"}


def inout_history() -> pd.DataFrame:
    """2025 입출차로 다시 만든 하루 주차대수(analysis.inout_2025) 중 하루치가 온전한 날. y90 = 3개 문 합계 90% 도달."""
    f = PROCESSED / "daily_2025_inout.csv"
    if not f.exists():
        return pd.DataFrame(columns=["date", "offday", "n_venues", "y90"])
    d = pd.read_csv(f, parse_dates=["date"])
    d = d[d.usable].copy()
    miss = d.offday.isna()
    if miss.any():
        cal = daily_calendar(d.date[miss].min().strftime("%Y-%m-%d"),
                             d.date[miss].max().strftime("%Y-%m-%d")).set_index("date")
        dd = d.loc[miss, "date"]
        d.loc[miss, "n_venues"] = dd.map(cal.n_venues).fillna(0).values
        d.loc[miss, "offday"] = ((dd.dt.dayofweek >= 5) | dd.dt.strftime("%Y-%m-%d").isin(HOLIDAYS_2025_JAN)).values
    d["offday"] = d.offday.astype(bool)
    d["y90"] = d.t90.notna().astype(int)
    return d


def monthly_rates() -> pd.DataFrame:
    """공연 있는 주말·공휴일의 달별 비율: 만차 기록(log)과 90% 도달(io), 둘 중 높은 쪽(rate)."""
    h = history()
    h = h[h.has_event]
    io = inout_history()
    io = io[io.offday & (io.n_venues > 0)]
    p_log, p_io = h.y.mean(), io.y90.mean()
    rows = []
    for mon in range(1, 13):
        a, b = h[h.date.dt.month == mon], io[io.date.dt.month == mon]
        r_log = (a.y.sum() + K_SHRINK * p_log) / (len(a) + K_SHRINK) if len(a) else None
        r_io = (b.y90.sum() + K_SHRINK * p_io) / (len(b) + K_SHRINK) if len(b) else None
        have = [r for r in (r_log, r_io) if r is not None]
        rows.append({"month": mon, "m_log": int(a.y.sum()), "n_log": len(a), "m_io": int(b.y90.sum()),
                     "n_io": len(b), "r_log": r_log, "r_io": r_io,
                     "rate": max(have) if have else p_log})
    return pd.DataFrame(rows).set_index("month")


def monthly_basis(mon: int, r: pd.Series) -> str:
    parts = []
    if r.n_log:
        parts.append(f"만차 기록 {int(r.n_log)}일 중 {int(r.m_log)}일")
    if r.n_io:
        parts.append(f"실제 주차대수 90% 이상 {int(r.n_io)}일 중 {int(r.m_io)}일")
    return f"2025년 {mon}월 공연 있는 주말·공휴일: " + (", ".join(parts) if parts else "기록 없음(연평균 사용)")


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
    mr = monthly_rates()
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
            mrow = mr.loc[r.date.month]
            m, n = (mrow.m_log, mrow.n_log) if mrow.n_log else (mrow.m_io, mrow.n_io)
            rec.update(grade=grade(mrow.rate), basis=monthly_basis(r.date.month, mrow), m=int(m), n=int(n))
        out.append(rec)
    return pd.DataFrame(out), stats


if __name__ == "__main__":
    print(monthly_rates().round(2).to_string())
    u, stats = upcoming()
    print(stats)
    print(u[u.offday | (u.n_venues > 0)][["date", "offday", "n_venues", "pop_max", "grade", "basis"]].to_string())
