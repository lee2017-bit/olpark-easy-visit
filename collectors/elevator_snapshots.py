"""서울교통공사 역 엘리베이터 가동현황 전체(약 870대)를 10분마다 저장 → 하루 안에 표시가 얼마나, 언제 바뀌는지 확인.

출처: 공공데이터포털 15143843 서울교통공사_교통약자 이용시설 승강기 가동현황 (getWksnElvtr).
      포털 안내는 5분마다 갱신이지만 행마다 갱신 시각은 없다.
산출: data/processed/elevator/snap_YYYYMMDD.jsonl.gz  한 줄 = {"t": "HH:MM 시각", "s": {승강기번호: 상태}}
      상태 M = 운행, S = 중지, null = 값 없음
사용: python -m collectors.elevator_snapshots record --every 10 --until 22:30
      python -m collectors.elevator_snapshots changes data/processed/elevator/snap_20261122.jsonl.gz
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import json
import time
from pathlib import Path

from olpark.common import PROCESSED, data_go_kr

KST = dt.timezone(dt.timedelta(hours=9))
DIR = PROCESSED / "elevator"


def fetch() -> list[dict]:
    b = json.loads(data_go_kr("B553766/wksn/getWksnElvtr", {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON"}))
    items = b["response"]["body"]["items"]
    return items["item"] if isinstance(items, dict) else items


def record(every: int, until: str, max_minutes: int) -> None:
    now = dt.datetime.now(KST)
    stop = now.replace(hour=int(until[:2]), minute=int(until[3:]), second=0)
    end = time.time() + max_minutes * 60 if max_minutes else None
    DIR.mkdir(parents=True, exist_ok=True)
    while dt.datetime.now(KST) < stop and (end is None or time.time() < end):
        t = dt.datetime.now(KST)
        out = DIR / f"snap_{t:%Y%m%d}.jsonl.gz"
        try:
            snap = {x["fcltNo"]: x.get("oprtngSitu") for x in fetch()}
            with gzip.open(out, "at", encoding="utf-8") as f:
                f.write(json.dumps({"t": t.strftime("%Y-%m-%dT%H:%M"), "s": snap}) + "\n")
            print(t.strftime("%H:%M"), len(snap), sum(v == "S" for v in snap.values()), flush=True)
        except Exception as e:  # 한 번 못 받아도 다음 회차는 계속
            print(t.strftime("%H:%M"), "error", type(e).__name__, flush=True)
        time.sleep(every * 60 - time.time() % (every * 60) + 30)


def changes(path: Path) -> list[dict]:
    """앞 기록과 상태가 달라진 승강기를 시각 순으로. 역 이름은 지금 받은 목록에서 붙인다."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    meta = {x["fcltNo"]: x for x in fetch()}
    out = []
    for a, b in zip(rows, rows[1:]):
        for k, v in b["s"].items():
            if a["s"].get(k) != v:
                m = meta.get(k, {})
                out.append({"t": b["t"], "fcltNo": k, "from": a["s"].get(k), "to": v,
                            "line": m.get("lineNm"), "station": m.get("stnNm"), "where": m.get("dtlPstn")})
    print(f"{len(rows)}회 기록 {rows[0]['t']} ~ {rows[-1]['t']}, 바뀐 횟수 {len(out)}, 승강기 {len({c['fcltNo'] for c in out})}대")
    print("시각별:", dict(collections.Counter(c["t"][11:] for c in out)))
    for c in out:
        print(c["t"][11:], c["from"], "→", c["to"], c["line"], c["station"], c["where"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--every", type=int, default=10)
    r.add_argument("--until", default="22:30")
    r.add_argument("--max-minutes", type=int, default=0)
    c = sub.add_parser("changes")
    c.add_argument("path", type=Path)
    a = ap.parse_args()
    if a.cmd == "record":
        record(a.every, a.until, a.max_minutes)
    else:
        changes(a.path)
