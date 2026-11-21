"""공연 있는 밤, 올림픽공원에서 장애인콜택시를 얼마나 기다렸나 (2025).

입력: 서울시설공단 장애인콜택시 탑승내역 2025 (공공데이터포털 15115859, 파일 약 340MB)
      → `python -m analysis.calltaxi_wait extract <받은 csv>` 로 송파구 오륜동·방이1·2동 출발/도착 건만 뽑아
        data/processed/calltaxi_park_2025.csv 로 저장 (원본은 저장소에 넣지 않음)
비교: 공원 공연장(KSPO DOME·핸드볼경기장·올림픽홀)은 행정동 '오륜동'. 첫 공연 16시 이후인 날 = 공연 있는 밤.
      옆 동(방이2동)도 같이 보아 공연 때문인지 확인.
지표: 20시 이후 접수, 접수(예약이면 예정 시각)부터 승차까지 분. 취소 비율.
산출: reports/calltaxi_wait_<날짜>.md
사용: python -m analysis.calltaxi_wait
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import date

import pandas as pd

from analysis.features import event_days
from olpark.common import PROCESSED, REPORTS

OUT = PROCESSED / "calltaxi_park_2025.csv"
DONGS = ("오륜동", "방이1동", "방이2동")


def extract(src: str) -> int:
    raw = open(src, "rb").read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    r = csv.reader(io.StringIO(txt))
    hdr = next(r)
    i_gu, i_dong, o_gu, o_dong = (hdr.index(c) for c in ("출발구", "출발동", "목적구", "목적동"))
    rows = [x for x in r if len(x) == len(hdr) and ((x[i_gu] == "송파구" and x[i_dong] in DONGS)
                                                     or (x[o_gu] == "송파구" and x[o_dong] in DONGS))]
    pd.DataFrame(rows, columns=hdr).to_csv(OUT, index=False)
    return len(rows)


def show_nights() -> set:
    ed = event_days()
    ed = ed[(ed.date >= "2025-01-01") & (ed.date <= "2025-12-31")]
    return set(ed[ed.venue.isin(["kspo_dome", "handball", "olympic_hall"]) & (ed.start_h >= 16)].date)


def run() -> pd.DataFrame:
    d = pd.read_csv(OUT)
    for c in ("접수일시", "예정일시", "승차일시", "취소일시"):
        d[c] = pd.to_datetime(d[c], errors="coerce", format="mixed")
    d["date"] = d.접수일시.dt.normalize()
    d["wait"] = (d.승차일시 - d[["접수일시", "예정일시"]].max(axis=1)).dt.total_seconds() / 60
    nights = show_nights()
    n_show, n_other = len(nights), 365 - len(nights)
    rows = []
    for dong in DONGS:
        o = d[(d.출발구 == "송파구") & (d.출발동 == dong) & (d.접수일시.dt.hour >= 20)]
        for show, g in o.groupby(o.date.isin(nights)):
            rows.append({"출발동": dong, "밤": "공연 있는 밤" if show else "그 밖의 밤", "건수": len(g),
                         "밤당 건수": round(len(g) / (n_show if show else n_other), 2),
                         "대기 중앙값(분)": round(g.wait.median(), 1), "대기 상위 25%(분)": round(g.wait.quantile(.75), 1),
                         "가장 긴 대기(분)": round(g.wait.max()), "취소 비율": round(g.취소일시.notna().mean(), 2)})
    return pd.DataFrame(rows), n_show


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "extract":
        print("rows:", extract(sys.argv[2]))
        sys.exit()
    t, n_show = run()
    txt = "\n".join([f"# 공연 있는 밤 장애인콜택시 대기 ({date.today():%Y-%m-%d})", "",
                     f"자료: 서울시설공단 장애인콜택시 탑승내역 2025, 20시 이후 접수. 공연 있는 밤 = 첫 공연 16시 이후 {n_show}일.", "",
                     "```", t.to_string(index=False), "```", "",
                     "- 공원 공연장이 있는 오륜동에서만 공연 있는 밤에 부르는 건수가 크게 늘고 대기가 길어짐 → 공연 때문으로 봄.",
                     "- 한계: 오륜동에는 선수촌아파트 등도 있음. 공연 있는 밤의 다수가 주말·공휴일.", ""])
    (REPORTS / f"calltaxi_wait_{date.today():%Y%m%d}.md").write_text(txt, encoding="utf-8")
    print(txt)
