"""기관에서 파일로 받은 '올림픽공원 2025 차량입출차·공연·날씨 연계 데이터'(또는 입출차 원자료) 넣기.

API(API_CPM_009/008)가 504로 막혀 있어, 기관이 CSV/XLSX로 보내 주면 이 스크립트로 정리합니다.
열 이름은 받아 봐야 알 수 있어서, 아래 CANDIDATES에 흔한 이름을 넣어 두고 자동으로 맞춥니다.
맞지 않으면 실행 결과에 원래 열 목록이 나오니 CANDIDATES에 추가하면 됩니다.

사용: python -m collectors.linked_file <받은파일.csv|xlsx> [linked|inout]
산출: data/raw/kcisa_<kind>/received.<ext> (원본 보관, 저장소에는 안 올라감)
      data/processed/linked_2025_hourly.csv 또는 data/processed/inout_2025.csv
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

from olpark.common import PROCESSED, RAW, decode_csv_bytes

CANDIDATES = {
    "date": ["일자", "날짜", "기준일자", "입차일", "date", "DATE", "YMD"],
    "hour": ["시간", "시간대", "기준시간", "hour", "HOUR", "HH"],
    "cars": ["차량대수", "주차대수", "입차대수", "차량수", "cars", "CNT", "count"],
    "event": ["공연명", "공연제목", "행사명", "title", "PERF_NM"],
    "venue": ["공연장소", "공연장", "장소", "place", "PLC"],
    "temp": ["기온", "temperature", "TA"],
    "rain": ["강수량", "rain", "RN"],
    "t_in": ["입차일시", "inDt", "IN_DT"],
    "t_out": ["출차일시", "outDt", "OUT_DT"],
    "zone": ["주차구역", "구역", "zone"],
}


def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    from io import StringIO
    return pd.read_csv(StringIO(decode_csv_bytes(path.read_bytes())))


def normalize(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    found = {}
    for std, names in CANDIDATES.items():
        for n in names:
            hit = [c for c in df.columns if str(c).strip().lower() == n.lower()]
            if hit:
                found[std] = hit[0]
                break
    out = df.rename(columns={v: k for k, v in found.items()})
    return out, found


def main(src: str, kind: str = "linked"):
    p = Path(src)
    dest = RAW / f"kcisa_{kind}" / f"received{p.suffix.lower()}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(p, dest)
    df = read_any(dest)
    print("rows:", len(df), "| 원래 열:", list(df.columns))
    df, found = normalize(df)
    print("맞춘 열:", found)
    name = "linked_2025_hourly.csv" if kind == "linked" else "inout_2025.csv"
    df.to_csv(PROCESSED / name, index=False)
    print("저장:", PROCESSED / name)
    print(df.head(5).to_string())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "linked")
