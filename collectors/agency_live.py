"""기관 홈페이지 실시간 주차대수(동2·남2·북2문)를 일정 간격으로 기록 → 기관 예상치·우리 안내와 비교.

출처: https://www.ksponco.or.kr/online/main/parking.do 의 "실시간 주차대수(동2문·남2문·북2문): N 대 주차 중 / 2,200대 가능"
산출: data/processed/agency_live.csv (captured_kst, live_parked, live_capacity, pct) 누적. 원본 HTML은 저장하지 않음.
사용: python -m collectors.agency_live --every 10 --until 22:30   (KST, 한 번만: 인자 없이)
"""
import argparse
import datetime as dt
import time

import pandas as pd

from collectors.agency_prediction import KST, URL, parse
from olpark.common import PROCESSED, http_get

OUT = PROCESSED / "agency_live.csv"


def once() -> dict:
    now = dt.datetime.now(KST)
    rec = parse(http_get(URL).decode("utf-8", "ignore"), now.isoformat(timespec="minutes"))
    row = {"captured_kst": rec["captured_kst"], "live_parked": rec["live_parked"],
           "live_capacity": rec["live_capacity"]}
    row["pct"] = round(row["live_parked"] / row["live_capacity"] * 100, 1) if row["live_parked"] else None
    df = pd.DataFrame([row])
    df.to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
    return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=0, help="분 간격 (0이면 한 번만)")
    ap.add_argument("--until", default="", help="KST HH:MM 까지 반복")
    ap.add_argument("--max-minutes", type=int, default=0, help="이 프로세스가 도는 최대 분")
    a = ap.parse_args()
    start = time.time()
    end = None
    if a.until:
        h, m = map(int, a.until.split(":"))
        end = dt.datetime.now(KST).replace(hour=h, minute=m, second=0, microsecond=0)
    while True:
        try:
            print(once(), flush=True)
        except Exception as e:  # 한 번 실패해도 다음 시각에 다시
            print("fail", type(e).__name__, str(e)[:120], flush=True)
        if not a.every:
            break
        nxt = time.time() + a.every * 60
        nxt -= nxt % (a.every * 60)  # 정각 기준 간격에 맞춤
        if end and dt.datetime.fromtimestamp(nxt, KST) > end:
            break
        if a.max_minutes and nxt - start > a.max_minutes * 60:
            break
        time.sleep(max(0, nxt - time.time()))
