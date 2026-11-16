"""문화공공데이터광장 주차 API 수집.

- linked : API_CPM_009  올림픽공원 2025 차량입출차·공연·날씨 연계 데이터 (약 7,803건)
- inout  : API_CPM_008  올림픽공원 입출차정보(전체구역) 2025 (약 240만 건)

키: CULTURE_GO_KR_KEY_LINKED / CULTURE_GO_KR_KEY_INOUT
페이지 단위로 저장하고, 중단되면 이어받습니다.
산출: data/raw/kcisa_<name>/page_NNNNN.json
사용: python -m collectors.kcisa_parking [linked|inout|all] [--probe] [--max-pages N]
"""
import json
import sys
import time

from olpark.common import RAW, FetchError, kcisa, save_bytes

APIS = {
    "linked": ("openapi/API_CPM_009/request", "kcisa_linked", 1000),
    "inout": ("openapi/API_CPM_008/request", "kcisa_inout", 1000),
}


def _total(obj):
    body = obj.get("response", {}).get("body", obj)
    for k in ("totalCount", "total_count", "totalcount"):
        if k in body:
            return int(body[k])
    return None


def collect(name: str, probe: bool = False, max_pages: int | None = None) -> str:
    path, key, rows = APIS[name]
    out = RAW / f"kcisa_{name}"
    if probe:
        rows = 5
    page = 1
    while True:
        f = out / f"page_{page:05d}.json"
        if not f.exists() or probe:
            try:
                b = kcisa(path, key, {"numOfRows": rows, "pageNo": page}, timeout=120, retries=2)
            except FetchError as e:
                return f"{name}: 실패 ({e}) — {page - 1}페이지까지 저장됨"
            save_bytes(f if not probe else out / "probe.json", b)
            time.sleep(0.3)
            if probe:
                obj = json.loads(b)
                return f"{name}: 성공 totalCount={_total(obj)} 샘플={str(obj)[:300]}"
        obj = json.loads(f.read_text(encoding="utf-8"))
        total = _total(obj)
        if total is None or page * rows >= total or (max_pages and page >= max_pages):
            return f"{name}: 완료 {page}페이지 (totalCount={total})"
        page += 1


INOUT_RE = None


def _parse_inout(item: dict) -> list:
    """'입구:동2문입구#1, 입차시간:2025-08-24 13:48:38, 출구:동2문출구#1, 출차시간:...' → [id, 입구, 입차, 출구, 출차]"""
    import re
    global INOUT_RE
    if INOUT_RE is None:
        INOUT_RE = re.compile(r"입구:([^,]*),\s*입차시간:([^,]*),\s*출구:([^,]*),\s*출차시간:(.*)")
    m = INOUT_RE.match(item.get("DESCRIPTION") or "")
    g = [x.strip() for x in m.groups()] if m else ["", item.get("ISSUED_DATE") or "", "", ""]
    return [item.get("LOCAL_ID") or ""] + g


def collect_inout_compact(rows: int = 10000, gap: float = 10.5) -> str:
    """API_CPM_008(2025 입출차 전체구역)을 1만 건씩 받아 필요한 열만 gzip CSV로 저장 (이어받기 가능).

    게이트웨이 제한이 '10초에 1회'라 요청 간격을 둔다. 원본 JSON(페이지당 약 3.7MB)은 저장하지 않는다.
    산출: data/raw/kcisa_inout/compact_NNNNN.csv.gz  (local_id, in_gate, in_time, out_gate, out_time)
    """
    import csv
    import gzip
    import io
    out = RAW / "kcisa_inout"
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "compact_total.txt"
    total = int(meta.read_text()) if meta.exists() else None
    page, last = 1, 0.0
    while True:
        f = out / f"compact_{page:05d}.csv.gz"
        if not f.exists():
            wait = gap - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            for attempt in range(6):
                last = time.time()
                try:
                    b = kcisa("openapi/API_CPM_008/request", "kcisa_inout",
                              {"numOfRows": rows, "pageNo": page}, timeout=300, retries=1)
                    break
                except FetchError as e:
                    print(f"page {page} 재시도 {attempt + 1}: {str(e)[:80]}", flush=True)
                    time.sleep(gap * (attempt + 2))
                    last = time.time()
            else:
                return f"inout: 중단 — {page - 1}페이지까지 저장됨 (다시 실행하면 이어받음)"
            obj = json.loads(b)
            total = _total(obj) or total
            if total:
                meta.write_text(str(total))
            items = obj.get("response", {}).get("body", {}).get("items", {}) or {}
            items = items.get("item", []) if isinstance(items, dict) else items
            if isinstance(items, dict):
                items = [items]
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["local_id", "in_gate", "in_time", "out_gate", "out_time"])
            for it in items:
                w.writerow(_parse_inout(it))
            f.write_bytes(gzip.compress(buf.getvalue().encode("utf-8")))
            print(f"page {page} 저장 {len(items)}건 (total={total})", flush=True)
            if not items:
                return f"inout: 빈 페이지 {page}에서 종료"
        if total and page * rows >= total:
            return f"inout: 완료 {page}페이지 (totalCount={total})"
        page += 1

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--compact" in args:
        print(collect_inout_compact())
        sys.exit()
    which = [a for a in args if a in ("linked", "inout", "all")] or ["all"]
    names = list(APIS) if which[0] == "all" else which
    mp = int(args[args.index("--max-pages") + 1]) if "--max-pages" in args else None
    for n in names:
        print(collect(n, probe="--probe" in args, max_pages=mp))
