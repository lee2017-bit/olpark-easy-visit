"""공원 근처 지하철역 엘리베이터 가동현황 → 사이트가 읽는 작은 JSON (GitHub Actions가 10분마다 실행).

출처: 서울교통공사_교통약자이용정보 getWksnElvtr (공공데이터포털 15143843, 엘리베이터는 5분마다 갱신)
      oprtngSitu(가동현황): 'M' 대부분 · 'S' 일부. 날마다 역마다 바뀌는 것을 확인함(11/15→11/22 18대 변동).
      코드 뜻은 명세에 없어 'M'=운행, 'S'=중지로 읽고, 그 밖의 값은 '확인 필요'로 둔다.
범위: 5호선 올림픽공원, 8호선 몽촌토성. 9호선(올림픽공원·한성백제)은 이 API에 없어 '실시간 정보 없음'.
키:   DATA_GO_KR_KEY (사이트에는 결과만 올리고 키는 올리지 않음)
사용: python -m collectors.live_status <출력 json 경로>
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from olpark.common import data_go_kr

KST = dt.timezone(dt.timedelta(hours=9))
STATIONS = {("5호선", "올림픽공원"), ("8호선", "몽촌토성")}
STATE = {"M": "ok", "S": "stop"}


def elevators() -> list[dict]:
    b = data_go_kr("B553766/wksn/getWksnElvtr", {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON"})
    items = json.loads(b)["response"]["body"]["items"]["item"]
    out = []
    for x in items:
        if (x.get("lineNm"), x.get("stnNm")) not in STATIONS:
            continue
        place = str(x.get("vcntEntrcNo") or "")
        out.append({
            "line": x["lineNm"], "station": x["stnNm"],
            "kind": "inside" if place == "내부" else "exit",
            "exit": None if place == "내부" else place,
            "where": x.get("dtlPstn") or "",
            "floors": f"{x.get('bgngFlr') or ''}~{x.get('endFlr') or ''}",
            "code": x.get("oprtngSitu"),
            "state": STATE.get(x.get("oprtngSitu"), "unknown"),
        })
    return sorted(out, key=lambda e: (e["line"], e["kind"] != "exit", e["exit"] or "", e["where"]))


def main(path: str) -> dict:
    now = dt.datetime.now(KST).isoformat(timespec="minutes")
    try:
        el = elevators()
        res = {"checked_at": now, "elevators": el, "ok": True}
    except Exception as e:  # 실패도 기록해 사이트가 '확인 못 함'이라고 말하게
        res = {"checked_at": now, "elevators": [], "ok": False, "error": type(e).__name__}
    res["source"] = {"name": "서울교통공사_교통약자이용정보 (엘리베이터 가동현황)",
                     "url": "https://www.data.go.kr/data/15143843/openapi.do"}
    res["not_covered"] = "9호선 올림픽공원·한성백제역 엘리베이터는 실시간 가동현황이 공개되지 않아요"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = main(sys.argv[1] if len(sys.argv) > 1 else "out/status.json")
    print(r["checked_at"], r["ok"], [(e["station"], e["exit"] or "내부", e["state"]) for e in r["elevators"]])
