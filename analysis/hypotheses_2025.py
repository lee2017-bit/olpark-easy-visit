"""2025 입출차(15분 주차대수)로 만차 가설 검증 → 기획서 3-2 표.

입력: data/processed/daily_2025_inout.csv (analysis.inout_2025), analysis.full_predict.build() (공연장·계절·비·가수 이력)
판정: 두 집단 평균 차이의 순열검정(2만 번) p<0.05이고 기관 만차 기록과 방향이 같으면 '맞음'.
산출: reports/hypotheses_2025_<날짜>.md
사용: python -m analysis.hypotheses_2025
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from analysis.full_predict import build
from olpark.common import PROCESSED, REPORTS

RNG = np.random.default_rng(1)


def perm_test(x, g, n: int = 20000) -> tuple[float, float, float, float]:
    """(집단 평균, 나머지 평균, 차이, 양측 p)"""
    x, g = np.asarray(x, float), np.asarray(g, bool)
    obs = x[g].mean() - x[~g].mean()
    hits = sum(abs(x[p].mean() - x[~p].mean()) >= abs(obs) for p in (RNG.permutation(g) for _ in range(n)))
    return x[g].mean(), x[~g].mean(), obs, hits / n


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(PROCESSED / "daily_2025_inout.csv", parse_dates=["date"])
    u = d[d.usable].copy()
    u["eve"] = u[["occ_19", "occ_20"]].mean(axis=1) / 2200 * 100  # 19·20시 평균 이용률(%)
    b = build()[["date", "ev_kspo_dome", "season", "rain", "early_start", "veteran"]]
    o = u[(u.offday == True) & (u.n_venues > 0)].merge(b, on="date")  # noqa: E712  쉬는 날 공연일
    o["multi"] = o.n_venues >= 2
    return u, o


def run() -> pd.DataFrame:
    u, o = load()
    od = u[u.offday == True]  # noqa: E712
    wk = u[u.offday == False]  # noqa: E712
    cl = u.dropna(subset=["any_full"])
    rows = [
        ("쉬는 날이 평일보다 붐빈다", u.dropna(subset=["offday"]), "peak_pct", lambda t: t.offday == True),  # noqa: E712
        ("공연이 있으면 붐빈다 (쉬는 날)", od, "peak_pct", lambda t: t.n_venues > 0),
        ("공연이 있으면 붐빈다 (평일 19~20시)", wk, "eve", lambda t: t.n_venues > 0),
        ("봄·가을(4~6·9~11월) 공연일이 더 붐빈다", o, "peak_pct", lambda t: t.season == 1),
        ("기관 만차 기록일은 실제로 붐빈 날이다", cl, "peak_pct", lambda t: t.any_full == True),  # noqa: E712
        ("공연장 2곳 이상이면 더 붐빈다", o, "peak_pct", lambda t: t.multi),
        ("KSPO DOME 공연이 있으면 더 붐빈다", o, "peak_pct", lambda t: t.ev_kspo_dome == 1),
        ("비 오는 날 더 붐빈다 (1mm 이상)", o, "peak_pct", lambda t: t.rain == 1),
        ("일찍(17시 이전) 시작하면 더 붐빈다", o, "peak_pct", lambda t: t.early_start == 1),
        ("일찍(17시 이전) 시작하면 더 붐빈다 (19~20시)", o, "eve", lambda t: t.early_start == 1),
        ("오래 활동한 가수 공연은 자가용이 많다", o, "peak_pct", lambda t: t.veteran == 1),
        ("오래 활동한 가수 공연은 자가용이 많다 (19~20시)", o, "eve", lambda t: t.veteran == 1),
    ]
    out = []
    for name, t, y, f in rows:
        g = f(t).fillna(False).astype(bool)
        a, b, diff, p = perm_test(t[y], g)
        out.append({"가설": name, "지표": y, "해당/나머지 일수": f"{g.sum()}/{(~g).sum()}",
                    "해당 평균%": round(a, 1), "나머지 평균%": round(b, 1), "차이%p": round(diff, 1), "p": round(p, 3)})
    # 저녁 공연도 오후에 찬다: 첫 공연 18시인 쉬는 날, 70%에 처음 닿은 시각이 공연 1시간 이상 전인 날의 수
    s = o[(o.first_start_h > 17.9) & (o.first_start_h <= 18.9)]
    lead70 = (s.first_start_h - s.t70).dropna()
    note = (f"첫 공연이 18시인 쉬는 날 {len(s)}일 중 {int((lead70 >= 1).sum())}일이 공연 1시간 이상 전에 70%를 넘음 "
            f"(중앙값 {lead70.median():.2f}시간 전)")
    return pd.DataFrame(out), note


if __name__ == "__main__":
    t, note = run()
    txt = "\n".join([f"# 2025 입출차로 본 만차 가설 검증 ({date.today():%Y-%m-%d})", "",
                     "지표 peak_pct = 하루 최대 이용률(수용 2,200대 대비), eve = 19·20시 평균 이용률. "
                     "p = 순열검정(2만 번) 양측.", "", "```", t.to_string(index=False), "```", "", f"- {note}", ""])
    (REPORTS / f"hypotheses_2025_{date.today():%Y%m%d}.md").write_text(txt, encoding="utf-8")
    print(txt)
