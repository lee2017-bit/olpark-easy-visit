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


def collect_inout_compact(rows: int = 5000, gap: float = 20.0) -> str:
    """API_CPM_008(2025 입출차 전체구역)을 나눠 받아 필요한 열만 gzip CSV로 저장 (이어받기 가능).

    게이트웨이 제한이 '10초에 1회'라 앞 요청이 끝난 뒤 gap초를 기다린다. 큰 페이지는 504가 잦아 5천 건씩.
    파일 이름은 시작 위치(offset) 기준이라 페이지 크기를 바꿔도 이어받을 수 있다.
    산출: data/raw/kcisa_inout/compact_oNNNNNNN.csv.gz  (local_id, in_gate, in_time, out_gate, out_time)
    """
    import csv
    import gzip
    import io
    out = RAW / "kcisa_inout"
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "compact_total.txt"
    total = int(meta.read_text()) if meta.exists() else None
    covered = []
    for f in out.glob("compact_o*.csv.gz"):
        a = int(f.name[len("compact_o"):-len(".csv.gz")])
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            covered.append((a, a + sum(1 for _ in fh) - 1))
    offset, last_end, fails = 0, 0.0, 0
    while total is None or offset < total:
        if any(a <= offset < b for a, b in covered):
            offset += rows
            continue
        wait = gap - (time.time() - last_end)
        if wait > 0:
            time.sleep(wait)
        try:
            b = kcisa("openapi/API_CPM_008/request", "kcisa_inout",
                      {"numOfRows": rows, "pageNo": offset // rows + 1}, timeout=120, retries=1)
        except FetchError as e:
            last_end = time.time()
            fails += 1
            print(f"offset {offset} 실패 {fails}: {str(e)[:60]}", flush=True)
            if fails >= 30:
                return f"inout: 연속 실패로 중단 — offset {offset}부터 다시 실행하면 이어받음"
            time.sleep(gap * (2 if "429" in str(e) else 1))
            continue
        last_end, fails = time.time(), 0
        obj = json.loads(b)
        total = _total(obj) or total
        if total:
            meta.write_text(str(total))
        items = obj.get("response", {}).get("body", {}).get("items", {}) or {}
        items = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(items, dict):
            items = [items]
        if not items:
            return f"inout: offset {offset}에서 빈 응답으로 종료"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["local_id", "in_gate", "in_time", "out_gate", "out_time"])
        for it in items:
            w.writerow(_parse_inout(it))
        (out / f"compact_o{offset:07d}.csv.gz").write_bytes(gzip.compress(buf.getvalue().encode("utf-8")))
        covered.append((offset, offset + len(items)))
        print(f"offset {offset} 저장 {len(items)}건 / {total}", flush=True)
        offset += rows
    return f"inout: 완료 (totalCount={total})"

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
