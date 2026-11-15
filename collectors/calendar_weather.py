"""공휴일(한국천문연구원 특일 정보)과 단기예보(기상청) 수집.

키: DATA_GO_KR_KEY
산출: data/processed/holidays.csv, data/raw/weather/fcst_<base>.json, data/processed/weather_forecast.csv
사용: python -m collectors.calendar_weather [holidays 2024 2026] [forecast]
"""
import datetime as dt
import json
import sys
import time

import pandas as pd

from olpark.common import PROCESSED, RAW, data_go_kr, save_bytes

NX, NY = 62, 126  # 송파구 방이동(올림픽공원) 격자
KST = dt.timezone(dt.timedelta(hours=9))


def holidays(y0: int, y1: int) -> pd.DataFrame:
    rows = []
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            b = data_go_kr("B090041/openapi/service/SpcdeInfoService/getRestDeInfo",
                           {"solYear": y, "solMonth": f"{m:02d}", "_type": "json", "numOfRows": 50})
            items = json.loads(b)["response"]["body"].get("items") or {}
            items = items.get("item", []) if isinstance(items, dict) else []
            items = items if isinstance(items, list) else [items]
            rows += [{"date": str(i["locdate"]), "name": i["dateName"], "holiday": i["isHoliday"]} for i in items]
            time.sleep(0.2)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df.to_csv(PROCESSED / "holidays.csv", index=False)
    return df


def forecast() -> pd.DataFrame:
    now = dt.datetime.now(KST) - dt.timedelta(minutes=15)
    base_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    h = max([b for b in base_hours if b <= now.hour], default=None)
    day = now if h is not None else now - dt.timedelta(days=1)
    h = 23 if h is None else h
    base_date, base_time = day.strftime("%Y%m%d"), f"{h:02d}00"
    b = data_go_kr("1360000/VilageFcstInfoService_2.0/getVilageFcst",
                   {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON", "base_date": base_date,
                    "base_time": base_time, "nx": NX, "ny": NY})
    save_bytes(RAW / "weather" / f"fcst_{base_date}{base_time}.json", b)
    items = json.loads(b)["response"]["body"]["items"]["item"]
    df = pd.DataFrame(items).pivot_table(index=["fcstDate", "fcstTime"], columns="category",
                                         values="fcstValue", aggfunc="first").reset_index()
    df.insert(0, "base", base_date + base_time)
    df.to_csv(PROCESSED / "weather_forecast.csv", index=False)
    return df


def daily_asos(start: str, end: str, stn: int = 108) -> pd.DataFrame:
    """기상청 ASOS 일자료 (서울 108). 연 단위로 나눠 호출."""
    rows = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        s = max(start, f"{y}0101")
        e = min(end, f"{y}1231")
        b = data_go_kr("1360000/AsosDalyInfoService/getWthrDataList",
                       {"pageNo": 1, "numOfRows": 400, "dataType": "JSON", "dataCd": "ASOS",
                        "dateCd": "DAY", "startDt": s, "endDt": e, "stnIds": stn})
        save_bytes(RAW / "weather" / f"asos_daily_{stn}_{y}.json", b)
        rows += json.loads(b)["response"]["body"]["items"]["item"]
        time.sleep(0.3)
    df = pd.DataFrame(rows)[["tm", "avgTa", "minTa", "maxTa", "sumRn", "avgRhm", "avgWs", "ddMes"]]
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.rename(columns={"tm": "date"})
    df["sumRn"] = df.sumRn.fillna(0)
    df.to_csv(PROCESSED / "weather_daily.csv", index=False)
    return df


if __name__ == "__main__":
    a = sys.argv[1:] or ["holidays", "2024", "2026", "forecast", "asos"]
    if "asos" in a:
        yesterday = (dt.datetime.now(KST) - dt.timedelta(days=1)).strftime("%Y%m%d")
        d = daily_asos("20240101", yesterday)
        print("asos daily:", len(d), d.date.min(), "~", d.date.max())
    if "holidays" in a:
        i = a.index("holidays")
        d = holidays(int(a[i + 1]), int(a[i + 2]))
        print("holidays:", len(d))
    if "forecast" in a:
        d = forecast()
        print("forecast rows:", len(d), "cols:", [c for c in d.columns][:12])
