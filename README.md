# 문턱 없는 올팍 (olpark-easy-visit)

휠체어·유모차로 가는 올림픽공원 공연, 예매부터 집에 갈 때까지.

올림픽공원 공연일에 교통약자(휠체어·유모차·보행 불편·시각·청각)가 겪는 불편을 단계별(예매 → 가는 길 → 주차 → 공원 안 → 공연장 → 집에 갈 때)로 모은 **비공식** 안내 사이트입니다.
항목마다 근거(공식·공공데이터·분석·기사·후기)를 표시합니다.
한국체육산업개발(주) 공공데이터 활용 경진대회 출품을 위한 개인 프로젝트이며, 기관의 공식 서비스가 아닙니다.

주차장이 언제 찰지는 예측하지 않습니다. 2025년 공연 있는 주말·공휴일 60일로 검증한 결과 공연·달력 정보로는 고정값보다 크게 나은 예측이 나오지 않았고
(`reports/predictability_20261121.md`), 실제 공연일 비교에서도 기관 「주차장 예상 이용률」이 더 정확했습니다(`reports/live_check_20261121.md`).
그래서 예측은 기관 안내로 연결하고, 해마다 비슷하게 반복되는 기록(공연 뒤 출차 몰림, 장애인콜택시 대기)과 접근성 정보에 집중합니다.

## 구성

- `site/` 정적 사이트 (GitHub Pages). `site/data/site.json`을 읽어 동행자 유형·날짜·공연장 선택 → 단계별 안내 → 지도(Leaflet + OpenStreetMap)
- `data/static/access_guide.json` 늘 같은 안내: 공연장별 휠체어석·출입·자막·BF 인증, 예매처 전화, 단계별 주의·팁, 공개 자료가 없는 것(gaps). 항목마다 출처
- `data/static/line9_elevators.csv` 9호선 올림픽공원·한성백제역 엘리베이터 출구 (공공데이터포털 15118716)
- `data/static/map_points.json` 지도 좌표: 공연장·지하철 출구의 OpenStreetMap 요소 좌표(© OpenStreetMap contributors, ODbL). 추정 좌표 없음
- `build/build_site.py` site.json 생성: 공연 일정 + 늘 같은 안내 + 날짜별 항목(예매처, 가까운 엘리베이터 출구, 끝나는 시각, 출차 몰림 시간대, 콜택시 대기, 비 예보 등)
  + 공연 포스터 썸네일(`build/posters.py`: 올림픽공원 홈페이지 공연 목록 이미지를 폭 240px로 줄여 `site/data/posters/`에 둠. 누르면 기관 공연 페이지)
  + 날짜별 「꼭 알아야 할 것」 후보(`key`, rank 순). 사이트가 여기에 지금 확인한 것(엘리베이터 중지·공연장 근처 공사·만차)을 더해 맨 위에 3개만 보여 줌
- `.github/workflows/site.yml` 매주 월·목 06:17(KST) 데이터 갱신 → 커밋 → 배포. 수집이 실패해도 기존 데이터로 배포
- `.github/workflows/status.yml` 5호선 올림픽공원·8호선 몽촌토성 엘리베이터 가동현황(`collectors/live_status.py`)을 10분마다 `status` 브랜치의 `status.json` 하나로 올림. GitHub 예약 실행이 몇 시간씩 밀리는 일이 있어, 한 번 시작하면 최대 약 5시간 40분 동안 안에서 10분마다 갱신(매시 예약 + 이 파일을 main에 올릴 때 시작, 01~05시 휴식). 사이트가 raw.githubusercontent.com 에서 읽음(키는 Actions 안에서만)
- 실시간 주차대수·기관 예상 이용률, 올팍소식 공사·통제 공지는 방문자 브라우저가 기관 홈페이지에서 바로 읽음(Access-Control-Allow-Origin: *)
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
python3 -m collectors.kcisa_parking all               # 2025 연계·입출차
python3 -m collectors.agency_prediction               # 기관 예상 이용률 스냅샷 (주말 전 실행)
python3 -m collectors.agency_live --every 10          # 기관 실시간 주차대수 기록 (검증용)
python3 -m collectors.accessibility                   # 지하철 엘리베이터, 무장애 정보
python3 -m collectors.calendar_weather                # 공휴일, 단기예보
python3 -m collectors.osm_points                      # 지도 좌표 (OSM, 필요할 때만)
```

## 분석

```
python3 -m analysis.inout_2025          # 2025 입출차 → 15분 단위 주차대수
python3 -m analysis.exit_wave           # 공연 뒤 출차 몰림 시각·규모 (KSPO DOME)
python3 -m analysis.calltaxi_wait       # 공연 있는 밤 장애인콜택시 대기 (서울시설공단 탑승내역 2025)
python3 -m analysis.predictability      # 만차 예측이 가능한지 검증 (일 단위 교차검증)
```

결과는 `reports/`에 날짜를 붙여 저장합니다. `analysis/risk.py`·`evaluate.py` 등은 예측 서비스였던 이전 버전의 분석으로, 기록을 위해 남겨 두었습니다.

## 데이터 출처·이용조건

- 한국체육산업개발 공공데이터(공공데이터포털·문화공공데이터광장): 이용허락범위 제한 없음 / 공연정보는 공공누리 1유형(출처표시)
- 서울교통공사, 서울시메트로9호선, 서울시설공단(장애인콜택시), 한국관광공사, 기상청, 한국천문연구원: 공공데이터포털 이용조건
- 올림픽공원 홈페이지 공연 일정·안내 페이지: 출처 표기
- 휠체어석·자막 등 일부 항목은 기사·관람 후기를 근거로 하며 사이트에 그렇게 표시
