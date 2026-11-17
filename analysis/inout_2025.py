"""2025 입출차 전체구역(API_CPM_008) → 15분 단위 주차대수와 공연일 저녁 분석.

입력: data/raw/kcisa_inout/compact_o*.csv.gz  (collectors.kcisa_parking --compact)
대상: 동2·남2·북2문 입구로 들어온 차량 (수용 2,200대, 2024-07 분석과 같은 기준)
      입구 이름 끝의 '#번호'와 'CMB'(무인 정산기로 추정)는 같은 문으로 묶음. '회관 임원 입구'는 제외.
주의: 출차 시각이 없거나 24시간 넘게 머문 차량은 occupancy()에서 빠짐 (장기 주차, 기록 누락).

산출
  data/processed/occupancy_2025_15min.csv  : 15분 단위 주차대수 (3개 문 합계)
  data/processed/daily_2025_inout.csv      : 일자별 최대·저녁 시간대 주차대수 + 기관 만차 기록·공연
  reports/inout_2025_<날짜>.md             : 요약표
사용: python -m analysis.inout_2025 [--partial]   (--partial: 다 받기 전 시험 실행)
"""
from __future__ import annotations

import sys
from datetime import date

import numpy as np
import pandas as pd

from analysis.occupancy import CAPACITY, occupancy
from olpark.common import PROCESSED, RAW, REPORTS

MAIN = ("동2문", "남2문", "북2문")
SRC = RAW / "kcisa_inout"
EVENING = ["16:00", "17:00", "18:00", "19:00", "20:00", "21:00"]


def load_compact() -> tuple[pd.DataFrame, int, int]:
    files = sorted(SRC.glob("compact_o*.csv.gz"))
    df = pd.concat((pd.read_csv(f, dtype=str, keep_default_na=False) for f in files), ignore_index=True)
    df = df.drop_duplicates("local_id")
    total = int((SRC / "compact_total.txt").read_text())
    rec = pd.DataFrame({
        "gate": df.in_gate.str.extract(r"^(\S{1,3}문)")[0],
        "t_in": pd.to_datetime(df.in_time, errors="coerce"),
        "t_out": pd.to_datetime(df.out_time.replace("", None), errors="coerce"),
    }).dropna(subset=["t_in"])
    return rec, len(df), total


def first_reach(occ: pd.DataFrame, level: float) -> pd.Series:
    """날마다 주차대수가 처음 level(대)에 닿은 시각(시, 소수). 못 닿으면 NaN."""
    hit = occ[occ.occ >= level]
    t = hit.groupby("date").t.min()
    return (t.dt.hour + t.dt.minute / 60).rename(f"t{int(level / CAPACITY * 100)}")


def daily(rec: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    main = rec[rec.gate.isin(MAIN)]
    occ = occupancy(main)
    occ = occ[occ.t.dt.year == 2025]
    d = occ.groupby("date").agg(peak=("occ", "max"))
    d["peak_time"] = occ.loc[occ.groupby("date").occ.idxmax()].set_index("date").slot
    ev = occ[occ.slot.isin(EVENING)].pivot(index="date", columns="slot", values="occ")
    ev.columns = [f"occ_{c[:2]}" for c in ev.columns]
    d = d.join(ev).join(first_reach(occ, 0.9 * CAPACITY)).join(first_reach(occ, 0.7 * CAPACITY))
    ent = main.assign(date=main.t_in.dt.normalize()).groupby("date").size().rename("entries")
    d = d.join(ent)
    d["peak_pct"] = (d.peak / CAPACITY * 100).round(1)
    d = d.reset_index()
    c = pd.read_csv(PROCESSED / "congestion_daily_2025.csv", parse_dates=["date"])
    keep = ["date", "dow", "holiday", "offday", "n_venues", "first_start_h", "titles",
            "full_lots", "first_full_h", "any_full", "ev_cat"]
    d = d.merge(c[keep], on="date", how="left")
    return d, occ


def pct(s):
    return (s / CAPACITY * 100).round(0)


def report(d: pd.DataFrame, n_rows: int, total: int) -> str:
    out = [f"# 2025 입출차 전체구역 분석 ({date.today():%Y-%m-%d})", "",
           f"- 받은 기록 {n_rows:,} / 전체 {total:,}건 ({n_rows / total * 100:.1f}%)",
           f"- 대상: 동2·남2·북2문 입구, 수용 {CAPACITY:,}대. 2025년 {d.date.nunique()}일", ""]
    o = d[d.offday == True]  # noqa: E712
    w = d[d.offday == False]  # noqa: E712

    out += ["## 1. 기관 '만차' 기록과 맞는지 (혼잡도 기록이 있는 2025-02-12~12-31)", ""]
    g = d.dropna(subset=["any_full"]).groupby("any_full").agg(
        days=("date", "size"), peak_pct_median=("peak_pct", "median"),
        peak_pct_p10=("peak_pct", lambda s: s.quantile(.1)), reach90=("t90", lambda s: s.notna().mean()))
    out += ["```", g.round(2).to_string(), "```", ""]

    out += ["## 2. 쉬는 날 공연 수별 시간대 이용률(%) 평균", ""]
    cols = [c for c in d.columns if c.startswith("occ_")]
    t = o.groupby("ev_cat", observed=True)[cols].mean().apply(pct)
    t["days"] = o.groupby("ev_cat", observed=True).size()
    t["peak_pct"] = o.groupby("ev_cat", observed=True).peak_pct.mean().round(0)
    out += ["```", t.to_string(), "```", ""]
    tw = w.groupby("ev_cat", observed=True)[cols].mean().apply(pct)
    tw["days"] = w.groupby("ev_cat", observed=True).size()
    out += ["평일", "```", tw.to_string(), "```", ""]

    out += ["## 3. 공연 시작 시각 대비 언제 차는가 (쉬는 날, 공연 있음)", ""]
    s = o[o.n_venues > 0].copy()
    s["lead90"] = s.first_start_h - s.t90
    s["lead70"] = s.first_start_h - s.t70
    s["start"] = pd.cut(s.first_start_h, [0, 16.9, 17.9, 18.9, 24], labels=["~16시", "17시", "18시", "19시~"])
    tt = s.groupby("start", observed=True).agg(
        days=("date", "size"), reach90=("t90", lambda x: x.notna().mean()),
        lead90_median_h=("lead90", "median"), reach70=("t70", lambda x: x.notna().mean()),
        lead70_median_h=("lead70", "median"), peak_pct=("peak_pct", "mean"))
    out += ["```", tt.round(2).to_string(), "```", "",
            "lead = 공연 시작 시각 − 처음 90%(70%)에 닿은 시각 (시간). 양수면 공연 전에 이미 찼다는 뜻.", ""]

    out += ["## 4. 가장 붐빈 날 (최대 이용률 상위 15일)", ""]
    top = d.nlargest(15, "peak_pct")[["date", "dow", "peak_pct", "peak_time", "t90", "first_start_h",
                                       "any_full", "first_full_h", "titles"]]
    top["titles"] = top.titles.fillna("").str.slice(0, 60)
    out += ["```", top.to_string(index=False), "```", ""]
    return "\n".join(out)


if __name__ == "__main__":
    rec, n_rows, total = load_compact()
    if n_rows < total and "--partial" not in sys.argv:
        sys.exit(f"아직 {n_rows:,}/{total:,}건만 받음 — 다 받은 뒤 실행 (시험: --partial)")
    d, occ = daily(rec)
    txt = report(d, n_rows, total)
    if n_rows >= total:
        occ.to_csv(PROCESSED / "occupancy_2025_15min.csv", index=False)
        d.to_csv(PROCESSED / "daily_2025_inout.csv", index=False)
        (REPORTS / f"inout_2025_{date.today():%Y%m%d}.md").write_text(txt, encoding="utf-8")
    print(txt)
