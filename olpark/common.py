"""Shared helpers: paths, HTTP with retries, API-key handling.

API keys are read from environment variables only and are never printed,
logged, or written to disk. Error messages mask the key.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"

UA = "Mozilla/5.0 (compatible; olpark-contest-research/0.1)"

# Environment variable names for each provider's key.
KEY_ENV = {
    "data_go_kr": "DATA_GO_KR_KEY",
    "kcisa_linked": "CULTURE_GO_KR_KEY_LINKED",
    "kcisa_inout": "CULTURE_GO_KR_KEY_INOUT",
    "kcisa_event": "CULTURE_GO_KR_KEY_EVENT",
}


class FetchError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def get_key(name: str) -> str:
    env = KEY_ENV[name]
    val = os.environ.get(env)
    if not val:
        raise SystemExit(f"환경 변수 {env} 가 없습니다.")
    return val


def _mask(text: str, secret: str | None) -> str:
    if secret:
        text = text.replace(secret, "***").replace(urllib.parse.quote(secret, safe=""), "***")
    return text


def http_get(url: str, params: dict | None = None, *, secret: str | None = None,
             headers: dict | None = None, method: str = "GET", body: bytes | None = None,
             timeout: int = 90, retries: int = 4, backoff: float = 3.0) -> bytes:
    """GET/POST with retries on network errors and 5xx. `secret` is masked in errors."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe="%")
    hdr = {"User-Agent": UA}
    hdr.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdr, method=method, data=body)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = FetchError(e.code, _mask(e.read()[:200].decode("utf-8", "ignore"), secret))
            if e.code < 500:
                raise last
        except Exception as e:  # network reset, timeout
            last = FetchError("NET", _mask(str(e)[:200], secret))
        time.sleep(backoff * (attempt + 1))
    raise last


def data_go_kr(path: str, params: dict, **kw) -> bytes:
    """Call apis.data.go.kr/<path> with DATA_GO_KR_KEY."""
    key = get_key("data_go_kr")
    k = key if "%" in key else urllib.parse.quote(key, safe="")
    p = {"serviceKey": k, **params}
    return http_get(f"https://apis.data.go.kr/{path}", p, secret=key, **kw)


def kcisa(path: str, key_name: str, params: dict, **kw) -> bytes:
    """Call api.kcisa.kr/<path> (문화공공데이터광장) with the matching culture.go.kr key."""
    key = get_key(key_name)
    p = {"serviceKey": urllib.parse.quote(key, safe=""), **params}
    return http_get(f"https://api.kcisa.kr/{path}", p, secret=key,
                    headers={"Accept": "application/json"}, **kw)


def save_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def save_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def decode_csv_bytes(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "ignore")
