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


if __name__ == "__main__":
    args = sys.argv[1:]
    which = [a for a in args if a in ("linked", "inout", "all")] or ["all"]
    names = list(APIS) if which[0] == "all" else which
    mp = int(args[args.index("--max-pages") + 1]) if "--max-pages" in args else None
    for n in names:
        print(collect(n, probe="--probe" in args, max_pages=mp))
