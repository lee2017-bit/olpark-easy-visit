"""공연일 저녁 이용률을 얼마나 맞힐 수 있나 — 예측 개선 가능성 검토 (2025 입출차).

대상: 쉬는 날·공연 있는 날(usable), 지표 = 17:00~21:00 30분 간격 9개 시각 평균 이용률(2,200대 대비 %).
방법: 하루씩 빼고 나머지 날로 맞힘(LOO), 평균 절대 오차(%p).
산출: reports/predictability_<날짜>.md
사용: python -m analysis.predictability
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from analysis.full_predict import build
from analysis.occupancy import CAPACITY
from olpark.common import PROCESSED, REPORTS

EVE = [f"{h:02d}:{m:02d}" for h in range(17, 21) for m in (0, 30)] + ["21:00"]


def load() -> pd.DataFrame:
    d = pd.read_csv(PROCESSED / "daily_2025_inout.csv", parse_dates=["date"])
    occ = pd.read_csv(PROCESSED / "occupancy_2025_15min.csv", parse_dates=["t", "date"])
    o = d[d.usable & (d.offday == True) & (d.n_venues > 0)].merge(build()[["date", "ev_kspo_dome"]], on="date")  # noqa: E712
    piv = occ[occ.date.isin(o.date)].pivot(index="date", columns="slot", values="occ") / CAPACITY * 100
    o = o.set_index("date")
    o["eve"] = piv[EVE].mean(axis=1)
    for h in ("12", "13", "14"):
        o[f"now{h}"] = piv[f"{h}:00"]
    o["m"] = o.index.month
    o["start_h"] = o.first_start_h.round()
    return o


def loo(o: pd.DataFrame, f) -> float:
    return float(np.mean([abs(f(o.drop(i), o.loc[i]) - o.at[i, "eve"]) for i in o.index]))


def group_mean(key):
    def f(tr, r):
        g = tr[(tr[key] == r[key]).all(axis=1)] if isinstance(key, list) else tr[tr[key] == r[key]]
        return g.eve.mean() if len(g) else tr.eve.mean()
    return f


def linear(col):
    def f(tr, r):
        a, b = np.polyfit(tr[col], tr.eve, 1)
        return a * r[col] + b
    return f


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    o = load()
    rows = [("전체 평균 하나", lambda tr, r: tr.eve.mean()),
            ("달별 평균", group_mean("m")),
            ("공연장(KSPO DOME 여부)·시작 시각별 평균", group_mean(["ev_kspo_dome", "start_h"])),
            ("당일 12시 실측으로 (직선)", linear("now12")),
            ("당일 13시 실측으로 (직선)", linear("now13")),
            ("당일 14시 실측으로 (직선)", linear("now14"))]
    t = pd.DataFrame([{"방법": n, "평균 오차(%p)": round(loo(o, f), 1)} for n, f in rows])
    s = o.reset_index().sort_values("date")
    s["t0"] = s.titles.fillna("").str[:25]
    nxt = s.shift(-1)
    pair = s[(s.t0 == nxt.t0) & ((nxt.date - s.date).dt.days == 1)]
    p = pd.DataFrame({"첫날": pair.date.dt.date, "둘째 날": nxt.loc[pair.index, "date"].dt.date,
                      "첫날 저녁%": pair.eve.round(0), "둘째 날 저녁%": nxt.loc[pair.index, "eve"].round(0)})
    p["차이%p"] = (p["첫날 저녁%"] - p["둘째 날 저녁%"]).abs()
    return t, p, o


if __name__ == "__main__":
    t, p, o = run()
    txt = "\n".join([
        f"# 공연일 저녁 이용률 예측 가능성 ({date.today():%Y-%m-%d})", "",
        f"대상: 2025년 쉬는 날·공연 있는 날 {len(o)}일. 지표: 17~21시 30분 간격 평균 이용률 "
        f"(평균 {o.eve.mean():.1f}%, 표준편차 {o.eve.std():.1f}%p). 하루씩 빼고 맞힘.", "",
        "```", t.to_string(index=False), "```", "",
        f"## 같은 공연 이틀 연속 {len(p)}쌍: 저녁 수준 차이 평균 {p['차이%p'].mean():.1f}%p", "",
        "```", p.to_string(index=False), "```", "",
        "## 해석", "",
        "- 공연장·시작 시각·달로 나눠도 전체 평균 하나로 맞히는 것과 차이가 거의 없음 (공연장·시작 시각은 오히려 나쁨).",
        "- 같은 공연이 이틀 연속이어도 저녁 수준이 크게 다름 → 날마다의 차이는 공개된 공연 정보로 설명되지 않음.",
        "- 당일 낮 실측을 쓰면 조금 나아지지만 여전히 10%p 넘게 틀림.",
        "- 2026-11-21 기관 예상(89% 고정)의 오차는 4.8%p (`reports/live_check_20261121.md`, 하루치).",
        "- 결론: 지금 공개된 자료로는 기관 예상보다 나은 예측을 만들기 어려움 → 서비스는 접근성 안내 중심으로.", ""])
    (REPORTS / f"predictability_{date.today():%Y%m%d}.md").write_text(txt, encoding="utf-8")
    print(txt)
