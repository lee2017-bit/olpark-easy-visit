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
    files = sorted(SRC.glob("compact_o*.csv.gz")) + sorted((SRC / "refill").glob("r_o*.csv.gz"))
    df = pd.concat((pd.read_csv(f, dtype=str, keep_default_na=False) for f in files), ignore_index=True)
    df = df.drop_duplicates("local_id")
    total = int((SRC / "compact_total.txt").read_text())
    rec = pd.DataFrame({
        "id": df.local_id.str.rpartition("-")[2].astype(int),
        "gate": df.in_gate.str.extract(r"^(\S{1,3}문)")[0],
        "t_in": pd.to_datetime(df.in_time, errors="coerce"),
        "t_out": pd.to_datetime(df.out_time.replace("", None), errors="coerce"),
        "out_gate": df.out_gate.str.extract(r"^(\S{1,3}문)")[0],
    }).dropna(subset=["t_in"])
    return rec, len(df), total


def month_coverage(rec: pd.DataFrame, total: int) -> pd.DataFrame:
    """월별로 받은 비율. 기록 ID는 1~total이고 달마다 이어진 구간이라(1월 1~188,895 …),
    구간 크기 = 다음 달 첫 ID − 이 달 첫 ID. 1~9월은 구간 안에서 ID와 시각이 무관하고(무작위 순서),
    10~12월은 ID가 시각 순서라 빠진 ID가 곧 빠진 시간대가 된다."""
    r = rec.assign(m=rec.t_in.dt.strftime("%Y-%m"))
    g = r.groupby("m").id.agg(["min", "max", "size"])
    g["n_ids"] = g["min"].shift(-1).fillna(total + 1).astype(int) - g["min"]
    g["coverage"] = (g["size"] / g["n_ids"]).round(3)
    g["time_ordered"] = [r[r.m == m].id.rank().corr(r[r.m == m].t_in.rank()) > 0.99 for m in g.index]
    return g.rename(columns={"size": "have"})


def gap_days(rec: pd.DataFrame, cov: pd.DataFrame, min_run: int = 50) -> set:
    """ID가 시각 순서인 달에서, 연속으로 min_run건 넘게 빠진 구간이 걸친 날짜."""
    days = set()
    for m, row in cov[cov.time_ordered].iterrows():
        g = rec[rec.t_in.dt.strftime("%Y-%m") == m].sort_values("id")
        ids, ts = g.id.values, g.t_in.values
        for i in np.where(np.diff(ids) > min_run)[0]:
            for d in pd.date_range(pd.Timestamp(ts[i]).normalize(), pd.Timestamp(ts[i + 1]).normalize()):
                days.add(d)
    return days


def first_reach(occ: pd.DataFrame, level: float) -> pd.Series:
    """날마다 주차대수가 처음 level(대)에 닿은 시각(시, 소수). 못 닿으면 NaN."""
    hit = occ[occ.occ >= level]
    t = hit.groupby("date").t.min()
    return (t.dt.hour + t.dt.minute / 60).rename(f"t{int(level / CAPACITY * 100)}")


TRUNCATED = {"2025-08", "2025-09"}  # 원본이 65,534건에서 잘려 하루 기록의 약 22%만 남은 달


def daily(rec: pd.DataFrame, cov: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """15분 주차대수. 1~7월은 기록이 무작위로 빠져 있어 그 달 받은 비율로 나눠 보정(occ),
    보정 전 값은 occ_raw. usable = 하루치가 온전한 날(8·9월, 11·12월 7일 이후, 10월 누락 구간, 매달 마지막 날 제외)."""
    main = rec[rec.gate.isin(MAIN)]
    occ = occupancy(main)
    occ = occ[occ.t.dt.year == 2025].copy()
    m = occ.t.dt.strftime("%Y-%m")
    w = m.map(lambda k: 1.0 if cov.time_ordered.get(k, True) else 1 / cov.coverage.get(k, 1.0))
    occ["occ_raw"] = occ.occ
    occ["occ"] = (occ.occ * w).round(0)
    bad = gap_days(rec, cov)
    last_t = rec.groupby(rec.t_in.dt.strftime("%Y-%m")).t_in.max()
    d = occ.groupby("date").agg(peak=("occ", "max"))
    d["peak_time"] = occ.loc[occ.groupby("date").occ.idxmax()].set_index("date").slot
    ev = occ[occ.slot.isin(EVENING)].pivot(index="date", columns="slot", values="occ")
    ev.columns = [f"occ_{c[:2]}" for c in ev.columns]
    d = d.join(ev).join(first_reach(occ, 0.9 * CAPACITY)).join(first_reach(occ, 0.7 * CAPACITY))
    ent = main.assign(date=main.t_in.dt.normalize()).groupby("date").size().rename("entries")
    d = d.join(ent)
    d["peak_pct"] = (d.peak / CAPACITY * 100).round(1)
    d = d.reset_index()
    mm = d.date.dt.strftime("%Y-%m")
    # 시각 순서인 달은 마지막 기록 시각 전날까지만 온전 (11·12월은 7일 도중에서 끊김)
    cut = mm.map(lambda k: last_t[k].normalize() if cov.time_ordered.get(k, False) else pd.Timestamp.max)
    # 매달 마지막 날은 원본에 입차 기록이 없음(전날 들어온 차만 남아 0에 가까움) → 입차 기록이 있는 날만
    d["usable"] = ~mm.isin(TRUNCATED) & ~d.date.isin(bad) & (d.date < cut) & d.entries.notna()
    c = pd.read_csv(PROCESSED / "congestion_daily_2025.csv", parse_dates=["date"])
    keep = ["date", "dow", "holiday", "offday", "n_venues", "first_start_h", "titles",
            "full_lots", "first_full_h", "any_full", "ev_cat"]
    d = d.merge(c[keep], on="date", how="left")
    return d, occ


def pct(s):
    return (s / CAPACITY * 100).round(0)


def report(d: pd.DataFrame, n_rows: int, total: int, cov: pd.DataFrame) -> str:
    out = [f"# 2025 입출차 전체구역 분석 ({date.today():%Y-%m-%d})", "",
           f"- 받은 기록 {n_rows:,} / 전체 {total:,}건 ({n_rows / total * 100:.1f}%)",
           f"- 대상: 동2·남2·북2문 입구, 기관 표기 수용 {CAPACITY:,}대 (기관 실시간 수치도 이를 넘곤 함 → 100% 초과 가능)",
           f"- 분석에 쓴 날: {int(d.usable.sum())}일 / 기록이 있는 {d.date.nunique()}일",
           "- 원본 문제: 8·9·11·12월은 각 65,534건에서 잘림(8·9월은 하루 기록의 약 22%만, 11·12월은 1~7일만),",
           "  모든 달의 마지막 날 없음. API가 요청마다 순서를 섞어 보내 ID로 중복을 빼고 다시 받아 메움.",
           "- 월별 받은 비율 (n_ids = 원본 건수, time_ordered = ID가 시각 순서):", "",
           "```", cov.to_string(), "```", ""]
    d = d[d.usable]
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
    first_pass = len(list(SRC.glob("compact_o*.csv.gz"))) * 5000 >= total - 10000
    final = first_pass and "--partial" not in sys.argv
    if not first_pass and "--partial" not in sys.argv:
        sys.exit(f"1차 수집이 아직 안 끝남 ({n_rows:,}/{total:,}건) — 끝난 뒤 실행 (시험: --partial)")
    cov = month_coverage(rec, total)
    d, occ = daily(rec, cov)
    txt = report(d, n_rows, total, cov)
    if final:
        occ.to_csv(PROCESSED / "occupancy_2025_15min.csv", index=False)
        d.to_csv(PROCESSED / "daily_2025_inout.csv", index=False)
        (REPORTS / f"inout_2025_{date.today():%Y%m%d}.md").write_text(txt, encoding="utf-8")
    print(txt)
