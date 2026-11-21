"""공연 뒤 출차가 언제 몰리나 (2025 입출차, 동2·남2·북2문 출구) → 귀가 안내.

대상: 공연 있는 날(usable), 첫 공연 시작 뒤 26시까지 15분 단위 출차 수.
지표: 가장 많이 나간 15분이 시작 몇 시간 뒤인가, 가장 많이 나간 30분의 대수.
주의: 1~7월은 기록 일부만 받아 대수가 실제보다 적게 나옴(시각은 영향 적음) → 대수는 10~12월만 따로 봄.
산출: data/processed/exit_wave_2025.csv, reports/exit_wave_<날짜>.md
사용: python -m analysis.exit_wave
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from analysis.full_predict import build
from analysis.inout_2025 import MAIN, load_compact
from olpark.common import PROCESSED, REPORTS


def run() -> pd.DataFrame:
    rec, _, _ = load_compact()
    out = rec[rec.out_gate.isin(MAIN) & rec.t_out.notna()]
    d = pd.read_csv(PROCESSED / "daily_2025_inout.csv", parse_dates=["date"])
    o = d[d.usable & (d.n_venues > 0) & d.first_start_h.notna()].merge(
        build()[["date", "ev_kspo_dome"]], on="date")
    rows = []
    for x in o.itertuples():
        st = x.date + pd.Timedelta(hours=float(x.first_start_h))
        e = out[(out.t_out >= st) & (out.t_out < x.date + pd.Timedelta(hours=26))]
        c = e.groupby(e.t_out.dt.floor("15min")).size()
        if c.empty:
            continue
        rows.append({"date": x.date.date(), "offday": x.offday, "kspo_dome": x.ev_kspo_dome, "n_venues": x.n_venues,
                     "first_start_h": x.first_start_h, "peak_after_start_h": (c.idxmax() - st).total_seconds() / 3600,
                     "peak_15min": int(c.max()), "peak_30min": int(c.rolling(2).sum().max()),
                     "full_count": x.date.month >= 10})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    t = run()
    t.to_csv(PROCESSED / "exit_wave_2025.csv", index=False)
    k = t[t.kspo_dome == 1]
    eve = k[k.first_start_h >= 16]
    full = eve[eve.full_count]
    txt = "\n".join([
        f"# 공연 뒤 출차가 몰리는 때 ({date.today():%Y-%m-%d})", "",
        f"- KSPO DOME 공연일 {len(k)}일 중 첫 공연 16시 이후 {len(eve)}일: 가장 많이 나간 15분은 시작 "
        f"{eve.peak_after_start_h.median():.2f}시간 뒤(중앙값, 사분위 {eve.peak_after_start_h.quantile(.25):.2f}~"
        f"{eve.peak_after_start_h.quantile(.75):.2f}시간)",
        f"- 가장 많이 나간 30분의 대수 (기록이 온전한 10~12월 {len(full)}일): 중앙값 {full.peak_30min.median():.0f}대 "
        f"(최소 {full.peak_30min.min()}, 최대 {full.peak_30min.max()})",
        "- 2026-11-21 실측(기관 계수기): 시작(18:00) 3시간 뒤 21:00~21:30에 546대 감소", "",
        "```", eve.to_string(index=False), "```", ""])
    (REPORTS / f"exit_wave_{date.today():%Y%m%d}.md").write_text(txt, encoding="utf-8")
    print(txt[:900])
