"""공연 포스터 → 작은 썸네일 (site/data/posters/<evtSeq>.jpg).

원본: 올림픽공원 홈페이지 공연 목록이 쓰는 이미지(attachFiles/eventInfo/<fileNm>, 한 장에 1~4MB).
휴대폰에서 그대로 띄우기엔 무거워 폭 240px로 줄여 둔다. 포스터 저작권은 주최 측에 있으므로
사이트에서는 공연을 알아보는 작은 그림으로만 쓰고, 누르면 기관 공연 페이지로 간다.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

from olpark.common import ROOT, http_get

POSTER_URL = "https://www.ksponco.or.kr/olympicpark/attachFiles/eventInfo/{}"
VIEW_URL = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoView.es?mid=a20301010100&evtSeq={}"
OUT = ROOT / "site" / "data" / "posters"
SIZE = (240, 360)


def thumb(seq: str, file_nm: str | None) -> str | None:
    """썸네일 경로(site 기준)를 돌려준다. 이미 있으면 다시 받지 않고, 못 받으면 None."""
    f = OUT / f"{seq}.jpg"
    if not f.exists():
        if not file_nm or str(file_nm) == "nan":
            return None
        try:
            b = http_get(POSTER_URL.format(file_nm), timeout=60, retries=2)
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(b))).convert("RGB")
        except Exception as e:  # 포스터가 없어도 사이트는 만든다
            print(f"poster {seq}: {type(e).__name__}")
            return None
        im.thumbnail(SIZE, Image.LANCZOS)
        OUT.mkdir(parents=True, exist_ok=True)
        im.save(f, "JPEG", quality=72, optimize=True, progressive=True)
    return f"data/posters/{seq}.jpg"


def prune(keep: set[str]) -> None:
    """지난 공연 썸네일 정리."""
    if OUT.exists():
        for f in OUT.glob("*.jpg"):
            if f.stem not in keep:
                f.unlink()
