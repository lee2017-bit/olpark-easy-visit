"""기관 「주차장 혼잡도 정보」(구역별 원활/혼잡/만차 기록) × 공연 일정.

주의: 원본 '등록시간'의 분·초 자리에 월·일이 들어간 오류가 있어 시(hour)만 사용.
2026년 들어 기록이 거의 끊겨 2025-02-12 ~ 2025-12-31만 분석.
"""
import pandas as pd

from analysis.features import daily_calendar
from olpark.common import PROCESSED, RAW

START, END = "2025-02-12", "2025-12-31"


def load() -> pd.DataFrame:
    c = pd.read_csv(RAW / "files" / "congestion_log.csv")
    c["date"] = pd.to_datetime(c["등록일"])
    c["hour"] = c["등록시간"].astype(str).str[:2].astype(int)
    return c[(c.date >= START) & (c.date <= END)]


def daily() -> pd.DataFrame:
    c = load()
    cal = daily_calendar(START, END)
    full = c[c["혼잡도"] == "만차"].groupby("date").agg(full_lots=("주차구역", "nunique"),
                                                       first_full_h=("hour", "min"))
    d = cal.merge(full, on="date", how="left").fillna({"full_lots": 0})
    d["any_full"] = d.full_lots > 0
    d["ev_cat"] = pd.cut(d.n_venues, [-1, 0, 1, 9], labels=["공연 없음", "1곳", "2곳 이상"])
    return d


def summary(d: pd.DataFrame) -> pd.DataFrame:
    return (d.groupby(["offday", "ev_cat"], observed=True)
             .agg(days=("date", "size"), full_days=("any_full", "sum"),
                  full_rate=("any_full", "mean"), avg_full_lots=("full_lots", "mean"))
             .round(2))


if __name__ == "__main__":
    d = daily()
    d.to_csv(PROCESSED / "congestion_daily_2025.csv", index=False)
    print(summary(d).to_string())
    f = d[d.any_full]
    print("first full hour (median):", f.first_full_h.median(), "| avg full lots:", round(f.full_lots.mean(), 1))
