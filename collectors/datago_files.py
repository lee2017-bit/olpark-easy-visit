"""공공데이터포털 파일데이터 다운로드 (키 불필요).

산출: data/raw/files/<name>.csv (UTF-8로 변환)
사용: python -m collectors.datago_files
"""
import json
import time

from olpark.common import RAW, decode_csv_bytes, http_get

FILES = {
    # name: (publicDataPk, publicDataDetailPk)
    "inout_202407": ("15138735", "uddi:d0e4bf79-59b5-4dc4-b5b8-ecf05e94e98c"),   # 입출차 2024-07 (동2·남2·북2문)
    "congestion_log": ("15164156", "uddi:34862174-8dc7-4230-9d35-ea44801c18f1"),  # 주차장 혼잡도 정보
    "monthly_parking": ("15131671", "uddi:927e88c8-da17-4883-a1d9-e3be66c858fc"),  # 월별 주차현황
}


def download(name: str, pk: str, dpk: str, refresh: bool = False):
    dest = RAW / "files" / f"{name}.csv"
    if dest.exists() and not refresh:
        return dest
    meta = json.loads(http_get("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
                               {"publicDataPk": pk, "publicDataDetailPk": dpk, "fileDetailSn": 1}))
    aid = meta["atchFileId"]
    b = http_get("https://www.data.go.kr/cmm/cmm/fileDownload.do",
                 {"atchFileId": aid, "fileDetailSn": 1}, timeout=300)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(decode_csv_bytes(b), encoding="utf-8")
    time.sleep(1)
    return dest


if __name__ == "__main__":
    for n, (pk, dpk) in FILES.items():
        p = download(n, pk, dpk)
        print(n, p.stat().st_size, "bytes")
