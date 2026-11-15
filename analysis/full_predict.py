"""대안 분석: 2025 주말·공휴일 '만차 발생 여부'와 '만차 구역 수' 예측.

데이터: 기관 주차장 혼잡도 기록(2025-02-12~12-31), 공연 일정, 가수 이력, 기상청 ASOS 일자료(서울)
검증: 하루씩 빼고 학습 → 그 날 예측 (leave-one-day-out)
비교:
  base_rate   : 학습 기간 만차 비율 하나 (기관식 '일괄' 예측에 해당)
  venues_only : 공연장 여부·동시 공연 수만
  full        : + 시작 시각, 장수 가수, 계절, 공휴일, 비·기온
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis import congestion_log
from analysis.artist_history import features_for, history_table
from analysis.features import CONCERT_VENUES, event_days
from olpark.common import PROCESSED, REPORTS

VENUE_COLS = [f"ev_{v}" for v in CONCERT_VENUES.values()]
SETS = {
    "venues_only": VENUE_COLS + ["n_venues"],
    "full": VENUE_COLS + ["n_venues", "early_start", "veteran", "season", "holiday", "rain", "maxTa"],
}


def build() -> pd.DataFrame:
    d = congestion_log.daily()
    d = d[d.offday].copy()
    ed = event_days()
    ed = ed[(ed.date >= congestion_log.START) & (ed.date <= congestion_log.END)].copy()
    hist = history_table()
    af = features_for(ed.title, ed.date.dt.year, hist)
    ed = pd.concat([ed, af], axis=1)
    agg = ed.groupby("date").agg(max_years=("years_active_at_venue", "max"),
                                 veteran_titles=("title", lambda s: " / ".join(
                                     sorted(set(s[ed.loc[s.index, "years_active_at_venue"] >= 8])))))
    d = d.merge(agg, on="date", how="left").fillna({"max_years": 0, "veteran_titles": ""})
    d["veteran"] = (d.max_years >= 8).astype(int)
    d["early_start"] = (d.first_start_h.fillna(24) <= 17).astype(int)
    d["season"] = d.date.dt.month.isin([4, 5, 6, 9, 10, 11]).astype(int)
    w = pd.read_csv(PROCESSED / "weather_daily.csv", parse_dates=["date"])
    d = d.merge(w[["date", "sumRn", "maxTa"]], on="date", how="left")
    d["rain"] = (d.sumRn.fillna(0) >= 1).astype(int)
    d["holiday"] = d.holiday.astype(int)
    for c in VENUE_COLS + ["n_venues"]:
        d[c] = d[c].fillna(0)
    d["y"] = d.any_full.astype(int)
    return d


def _std(train: pd.DataFrame, test: pd.DataFrame, cols):
    mu, sd = train[cols].mean(), train[cols].std().replace(0, 1)
    X = np.column_stack([np.ones(len(train)), ((train[cols] - mu) / sd).values])
    Xt = np.column_stack([np.ones(len(test)), ((test[cols] - mu) / sd).values])
    return X, Xt


def logistic(X, y, lam=1.0, iters=50):
    w = np.zeros(X.shape[1])
    R = lam * np.eye(X.shape[1]); R[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        W = p * (1 - p) + 1e-6
        g = X.T @ (p - y) + R @ w
        H = X.T @ (X * W[:, None]) + R
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return w


def ridge(X, y, lam=1.0):
    R = lam * np.eye(X.shape[1]); R[0, 0] = 0
    return np.linalg.solve(X.T @ X + R, X.T @ y)


def auc(y, p):
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    return float(((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean()))


def loo(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i in range(len(d)):
        tr, te = d.drop(d.index[i]), d.iloc[[i]]
        r = {"date": te.date.iloc[0], "y": te.y.iloc[0], "lots": te.full_lots.iloc[0],
             "p_base_rate": tr.y.mean(), "lots_base_rate": tr.full_lots.mean()}
        for name, cols in SETS.items():
            X, Xt = _std(tr, te, cols)
            r[f"p_{name}"] = float((1 / (1 + np.exp(-Xt @ logistic(X, tr.y.values))))[0])
            r[f"lots_{name}"] = float(np.clip(Xt @ ridge(X, tr.full_lots.values), 0, 11)[0])
        rows.append(r)
    return pd.DataFrame(rows)


def score(P: pd.DataFrame) -> pd.DataFrame:
    out = []
    for m in ["base_rate"] + list(SETS):
        p, y = P[f"p_{m}"].values, P.y.values
        out.append({"model": m, "brier": np.mean((p - y) ** 2), "auc": auc(y, p),
                    "accuracy@0.5": np.mean((p >= 0.5) == y),
                    "lots_MAE": np.mean(np.abs(P[f"lots_{m}"] - P.lots))})
    return pd.DataFrame(out).set_index("model")


def coefficients(d: pd.DataFrame) -> pd.Series:
    cols = SETS["full"]
    X, _ = _std(d, d.iloc[:1], cols)
    w = logistic(X, d.y.values)
    return pd.Series(w[1:], index=cols).sort_values()


def group_rates(d: pd.DataFrame) -> dict:
    ev = d[d.n_venues > 0]
    def rate(mask):
        s = ev[mask]
        return f"{int(s.y.sum())}/{len(s)}일 ({s.y.mean():.0%}), 평균 만차 구역 {s.full_lots.mean():.1f}"
    return {"장수 가수 공연 있음": rate(ev.veteran == 1), "장수 가수 없음": rate(ev.veteran == 0),
            "비 1mm 이상": rate(ev.rain == 1), "비 없음": rate(ev.rain == 0),
            "봄·가을(4~6, 9~11월)": rate(ev.season == 1), "여름·겨울": rate(ev.season == 0),
            "KSPO DOME 공연": rate(ev.ev_kspo_dome == 1), "KSPO DOME 없음": rate(ev.ev_kspo_dome == 0)}


if __name__ == "__main__":
    d = build()
    d.to_csv(PROCESSED / "full_predict_days.csv", index=False)
    P = loo(d)
    P.to_csv(PROCESSED / "full_predict_loo.csv", index=False)
    s = score(P)
    print("days:", len(d), "full days:", int(d.y.sum()))
    print(s.round(3).to_string())
    print("\n계수(표준화, 전체 학습):\n", coefficients(d).round(2).to_string())
    print()
    for k, v in group_rates(d).items():
        print(f"{k}: {v}")
