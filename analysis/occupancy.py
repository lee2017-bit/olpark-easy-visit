"""입출차 기록 → 15분 단위 주차대수(occupancy)와 일자별 요약.

입력 형식이 출처마다 달라서 load_inout()이 열 이름을 맞춰 줍니다.
- 2024-07 파일(data/raw/files/inout_202407.csv): 입차일, 입차일시, 출차일시
- 2025 API(API_CPM_008): 열 이름 확인 후 IN_COLS/OUT_COLS에 추가

출차 시각이 없거나 24시간 넘게 머문 차량(장기 주차)은 별도로 세고 주차대수에서는 뺍니다.
기관 실시간 수치가 수용 대수를 넘는 원인으로 추정되는 부분입니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from olpark.common import PROCESSED, RAW

IN_COLS = ["입차일시", "inDt", "in_time", "IN_DT"]
OUT_COLS = ["출차일시", "outDt", "out_time", "OUT_DT"]
CAPACITY = 2200  # 동2문·남2문·북2문 (기관 예상 이용률 서비스 표기)


def load_inout(path=None) -> pd.DataFrame:
    path = path or RAW / "files" / "inout_202407.csv"
    df = pd.read_csv(path)
    ic = next(c for c in IN_COLS if c in df.columns)
    oc = next(c for c in OUT_COLS if c in df.columns)
    out = pd.DataFrame({"t_in": pd.to_datetime(df[ic], errors="coerce"),
                        "t_out": pd.to_datetime(df[oc], errors="coerce")})
    return out.dropna(subset=["t_in"])


def occupancy(rec: pd.DataFrame, freq: str = "15min", max_hours: float = 24) -> pd.DataFrame:
    dur = (rec.t_out - rec.t_in).dt.total_seconds() / 3600
    ok = rec[(dur >= 0) & (dur <= max_hours)]
    start = rec.t_in.min().normalize()
    end = rec.t_in.max().normalize() + pd.Timedelta(days=1)
    grid = pd.date_range(start, end, freq=freq, inclusive="left")
    ins = np.sort(ok.t_in.values)
    outs = np.sort(ok.t_out.values)
    occ = np.searchsorted(ins, grid.values, side="right") - np.searchsorted(outs, grid.values, side="right")
    o = pd.DataFrame({"t": grid, "occ": occ})
    o["date"] = o.t.dt.normalize()
    o["slot"] = o.t.dt.strftime("%H:%M")
    return o


def daily_summary(rec: pd.DataFrame, occ: pd.DataFrame) -> pd.DataFrame:
    dur = (rec.t_out - rec.t_in).dt.total_seconds() / 3600
    r = rec.assign(date=rec.t_in.dt.normalize(), dur=dur, h=rec.t_in.dt.hour)
    g = r.groupby("date").agg(entries=("t_in", "size"),
                              long_stay_6h=("dur", lambda s: int(((s > 6) & (s <= 24)).sum())),
                              over_24h_or_missing=("dur", lambda s: int(((s > 24) | s.isna()).sum())),
                              arrivals_15_18=("h", lambda s: int(((s >= 15) & (s < 18)).sum())))
    pk = occ.groupby("date").agg(peak=("occ", "max"))
    pk["peak_time"] = occ.loc[occ.groupby("date")["occ"].idxmax()].set_index("date")["slot"]
    ev = occ[occ.slot.isin(["17:00", "18:00", "19:00", "20:00"])].pivot(index="date", columns="slot", values="occ")
    ev.columns = [f"occ_{c.replace(':', '')}" for c in ev.columns]
    d = g.join(pk).join(ev)
    d["peak_pct"] = (d.peak / CAPACITY * 100).round(1)
    return d.reset_index()


if __name__ == "__main__":
    rec = load_inout()
    occ = occupancy(rec)
    s = daily_summary(rec, occ)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    occ.to_csv(PROCESSED / "occupancy_202407_15min.csv", index=False)
    s.to_csv(PROCESSED / "daily_202407.csv", index=False)
    print(s.to_string())
