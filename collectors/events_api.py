"""한국체육산업개발 올림픽공원 공연정보 API (문화공공데이터광장, KSCperf) 수집.

키: CULTURE_GO_KR_KEY_EVENT
산출: data/raw/events_api/page_NNN.json, data/processed/events_api.csv
사용: python -m collectors.events_api
"""
import json
import time

import pandas as pd

from olpark.common import PROCESSED, RAW, kcisa, save_bytes

PATH = "openapi/service/rest/meta/KSCperf"
ROWS = 100


def fetch(refresh: bool = False) -> pd.DataFrame:
    out = RAW / "events_api"
    page, total = 1, None
    while True:
        f = out / f"page_{page:03d}.json"
        if refresh or not f.exists():
            b = kcisa(PATH, "kcisa_event", {"numOfRows": ROWS, "pageNo": page})
            save_bytes(f, b)
            time.sleep(0.5)
        body = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]
        total = int(body.get("totalCount") or 0)
        if page * ROWS >= total:
            break
        page += 1
    rows = []
    for f in sorted(out.glob("page_*.json")):
        items = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]["items"]
        items = items.get("item", []) if isinstance(items, dict) else []
        rows.extend(items if isinstance(items, list) else [items])
    df = pd.DataFrame(rows)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "events_api.csv", index=False)
    return df


if __name__ == "__main__":
    df = fetch()
    print(f"events_api rows: {len(df)}")
    print(df.columns.tolist())
