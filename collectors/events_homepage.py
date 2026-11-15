"""올림픽공원 홈페이지 공연 일정 (월별 AJAX) 수집.

출처: https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoList?mid=a20301010100
산출: data/raw/events_homepage/YYYYMM.json, data/processed/events_homepage.csv
사용: python -m collectors.events_homepage 202401 202612
"""
import json
import sys
import time

import pandas as pd

from olpark.common import PROCESSED, RAW, http_get, save_bytes

URL = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListAjax.es"
VENUE = {"01": "올림픽홀", "02": "KSPO DOME", "03": "핸드볼경기장", "04": "우리금융아트홀",
         "05": "기타", "06": "88잔디마당", "07": "뮤즈라이브"}
FIELDS = ["evtSeq", "title", "beginDt", "endDt", "tm", "plc", "plcCd", "tktPrc", "seeAge",
          "ndTm", "muf", "spns", "regDate", "evtLink"]


def months(start: str, end: str):
    y, m = int(start[:4]), int(start[4:])
    while y * 100 + m <= int(end):
        yield f"{y}{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def fetch(start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    out = RAW / "events_homepage"
    for ym in months(start, end):
        f = out / f"{ym}.json"
        if f.exists() and not refresh:
            continue
        body = json.dumps({"nowYM": ym, "plcCd": ""}).encode()
        b = http_get(URL, method="POST", body=body,
                     headers={"Content-Type": "application/json;charset=UTF-8"})
        save_bytes(f, b)
        time.sleep(0.7)
    rows = []
    for f in sorted(out.glob("*.json")):
        for part in json.loads(f.read_text(encoding="utf-8")):
            for it in part:
                rows.append({k: (it.get(k).strip() if isinstance(it.get(k), str) else it.get(k))
                             for k in FIELDS})
    df = pd.DataFrame(rows, columns=FIELDS)
    prev_f = PROCESSED / "events_homepage.csv"
    if prev_f.exists():  # CI에는 raw가 없으므로 기존 결과와 합침 (새로 받은 값 우선)
        prev = pd.read_csv(prev_f, dtype=str)[FIELDS]
        df = pd.concat([prev, df.astype(str).replace({"None": None})], ignore_index=True)
    df["evtSeq"] = df["evtSeq"].astype(str)
    df = df.drop_duplicates("evtSeq", keep="last")
    df["venue"] = df["plcCd"].map(VENUE).fillna("기타")
    df["run_days"] = (pd.to_datetime(df.endDt) - pd.to_datetime(df.beginDt)).dt.days + 1
    df = df.sort_values(["beginDt", "plcCd"])
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "events_homepage.csv", index=False)
    return df


def upcoming_range(months_ahead: int = 6) -> tuple[str, str]:
    import datetime as dt
    t = dt.date.today()
    y, m = t.year + (t.month - 1 + months_ahead) // 12, (t.month - 1 + months_ahead) % 12 + 1
    return f"{t.year}{t.month:02d}", f"{y}{m:02d}"


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--upcoming" in a:  # CI용: 이번 달~6개월 뒤를 새로 받음
        s, e = upcoming_range()
        df = fetch(s, e, refresh=True)
    else:
        a = a or ["202401", "202612"]
        df = fetch(a[0], a[1], refresh="--refresh" in a)
    print(f"events: {len(df)}  ({df.beginDt.min()} ~ {df.endDt.max()})")
    print(df.groupby("venue").size().to_string())
