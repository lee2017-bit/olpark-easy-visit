# 문턱 없는 올팍 (olpark-easy-visit)

휠체어·유모차로 가는 올림픽공원 공연일 안내.

올림픽공원 공연일의 주차 혼잡 위험과 교통약자 이동 정보(지하철 엘리베이터 출구, 장애인 주차, 휠체어 대여)를 한곳에 모은 **비공식** 안내 사이트입니다.
한국체육산업개발(주) 공공데이터 활용 경진대회 출품을 위한 개인 프로젝트이며, 기관의 공식 서비스가 아닙니다.

## 구성

- `site/` 정적 사이트 (GitHub Pages). `site/data/site.json`을 읽어 날짜 선택 → 아이콘 안내 → 지도(Leaflet + OpenStreetMap)로 보여줌
- `data/static/map_points.json` 지도 좌표: 공연장·지하철 출구의 OpenStreetMap 요소 좌표(© OpenStreetMap contributors, ODbL). 추정 좌표 없음, 주차장은 기관 번호와 OSM 이름이 맞지 않아 지도에 찍지 않음
- `build/build_site.py` site.json 생성
- `analysis/risk.py` 만차 위험 등급: 2025년 같은 조건 날들의 실제 만차 비율
- `.github/workflows/site.yml` 매주 월·목 06:17(KST) 데이터 갱신 → 커밋 → 배포. 수집이 실패해도 기존 데이터로 배포
- 저장소 Secrets: `DATA_GO_KR_KEY` (자동 갱신용, 이것 하나만 필요)

로컬 미리보기: `python3 -m build.build_site && cd site && python3 -m http.server`

## 필요한 환경 변수 (값은 코드·로그·저장소에 남기지 않음)

| 변수 | 용도 |
|---|---|
| `DATA_GO_KR_KEY` | 공공데이터포털 (기상청 단기예보, 특일 정보, 서울교통공사 교통약자이용정보, 한국관광공사 무장애 여행 정보) |
| `CULTURE_GO_KR_KEY_LINKED` | 문화공공데이터광장 API_CPM_009 (2025 입출차·공연·날씨 연계) |
| `CULTURE_GO_KR_KEY_INOUT` | 문화공공데이터광장 API_CPM_008 (2025 입출차 전체구역) |
| `CULTURE_GO_KR_KEY_EVENT` | 문화공공데이터광장 KSCperf (올림픽공원 공연정보) |

## 수집 (프로젝트 루트에서)

```
python3 -m collectors.events_homepage 202401 202612   # 홈페이지 공연 일정
python3 -m collectors.events_api                      # 기관 공연정보 API (2014~2024 이력)
python3 -m collectors.datago_files                    # 입출차 2024-07, 혼잡도 기록, 월별 주차
python3 -m collectors.kcisa_parking all               # 2025 연계·입출차 (11/11 기준 504 오류)
python3 -m collectors.agency_prediction               # 기관 예상 이용률 스냅샷 (주말 전 실행)
python3 -m collectors.accessibility                   # 지하철 엘리베이터, 무장애 정보
python3 -m collectors.calendar_weather                # 공휴일, 단기예보
python3 -m collectors.osm_points                      # 지도 좌표 (OSM, 필요할 때만)
```

## 분석

```
python3 -m analysis.occupancy       # 15분 단위 주차대수, 일자 요약
python3 -m analysis.congestion_log  # 2025 혼잡도 기록 × 공연
python3 -m analysis.evaluate        # 기관식 일괄 예측 vs 공연 반영 예측
python3 -m analysis.report          # reports/analysis_<날짜>.md
```

## 데이터 출처·이용조건

- 한국체육산업개발 공공데이터(공공데이터포털·문화공공데이터광장): 이용허락범위 제한 없음 / 공연정보는 공공누리 1유형(출처표시)
- 서울교통공사, 한국관광공사, 기상청, 한국천문연구원: 공공데이터포털 이용조건
- 올림픽공원 홈페이지 공연 일정·안내 페이지: 출처 표기
