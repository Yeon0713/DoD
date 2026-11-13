# 가게 지역 날씨 (기상청 API허브)

사장님이 가게를 등록하면, 네이버 지도에서 읽어 둔 **가게 좌표(store 표의 lat, lng)** 로 그 지역 날씨를 받아
그 가게 DB 파일(`db/data/s101.db` …)에 저장합니다. 사장님이 위도·경도를 직접 적지 않습니다. 그 뒤로는 3시간마다 새로 받습니다.

날짜마다 저장하는 값은 **하늘상태**(맑음 / 구름많음 / 흐림), **강수형태**(없음 / 비 / 비/눈 / 눈 / 소나기), **최고·최저기온**, 강수량, 강수확률입니다.

| 기간 | 쓰는 API | 비고 |
|---|---|---|
| 지난 30일 | 지점정보 → ASOS 일자료 | 가게에서 가장 가까운 관측소의 실제 관측 |
| 오늘 ~ 약 4·5일 뒤 | 단기예보 | 가게가 있는 5km 격자 예보 |

```
가게 등록 (POST /api/stores/register) ─ 응답을 보낸 뒤 백그라운드로, 그 뒤 3시간마다 (auto_refresh.py)
  store 표 lat, lng
    ├ 지점정보 → 가까운 ASOS 관측소 (stations.py) → 일자료 (observations.py)   지난 30일
    └ 격자 nx, ny (coordinates.to_grid) → 단기예보 (short_forecast.py)          오늘부터
  → 가게 파일 store_weather_daily (날짜마다 한 줄), store_weather_fetch (받은 전체)
분석 (read_store_db.read_weather(store_id)) → 그 가게 날씨. 받은 적 없으면 공통 목업 날씨
```

- 지난 날씨는 분석의 "지난번 비 온 날 매출 −20% → 다음 비 예보 날도 비슷"을 계산하는 데 씁니다.
- 목업 가게(s001~s004)는 생성기가 만든 파일을 고치지 않고 지금처럼 공통 목업 날씨(`common.db` weather_daily)를 씁니다.
- 인증키가 없거나 날씨 받기가 실패해도 매장 등록은 그대로 되고, 그 가게는 공통 목업 날씨를 씁니다.

## 1. 준비 (활용신청 3개)

1. [기상청 API허브](https://apihub.kma.go.kr) 회원가입 → 마이페이지에서 인증키 확인 (공공데이터포털 data.go.kr 키와 다릅니다)
2. 아래 3개를 **각각 활용신청**. 승인 전에는 "활용신청이 필요한 API 입니다" 가 옵니다.

   | API허브 메뉴 | 주소 | 하는 일 |
   |---|---|---|
   | 지상관측 › 지점정보 조회 › 지상(SFC) | `/api/typ01/url/stn_inf.php` | 가까운 관측소 찾기 |
   | 지상관측 › 종관기상관측(ASOS) › 일자료 | `/api/typ01/url/kma_sfcdd.php` | 지난 30일 날씨 |
   | 예특보 › 4.3 단기예보조회 (2.1 단기예보 아님) | `/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst` | 오늘부터 날씨 |

3. `server/.env` 에 키 넣기 (`.env` 는 GitHub 에 올라가지 않습니다)
   ```dotenv
   KMA_API_KEY=발급받은_API허브_인증키
   ```

## 2. 실행

```bash
cd server
python run_dev.py                      # 서버. 가게를 등록하면 날씨를 받고, 켜져 있는 동안 3시간마다 새로 받는다

python -m app.weather s004             # 가게 좌표로 받아 weather.json 저장 + 날짜별 요약 출력 (DB 는 그대로)
python -m app.weather s101 --save      # 등록한 가게 DB(store_weather_daily)에도 저장
python -m pytest tests/weather -q      # 인증키 없이 가짜 응답으로 시험
```

| API | 하는 일 |
|---|---|
| `GET /api/stores/{store_id}/weather` | 저장해 둔 날씨 (날짜별 + 위치·관측소 정보) |
| `POST /api/stores/{store_id}/weather/refresh` | 지금 바로 다시 받기 (등록한 가게만) |

코드에서 바로 부르기:

```python
from app.weather.service import get_weather
result = get_weather(latitude=37.8813, longitude=127.7298, past_days=30)
result.model_dump(mode="json")
```

## 3. 각 API 요청과 응답

모든 요청 끝에 `&authKey=인증키` 가 붙습니다 (아래에서는 생략). 시각은 모두 서울 시각(KST)입니다.

### 3-1. 지점정보 → 가까운 ASOS 관측소

```
GET https://apihub.kma.go.kr/api/typ01/url/stn_inf.php?inf=SFC&stn=&tm=202611131400&help=1
```
글자(텍스트) 응답. 실제 응답은 칸 이름이 두 줄로 나뉘어 옵니다 (`# STN  LON  LAT … STN STN_KO …` 아래 `#  ID degee degree …  AD …` → `STN_ID`, `STN_AD`).
마지막 칸(법정동 주소)에 빈칸이 있어 남는 값은 마지막 칸에 이어 붙입니다. 위도·경도가 한국 범위를 벗어나게 읽힌 줄은 버립니다. 하루 동안 메모리에 보관합니다.
2026-11 기준 ASOS 관측소 97곳 (서울시청 → 108 서울 1.2km, 춘천 → 101 춘천 2.4km, 부산시청 → 159 부산 9.2km, 제주 → 184 제주 1.6km).

### 3-2. 지난 30일: ASOS 일자료

```
GET https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd.php?tm=20261112&stn=101&disp=1&help=1
```
```
#  1. TM   : 관측일 (KST)
#  2. STN  : 국내 지점번호
#  …        (help=1 이면 칸마다 번호 붙은 설명이 온다 → 이 번호로 칸 순서를 정한다)
20261112,101,1.8,…,5.2,11.0,…
```
쓰는 칸: `TA_AVG/TA_MAX/TA_MIN`(℃), `RN_DAY` 일강수량(mm), `SD_NEW` 신적설(cm), `CA_TOT` 일 평균 전운량(0~10).
- 하늘상태 = 전운량을 단기예보 기준으로: 0~5 맑음, 6~8 구름많음, 9~10 흐림.
- 강수형태 = 신적설이 있으면 눈, 일강수량이 0 보다 크면 비, 0 이거나 `-9` 면 없음.
- 결측: 기온 칸은 `-99` 이하, 나머지는 `-9` 이하 → `null`.
- **실제 응답 확인 (2026-11 춘천 30일)**: 비 온 날은 일강수량이 숫자(0.2, 29.7 …), 아주 약한 비는 `0.0`, 비가 오지 않은 맑은 날은 모두 `-9` 였습니다.
  그래서 일강수량 숫자는 `null` 로 두되(0 으로 만들지 않음), 그날 기온 관측이 있으면 강수형태는 "없음"으로 봅니다.
  기온까지 빠진 날(관측 자체가 없는 날)은 강수형태도 `null` 입니다.
- 실제 응답에는 칸마다 번호 붙은 설명(`#  1. TM : 관측일`)이 오고, 그 번호로 칸 순서를 읽습니다 (`tests/weather/samples/` 에 실제 응답 원문).
- 날짜마다 1번 부릅니다. 처음 받을 때 30번, 3시간마다 새로 받을 때는 이미 저장한 날을 건너뛰어 1번(어제)입니다.
- 가장 가까운 관측소부터 어제 기온이 있는 첫 관측소(최대 3곳)를 씁니다.

### 3-3. 오늘부터: 단기예보

```
GET https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst?base_date=20261113&base_time=1100&nx=73&ny=134&dataType=JSON&pageNo=1&numOfRows=1000
```
```json
{"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
  "body": {"items": {"item": [{"baseDate": "20261113", "baseTime": "1100", "category": "SKY",
                               "fcstDate": "20261114", "fcstTime": "1500", "fcstValue": "4", "nx": 73, "ny": 134}, …]},
           "totalCount": 900}}}
```
- 발표 02·05·08·11·14·17·20·23시, 발표 10분 뒤부터 조회. 자료가 없으면(`resultCode 03`) 직전 발표(최대 3번).
- `totalCount` 를 보고 모든 쪽(page)을 모읍니다.
- 쓰는 항목: `SKY`(1 맑음, 3 구름많음, 4 흐림), `PTY`(0 없음, 1 비, 2 비/눈, 3 눈, 4 소나기), `TMP`, `TMN`, `TMX`, `POP`, `PCP`, `SNO`.
- 하루 하늘상태 = 그날 시간별 하늘상태 중 가장 많은 것(같으면 더 흐린 쪽). 하루 강수형태 = 비와 눈이 섞이면 비/눈, 눈만 눈, 비가 있으면 비, 소나기만 소나기.
- `PCP` 는 `"강수없음"`, `"1mm 미만"`, `"30.0~50.0mm"`, `"50.0mm 이상"` 같은 글자라, 하루 강수량은 범주 아래 끝을 더한 값(적어도 이만큼)입니다.
- 오늘 `TMN`(최저)은 이른 발표에만 있어서 늦게 받으면 `null` 입니다 (시간별 기온으로 만들지 않음).

### 오류

| 상황 | 처리 |
|---|---|
| 키 오류 / 활용신청 미승인 (401·403, `{"result": {"status": 401}}`, 코드 20·21·30~33) | `KmaAuthError`, 재시도 안 함 |
| 호출 한도 초과 (429, 코드 22) | `KmaRateLimitError`, 재시도 안 함 |
| 시간 초과·연결 실패·서버 5xx | 최대 3번 (0.5초, 1초 쉬고) |
| 자료 없음 (코드 03) | 직전 발표 시각으로 |
| JSON 대신 XML·HTML·글 | 코드를 읽어 위 종류로, 모르면 `KmaResponseError` |
| 칸 이름 줄 없음 / 칸 수 다름 | `KmaResponseError` (짐작해서 읽지 않음) |

한 API 가 실패해도 나머지는 돌려주고 `metadata.errors` 에 적습니다. 오류 문구에는 요청 주소(인증키 포함)를 넣지 않습니다.

## 4. 결과 모양 (`weather.json`, schemas.py)

```jsonc
{
  "location": {"latitude": 37.8813, "longitude": 127.7298, "nx": 73, "ny": 134,
               "station": {"station_id": 101, "name": "춘천", "latitude": 37.90262, "longitude": 127.7357, "distance_km": 1.6}},
  "timezone": "Asia/Seoul",
  "observations": [{"date": "2026-11-07", "type": "observed", "source": "asos_daily", "station_id": 101,
                    "temperature_avg": 5.2, "temperature_min": -1.3, "temperature_max": 11.0,
                    "precipitation_mm": 12.5, "new_snow_cm": null, "cloud_cover": 9.4, "sky": "흐림", "precipitation_type": "비"}],
  "forecasts": {
    "hourly": [{"datetime": "2026-11-14T15:00:00+09:00", "type": "forecast", "source": "short_term",
                "issued_at": "2026-11-13T11:00:00+09:00", "temperature": 8, "sky": "흐림", "precipitation_type": "비",
                "precipitation_probability": 70, "precipitation_text": "2.0mm", "precipitation_mm_min": 2.0, "snow_text": "적설없음"}],
    "daily": [{"date": "2026-11-14", "type": "forecast", "source": "short_term", "issued_at": "2026-11-13T11:00:00+09:00",
               "temperature_min": 1, "temperature_max": 12, "sky": "흐림", "precipitation_type": "비",
               "precipitation_mm_min": 48.0, "precipitation_probability_max": 70, "hours": 24}]
  },
  "metadata": {"requested_at": "…", "short_forecast_issued_at": "…", "forecast_end_at": "2026-11-16T23:00:00+09:00",
               "notes": ["지난 관측은 가게가 아니라 1.6km 떨어진 ASOS 관측소 101(춘천) 값이에요. …"], "errors": []}
}
```

가게 DB `store_weather_daily` 는 이 결과를 날짜마다 한 줄로 줄인 것입니다
(`kind` observed/forecast, `source`, `temp_avg/max/min`, `sky`, `precip_type`, `precip_mm`, `pop_max`, `issued_at`, `fetched_at`).
다시 받으면 관측이 같은 날 예보를 대신하고, 지난날 예보는 지우고, 이번에 받지 못한 관측일은 예전 값을 지우지 않습니다.

## 5. 알아 둘 것

- **3시간마다 새로 받기** (`auto_refresh.py`): 서버가 켜져 있는 동안 10분마다 등록한 가게를 훑어, 마지막으로 받은 지 3시간이 지난 가게만 다시 받습니다.
  서버가 꺼져 있는 동안에는 받지 않고, 켜면 밀린 가게부터 받습니다. 서버(worker)를 여러 개 켜면 서버마다 따로 받습니다.
- **예보는 약 4·5일 뒤까지**: 가게 달력은 35일 앞까지 보여 주지만 그 뒤로는 날씨 이유가 붙지 않습니다.
- **지난 30일만**: 시연용 목업 주문은 70일 전부터 있어서, 그 앞 기간은 날씨 없이 분석됩니다.
- **실제 응답 확인 (2026-11-13)**: 세 API 모두 실제 응답으로 확인했고 원문을 `tests/weather/samples/` 에 두었습니다.
  춘천 가게 기준 처음 받기 약 7초(관측 30일 + 예보 5일), 3시간 뒤 새로 받기 약 2초.
- **단기예보 3일 뒤부터**: 3시간 간격이고 강수량이 단위 없는 숫자("0", "1")로 옵니다. "0" 은 없음, 그 밖은 뜻이 문서에 없어 강수량을 비워 둡니다 (강수형태 비/눈은 그대로 구분됨).
  마지막 날 00시 한 시각만 있는 날은 하루 요약을 만들지 않습니다.
- **활용신청 이름 주의**: API허브에는 "단기예보"가 두 개 있습니다. 필요한 것은 예특보 › **4.3 단기예보조회**(`getVilageFcst`)이고, 2.1 단기예보(`nph-dfs_shrt_grd`, 전국 격자 파일)는 쓰지 않습니다.
