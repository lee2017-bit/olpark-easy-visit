"""교통약자 관련 데이터 수집.

1) 서울교통공사_교통약자이용정보 (엘리베이터·휠체어리프트) — 올림픽공원역·몽촌토성역·한성백제역
2) 한국관광공사_무장애 여행 정보 (KorWithService2) — 올림픽공원(contentId 126532)
3) 기관 공지·홈페이지에 적힌 정보(장애인 주차면, 휠체어 대여, 휠체어 진입로, 지하철 출구 안내)는
   API가 없어 출처 URL과 함께 수기 기록 (STATIC_FACTS)

키: DATA_GO_KR_KEY
산출: data/raw/accessibility/*.json, data/processed/accessibility.json
사용: python -m collectors.accessibility
"""
import json

from olpark.common import PROCESSED, RAW, data_go_kr, save_bytes, save_json

STATIONS = ["올림픽공원", "몽촌토성", "한성백제"]

STATIC_FACTS = {
    "disabled_parking_by_spot": {
        "source": "https://www.ksponco.or.kr/board.es?mid=a10301000000&bid=0046&list_no=82568&act=view",
        "as_of": "2025-12-09",
        "spots": {"남2문 대형주차장 P1A": 6, "남2문 대형주차장 P1B": 6, "올림픽홀": 5, "테니스장": 10,
                  "수영장": 7, "체조경기장(KSPO DOME)": 10, "티켓링크 라이브아레나": 3, "역도경기장": 6,
                  "남3문": 6, "남4문": 12, "서1문": 3, "서2문": 11},
    },
    "wheelchair_rental": {
        "source": "https://www.ksponco.or.kr/olympicpark/menu.es?mid=a20106010000",
        "places": {"평화의광장 안내센터": 3, "만남의광장 안내센터": 3},
        "hours": "09:00~19:00 (휴게 12:00~13:00)",
        "rule": "무상, 신분증 맡기고 3시간",
    },
    "wheelchair_entry_route": {
        "source": "https://www.ksponco.or.kr/olympicpark/parkingInfo?mid=a20111000000",
        "text": "만남의광장: 동2문 입차 → 그래피티의 벽 주차장 → 올림픽공원역 쪽 경사로",
    },
    "subway_exit_guidance": {
        "source": "https://www.ksponco.or.kr/olympicpark/menu.es?mid=a20109000000",
        "text": "5·9호선 올림픽공원역 3·4번 출구, 8호선 몽촌토성역 1번 출구, 9호선 한성백제역 2번 출구",
    },
    "venue_nearest_parking": {
        "source": "https://www.ksponco.or.kr/olympicpark/parkingInfo?mid=a20111000000",
        "KSPO DOME": {"lot": "P5", "spaces": 176, "walk_min": "1"},
        "핸드볼경기장": {"lot": "P6", "spaces": 167, "walk_min": "1~2"},
        "올림픽홀": {"lot": "P2·올림픽홀 지하", "spaces": 320, "walk_min": "1~2"},
        "우리금융아트홀": {"lot": "P7", "spaces": 137, "walk_min": "1~2"},
        "K-아트홀": {"lot": "P1", "spaces": 562, "walk_min": "3~4"},
        "올림픽수영장": {"lot": "P4", "spaces": 117, "walk_min": "1"},
        "올림픽테니스경기장": {"lot": "P11", "spaces": 190, "walk_min": "1~2"},
        "gate_area_capacity": {"동2문·남2문·북2문": 2200,
                               "source": "https://www.ksponco.or.kr/online/main/parking.do"},
    },
}


def elevators() -> list:
    b = data_go_kr("B553766/wksn/getWksnElvtr", {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON"})
    save_bytes(RAW / "accessibility" / "seoulmetro_elevators.json", b)
    items = json.loads(b)["response"]["body"]["items"]["item"]
    return [x for x in items if any(s in x.get("stnNm", "") for s in STATIONS)]


def wheelchair_lifts() -> list:
    b = data_go_kr("B553766/wksn/getWksnWhcllift", {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON"})
    save_bytes(RAW / "accessibility" / "seoulmetro_wheelchair_lifts.json", b)
    items = json.loads(b)["response"]["body"].get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else []
    return [x for x in items if any(s in x.get("stnNm", "") for s in STATIONS)]


def barrier_free() -> dict:
    b = data_go_kr("B551011/KorWithService2/detailWithTour2",
                   {"MobileOS": "ETC", "MobileApp": "olpark", "contentId": 126532, "_type": "json"})
    save_bytes(RAW / "accessibility" / "korwith_126532.json", b)
    it = json.loads(b)["response"]["body"]["items"]["item"]
    it = it[0] if isinstance(it, list) else it
    return {k: v for k, v in it.items() if v}


if __name__ == "__main__":
    res = {"elevators": elevators(), "wheelchair_lifts": wheelchair_lifts(),
           "barrier_free_knto": barrier_free(), "agency_static": STATIC_FACTS}
    save_json(PROCESSED / "accessibility.json", res)
    for x in res["elevators"]:
        print(x["lineNm"], x["stnNm"], "|", x["fcltNm"], "|", x.get("dtlPstn"), "| 출입구", x.get("vcntEntrcNo"))
    print("wheelchair lifts:", len(res["wheelchair_lifts"]))
    print("KNTO:", {k: res["barrier_free_knto"][k] for k in ("parking", "wheelchair", "restroom") if k in res["barrier_free_knto"]})
