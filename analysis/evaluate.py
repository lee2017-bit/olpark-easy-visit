"""기관식 일괄 예측 vs 공연 정보 반영 예측 비교.

대상: 주말·공휴일의 17:00~21:00, 30분 단위 주차 이용률(%) — 기관 「예상 이용률 서비스」와 같은 범위.
모델:
  agency_flat_76 : 모든 시간대 76% (2026-11-14 기관 페이지에 실제로 표시된 값)
  flat_mean      : 학습 기간 평균 하나 (기관식 '일괄값'을 데이터로 맞춘 경우)
  slot_mean      : 시간대별 평균
  event_ridge    : 시간대 평균 + 공연 특성(공연장별 여부, 동시 공연장 수, 시작까지 남은 시간, 공휴일) 릿지 회귀
평가: 하루씩 빼고 학습 → 그 날 예측 (leave-one-day-out). 지표: 평균 절대오차(%p), 등급 일치율.
등급: <50 원활, 50~70 다소혼잡, 70~90 혼잡, ≥90 만차 (기관 페이지 범례 기준)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.features import CONCERT_VENUES, daily_calendar
from analysis.occupancy import CAPACITY

SLOTS = [f"{h:02d}:{m:02d}" for h in range(17, 21) for m in (0, 30)] + ["21:00"]


def grade(p):
    return np.select([p >= 90, p >= 70, p >= 50], ["만차", "혼잡", "다소혼잡"], "원활")


def build_frame(occ: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    o = occ[occ.slot.isin(SLOTS)].copy()
    o["pct"] = o.occ / CAPACITY * 100
    o["slot_h"] = o.t.dt.hour + o.t.dt.minute / 60
    df = o.merge(cal, on="date", how="left")
    df = df[df.offday]
    df["to_start"] = (df.first_start_h - df.slot_h).where(df.n_venues > 0, np.nan)
    return df


def _design(df: pd.DataFrame, slot_means: pd.Series) -> np.ndarray:
    ts = df.to_start.fillna(0)
    cols = [np.ones(len(df)), df.slot.map(slot_means).fillna(slot_means.mean()).values]
    for v in CONCERT_VENUES.values():
        cols.append(df[f"ev_{v}"].fillna(0).values)
    cols += [df.n_venues.fillna(0).values,
             (df.n_venues > 0).values * np.clip(ts, -3, 4).values,
             df.holiday.astype(float).values]
    return np.column_stack(cols)


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, lam: float = 5.0) -> dict:
    flat = train.pct.mean()
    sm = train.groupby("slot").pct.mean()
    X, Xt = _design(train, sm), _design(test, sm)
    reg = lam * np.eye(X.shape[1])
    reg[0, 0] = 0
    w = np.linalg.solve(X.T @ X + reg, X.T @ train.pct.values)
    return {"agency_flat_76": np.full(len(test), 76.0),
            "flat_mean": np.full(len(test), flat),
            "slot_mean": test.slot.map(sm).fillna(flat).values,
            "event_ridge": np.clip(Xt @ w, 0, 110)}


def evaluate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    preds = []
    for d in sorted(df.date.unique()):
        tr, te = df[df.date != d], df[df.date == d]
        if tr.date.nunique() < 3:
            continue
        p = fit_predict(tr, te)
        for k, v in p.items():
            preds.append(te[["date", "slot", "pct", "n_venues", "titles"]].assign(model=k, pred=v))
    P = pd.concat(preds)
    P["abs_err"] = (P.pred - P.pct).abs()
    P["grade_ok"] = grade(P.pred) == grade(P.pct)
    summary = P.groupby("model").agg(MAE_pctp=("abs_err", "mean"), grade_match=("grade_ok", "mean"),
                                     n_slots=("abs_err", "size")).sort_values("MAE_pctp")
    return summary, P


if __name__ == "__main__":
    from analysis.occupancy import load_inout, occupancy
    occ = occupancy(load_inout())
    cal = daily_calendar(occ.date.min(), occ.date.max())
    df = build_frame(occ, cal)
    s, P = evaluate(df)
    print("days:", df.date.nunique(), "slots:", len(df))
    print(s.round(3).to_string())
    print(P[P.model.isin(["agency_flat_76", "event_ridge"])].pivot_table(
        index=["date"], columns="model", values="abs_err", aggfunc="mean").round(1).to_string())
