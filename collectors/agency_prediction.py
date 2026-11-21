"""기관 「올림픽공원 주차장 예상 이용률 서비스」 스냅샷.

출처: https://www.ksponco.or.kr/online/main/parking.do (주말에만 예상치 제공)
우리 예측과 비교할 기준선(baseline)으로 쓰기 위해 원본 HTML과 파싱 결과를 시각별로 쌓습니다.
산출: data/raw/agency_prediction/YYYYMMDD_HHMM.html, data/processed/agency_prediction.csv (누적)
사용: python -m collectors.agency_prediction
"""
import datetime as dt
import html
import re

import pandas as pd

from olpark.common import PROCESSED, RAW, http_get, save_bytes

URL = "https://www.ksponco.or.kr/online/main/parking.do"
KST = dt.timezone(dt.timedelta(hours=9))


def parse(text: str, captured: str) -> dict:
    # 주석(<!-- -->) 안의 견본 공연 행(산타와 빈양말·미스터트롯)은 실제 공연이 아니므로 뺌
    t = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", "", text, flags=re.S)
    x = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    x = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", x))
    live = re.search(r"실시간 주차대수[^:]*:\s*\n?\s*([\d,]+)\s*대.*?([\d,]+)\s*대\s*가능", x, re.S)
    preds = re.findall(r"(\d{4}-\d\d-\d\d)\s+(\d\d:\d\d):\d\d\s*\n\s*(\d+)%", x)
    days = re.findall(r"(\d{4}-\d\d-\d\d) \((.)요일\)", x)
    ev_block = x[x.find("공연정보"):x.find("주차장 예상 이용률", x.find("공연정보"))]
    return {
        "captured_kst": captured,
        "live_parked": int(live.group(1).replace(",", "")) if live else None,
        "live_capacity": int(live.group(2).replace(",", "")) if live else None,
        "days": [d for d, _ in days],
        "pred": [(d, h, int(p)) for d, h, p in preds],
        "events_text": ev_block.strip()[:2000],
    }


def snapshot() -> dict:
    now = dt.datetime.now(KST)
    b = http_get(URL)
    stamp = now.strftime("%Y%m%d_%H%M")
    save_bytes(RAW / "agency_prediction" / f"{stamp}.html", b)
    rec = parse(b.decode("utf-8", "ignore"), now.isoformat(timespec="minutes"))
    rows = [{"captured_kst": rec["captured_kst"], "date": d, "time": h, "pred_pct": p,
             "live_parked": rec["live_parked"], "live_capacity": rec["live_capacity"]}
            for d, h, p in rec["pred"]] or [{"captured_kst": rec["captured_kst"], "date": None,
                                             "time": None, "pred_pct": None,
                                             "live_parked": rec["live_parked"],
                                             "live_capacity": rec["live_capacity"]}]
    f = PROCESSED / "agency_prediction.csv"
    df = pd.DataFrame(rows)
    if f.exists():
        df = pd.concat([pd.read_csv(f), df], ignore_index=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False)
    return rec


if __name__ == "__main__":
    r = snapshot()
    print("실시간:", r["live_parked"], "/", r["live_capacity"], "| 대상일:", r["days"])
    print("예상 이용률:", r["pred"][:20])
