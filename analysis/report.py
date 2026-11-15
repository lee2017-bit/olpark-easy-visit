"""분석 결과를 reports/analysis_<날짜>.md 로 정리."""
import datetime as dt
import json

import pandas as pd

from analysis import congestion_log
from analysis.evaluate import build_frame, evaluate
from analysis.features import daily_calendar
from analysis.occupancy import CAPACITY, daily_summary, load_inout, occupancy
from olpark.common import PROCESSED, REPORTS


def md(df: pd.DataFrame) -> str:
    return df.to_markdown() if hasattr(df, "to_markdown") else "```\n" + df.to_string() + "\n```"


def main():
    rec = load_inout()
    occ = occupancy(rec)
    cal = daily_calendar(occ.date.min(), occ.date.max())
    day = daily_summary(rec, occ).merge(cal[["date", "offday", "n_venues", "first_start_h", "titles"]], on="date")
    wk = day[day.offday][["date", "peak", "peak_pct", "peak_time", "occ_1700", "occ_1900", "long_stay_6h", "n_venues", "titles"]]
    s, _ = evaluate(build_frame(occ, cal))
    cd = congestion_log.daily()
    cs = congestion_log.summary(cd)
    acc = json.loads((PROCESSED / "accessibility.json").read_text(encoding="utf-8"))
    ap = PROCESSED / "agency_prediction.csv"
    agency = pd.read_csv(ap) if ap.exists() else pd.DataFrame()

    lines = [f"# 올림픽공원 주차·교통약자 분석 ({dt.date.today()})", "",
             "## 1. 2024-07 주말·공휴일 주차대수 (동2·남2·북2문, 수용 2,200대)", "",
             "```", wk.to_string(index=False), "```", "",
             "## 2. 17~21시 30분 단위 이용률 예측 비교 (2024-07 주말 8일, 하루씩 빼고 검증)", "",
             "```", s.round(3).to_string(), "```", "",
             "- agency_flat_76은 기관 페이지 표시값(76%)을 그대로 쓴 것. 기관의 주차대수 정의(장기 주차 포함 여부)가 우리 계산과 다를 수 있어 직접 비교는 참고용.",
             "- 표본이 8일뿐이라 모델 간 차이는 의미 없음. 2025년 데이터 확보 후 재평가 필요.", "",
             f"## 3. 2025 혼잡도 기록 × 공연 ({congestion_log.START}~{congestion_log.END})", "",
             "```", cs.to_string(), "```", "",
             "## 4. 교통약자 데이터", "",
             "- 지하철 외부 엘리베이터: " + "; ".join(
                 f"{x['lineNm']} {x['stnNm']} {x.get('dtlPstn')}" for x in acc["elevators"] if "외부" in x["fcltNm"]),
             f"- 공원 안내 출구: {acc['agency_static']['subway_exit_guidance']['text']}",
             f"- 장애인 주차: 기관 공지 {sum(acc['agency_static']['disabled_parking_by_spot']['spots'].values())}면 / 한국관광공사 '{acc['barrier_free_knto'].get('parking')}'",
             f"- 휠체어 대여: {acc['agency_static']['wheelchair_rental']['places']} {acc['agency_static']['wheelchair_rental']['hours']}, {acc['agency_static']['wheelchair_rental']['rule']}", "",
             "## 5. 기관 예상 이용률 스냅샷", "",
             "```", agency.tail(12).to_string(index=False) if len(agency) else "(없음)", "```"]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"analysis_{dt.date.today():%Y%m%d}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
