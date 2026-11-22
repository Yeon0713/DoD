# server/app · server/db 버그 수정 계획 (A3, A6, A10)

2026-11-22 · 기준 코드: 브랜치 `jiho/feat-hr-demo-docs`, 커밋 `d497f97`에 이번 수정 22건을 더한 작업 트리(아직 커밋 전) · 줄 번호는 이 작업 트리 기준입니다. 코드가 바뀌었으면 함수 이름으로 찾아 주세요.

- 범위: `server/app`, `server/db`만 봤습니다 (`server/voice`, `server/Harness`는 뺌).
- A1, A2, A4, A5, A7, A8, A9는 2026-11-22에 고쳐서 이 문서에서 뺐습니다. A3·A6은 그때 정책을 정하지 않아 미뤘습니다.
- A10은 그 수정을 다시 리뷰하다 찾은 것입니다(A8 수정에 남은 틈).
- 지금 시험: `server/.venv/bin/python -m pytest server/tests -q --ignore=server/tests/voice` → 702개 모두 통과합니다.
- 시스템 python(`python`)에는 pytest가 없습니다. 꼭 `server/.venv/bin/python`을 쓰세요.
- "재현함"은 직접 실행해서 증상을 본 것, "코드로 확인"은 코드를 따라가 확인한 것, "가능성 있음"은 입력 조건이 실제로 오는지 아직 모르는 것입니다.

| # | 버그 | 심각도 | 확신 | 주요 파일 |
|---|---|---|---|---|
| A3 | 마감 "24:00" 가게는 할 일·설정이 400으로 막힘 | 중간 | 가능성 있음 (입력이 "24:00"이면 재현함) | `app/data_pipeline/registered_stores.py`, `app/core/naver_place.py` |
| A6 | 사장님 확인에서 owner_key를 앱이 마음대로 보냄 + 진짜 네이버 키가 있어도 임시 로그인이 열려 있음 | 중간 (배포 전) / 낮음 (지금 데모) | 코드로 확인 | `app/modules/owner_check/`, `app/modules/auth/router.py` |
| A10 | 예약 상태 바꾸기가 확인과 저장 사이에 끊겨 있음 | 낮음 | 코드로 확인 | `app/data_pipeline/reservations.py:106-118` |

---

## A3. 마감 "24:00" 가게는 할 일·설정이 400으로 막힘

- 심각도: 중간, 확신: 가능성 있음 (네이버가 "24:00"을 주는지는 확인 못 함. 입력이 "24:00"이면 재현함)

**무엇이 잘못되나**
- 네이버 지도 영업시간 끝이 `"24:00"`(자정 마감)이면 이런 일이 생깁니다.
  - 등록 화면은 자정을 넘기는 가게가 아니라고 보고 목업 주문을 넣습니다.
  - 그런데 `/api/today`, `/api/plan`, `/api/settings`는 모두 `400 OVERNIGHT_STORE_NOT_SUPPORTED`("자정을 넘겨 영업하는 가게는 아직 알림 계획을 만들 수 없어요")입니다.
- 재현 (직접 실행): 일곱 요일 모두 `{"open": "11:00", "close": "24:00"}`인 `PlaceInfo`를 씁니다.
  - `store_row()` 결과: `open_time 11:00`, `close_time 00:00`, slots `['10:30', '15:00', '23:30']`
  - 등록 화면 판정(`close <= open`, 글자 비교): False. 자정을 넘기지 않는 가게로 봅니다.
  - `build_store_settings(...)`: `ApiError OVERNIGHT_STORE_NOT_SUPPORTED`
- 저장해 둔 등록 기록(`db/app_data/registry.db`)에는 지금 "24:00" 가게가 없습니다. 테스트 html에도 없습니다. 그래서 "가능성 있음"입니다.
- 다만 `_hhmm()`이 굳이 `hour % 24`를 하는 것을 보면, 만든 사람이 "24:00"을 본 적이 있는 것으로 보입니다.

**왜 생기나**
1. 네이버에서 읽은 값을 그대로 저장합니다(`naver_place.py:182`). "24:00"이 그대로 들어옵니다.
2. 등록 화면(`stores/router.py:149`)과 기본 설정(`store_snapshot_cache.py:124`)은 **글자**로 `close <= open`을 비교합니다. `"24:00" <= "11:00"`은 거짓이라 자정을 넘기지 않는 가게로 봅니다.
3. 가게 파일 store 표를 만들 때(`registered_stores.py:130`)는 `_hhmm("24:00")`이 `time(0, 0)`으로 바꿉니다.
4. 계획을 만들 때(`analysis_to_plan_inputs.py:74`)는 **시각**으로 `close_time(00:00) < open_time(11:00)`을 비교합니다. 이번에는 자정을 넘기는 가게로 보고 막습니다.
5. 같은 가게를 두 곳이 서로 다르게 판정합니다.
6. 한 겹 더 있습니다. `_registered_base`가 넘기는 `weekly_hours`의 `"24:00"`은 `StoreSettings`의 `HHMM` 규칙(`^([01]\d|2[0-3]):[0-5]\d$`)에도 맞지 않습니다. 4번에서 먼저 막히지 않았다면 pydantic 검증 오류(500)가 났을 것입니다.

**문제 코드**

`server/app/core/naver_place.py:179-182`
```python
179     for codes, day in sorted(rows, key=lambda r: -len(r[0])):
180         hours = day["businessHours"]
181         for code in codes:
182             weekly[code] = {"open": hours["start"], "close": hours["end"]}   ← "24:00" 이 그대로 들어감
```

`server/app/data_pipeline/registered_stores.py:99-101, 129-130`
```python
 99 def _hhmm(value: str) -> dt.time:
100     hour, minute = map(int, value.split(":"))
101     return dt.time(hour % 24, minute)                                       ← "24:00" → 00:00
...
129         "open_time": _hhmm(open_time),
130         "close_time": _hhmm(close_time),                                    ← store 표 close_time = 00:00
```

`server/app/modules/stores/router.py:149-151`, `server/app/data_pipeline/store_snapshot_cache.py:124`
```python
149     overnight = any(h and h["close"] <= h["open"] for h in info.weekly_hours.values())   ← 글자 비교: "24:00" 은 False
150     if settings.demo_store_data and not overnight:
151         demo_data.fill(store_id, info.weekly_hours, info.break_time)
...
124     if any(h and h["close"] <= h["open"] for h in info.weekly_hours.values()):   ← 같은 글자 비교
```

`server/app/data_pipeline/analysis_to_plan_inputs.py:73-80`
```python
73     open_time, close_time = hhmm(store["open_time"]), hhmm(store["close_time"])
74     if store["close_time"] < store["open_time"]:                             ← 시각 비교: 00:00 < 11:00 → 막음
75         raise ApiError(
76             400,
77             "OVERNIGHT_STORE_NOT_SUPPORTED",
```

**고치는 방향**
- 권장안: **네이버에서 읽을 때 자정 마감을 한 값으로 맞춥니다.** 끝 시각이 `"24:00"`이면 `"23:59"`로 바꿉니다.
  - `naver_place.parse_place`의 182줄에서 `close = _midnight_close(hours["end"])`로 바꿉니다. `"24:00"`이면 `"23:59"`, 나머지는 그대로입니다.
  - 이미 저장된 `info_json`도 있을 수 있습니다. `PlaceInfo.from_dict`에서도 같은 함수를 거치게 하면 다시 등록하지 않아도 맞춰집니다.
  - 이렇게 하면 store 표 `close_time 23:59`, slots CLOSING `23:29`가 되어 계획 엔진이 그대로 동작합니다. 모든 비교(글자·시각)가 "자정을 넘기지 않음"으로 같아집니다.
- 끝이 `"00:00"`인 경우도 같은 뜻(자정 마감)일 수 있습니다. 함께 `"23:59"`로 맞출지 정해 주세요.
  - 맞추면 "00:00 마감" 가게도 계획을 받습니다.
  - 안 맞추면 지금처럼 자정을 넘기는 가게로 보고 막습니다.
  - 권장: 여는 시각이 `"00:00"`이 아닐 때만 맞춥니다.
- 다른 방법: `00:00` 마감을 계획 엔진 전체가 "그날 끝"으로 이해하게 바꾸기. `close_time_on`, `_check_slots`, `default_notice_dayparts`, HHMM 규칙까지 바꿔야 해서 큽니다. 권장하지 않습니다.
- 등록 화면과 `_registered_base`의 판정은 `registered_stores`에 함수 하나(`is_overnight(weekly_hours)`)로 모아 같은 기준을 쓰게 합니다.

**같이 볼 곳**
- 앱은 시간대 끝으로 `"24:00"`을 이미 씁니다(`mobile/src/lib/hours.ts:31, 79, 232`, `mobile/src/lib/check.ts:52`). 이것은 앱 안 시간대 값이고, 서버 HHMM으로 보내는 값은 아닙니다. 영향은 없지만 헷갈리지 않게 적어 둡니다.
- A4와 같은 주제(자정 언저리 영업)입니다. voice 쪽(`server/voice`)도 가게 영업시간을 따로 다루면 같은 정규화가 필요한지 그쪽 담당이 봐야 합니다.
- `app/modules/stores/router.py:209`(리뷰 불러오기)가 `store["close_time"].hour`를 `make_reviews`에 넘깁니다. 00:00이면 리뷰 시각이 모두 여는 시각 한 시간으로 몰립니다. 23:59로 맞추면 함께 풀립니다.

**고친 뒤 확인**
- `server/tests/modules/test_store_register.py`에 시험을 더합니다.
  - `test_midnight_close_is_normalized`: "24:00" 줄이 든 네이버 html(이 파일의 `_state_html` 꼴)을 `parse_place`로 읽습니다. assert `weekly_hours["MON"]["close"] == "23:59"`.
  - `test_midnight_close_store_gets_plan`: 위 정보로 `store_row`를 만들고 `build_store_settings(row, {"weekly_hours": ..., "break_time": None})`를 부릅니다. assert 오류 없이 `close_time == "23:59"`, `slots.CLOSING == "23:29"`.
- 명령: `server/.venv/bin/python -m pytest server/tests/modules/test_store_register.py server/tests/data_pipeline -q`

**주의**
- 앱 화면에 "23:59 마감"으로 보입니다. 화면에서 "24:00"으로 보여 주고 싶으면 앱 표시 쪽에서 바꿔야 합니다(서버 값은 23:59).
- 자정을 넘기는 가게(예: 17:00~03:00, 목업 s002)는 지금처럼 계획을 막아야 합니다. 문서에 정해 둔 동작입니다(`test_overnight_store_has_analysis_but_no_plan`, `test_store_snapshot_and_api.py:51`).

---


## A6. 사장님 확인에서 owner_key를 앱이 마음대로 보냄 + 진짜 네이버 키가 있어도 임시 로그인이 열려 있음

- 심각도: 중간 (배포 전에 꼭) / 낮음 (지금 데모), 확신: 코드로 확인

**무엇이 잘못되나**
- (가) 사장님 확인 신청 `POST /api/owner_check`가 본문의 `owner_key`를 그대로 믿습니다.
  - 아무 클라이언트나 `"owner_key": "naver:<남의 네이버 회원번호>"`로 신청할 수 있습니다.
  - 승인되면 그 남의 계정이 신청자가 고른 가게에 이어집니다(`set_owner`).
  - 그 사람이 다음에 네이버로 로그인하면 신청자의 가게로 들어갑니다.
- (나) 진짜 네이버 키(`NAVER_LOGIN_CLIENT_ID/SECRET`)를 넣어도 임시 로그인 화면이 그대로 열려 있습니다(`/api/auth/naver/mock/login`).
  - `/naver/start`로 받은 state만 있으면 이 화면에 들어갈 수 있습니다.
  - 화면의 "테스트 계정 보기"에 아이디·비밀번호(`dona_demo` / `dona1234`)가 보입니다. 누구나 데모 계정으로 로그인합니다.
- 재현 순서
  - (가) 시험 계정으로 s004 사장님 확인 시험용 값(`GET /api/owner_check/sample?store_id=s004`)을 받고, `owner_key`만 `"naver:VICTIM"`으로 바꿔 신청합니다. 5초 뒤 결과를 읽으면 `owners` 표에 `naver:VICTIM → s004`가 생깁니다.
  - (나) 키를 넣고 서버를 켭니다 → `GET /api/auth/naver/start?back=<허용된 앱 주소>`를 부르되 따라가지 않고 state만 읽습니다 → `GET /api/auth/naver/mock/login?state=<그 state>`가 로그인 화면을 그립니다.

**왜 생기나**
- (가) 네이버 로그인 결과는 서버 메모리 `_results[ticket]`에 있습니다(프로필 id 포함). 그런데 사장님 확인은 이 ticket을 받지 않고 앱이 만든 문자열을 받습니다.
  - 앱은 `naverProfile`의 id로 `naver:<id>`를 만듭니다(`mobile/src/components/start/StoreRegister.tsx:35-40`). 서버가 이 값이 정말 로그인한 사람 것인지 확인할 길이 없습니다.
- (나) 문서 의도(`docs/test-accounts.md:3`): "임시 네이버 로그인 화면(진짜 네이버 키가 없을 때)". 그런데 임시 화면 두 함수는 `_real_naver()`를 보지 않고 state만 봅니다.
- 참고: 전체 API에 인증이 없는 것(`?store_id=`로 아무 가게나 봄)은 문서에 적힌 지금 단계 설계입니다(`app/data_pipeline/store_selection.py` 머리글). A6은 그 설계 안에서도 **계정과 가게를 잇는 길**만은 막자는 것입니다.

**문제 코드**

`server/app/modules/owner_check/router.py:20-36`
```python
20 class CheckRequest(BaseModel):
21     store_id: str
22     owner_key: str                     ← 앱이 보낸 글자 그대로
...
29 @router.post("", summary="사장님 확인 심사 신청")
30 def submit(body: CheckRequest):
...
34         return review.submit(body.owner_key, body.store_id, ...)   ← 확인 없이 넘김
```

`server/app/modules/owner_check/review.py:138-144`
```python
138     if row["result"] is None and _now() >= dt.datetime.fromisoformat(row["decide_at"]):
139         result, reason = decide(row)
...
143         if result == "approved":
144             registered_stores.set_owner(row["owner_key"], row["store_id"])   ← 그 owner_key 를 가게에 이음
```

`server/app/modules/auth/router.py:319-338`
```python
319 @router.get("/naver/mock/login", response_class=HTMLResponse, include_in_schema=False)
320 def mock_login_page(state: str = ""):
321     if state not in _pending:                       ← 진짜 네이버 키가 있어도 통과
320         return _page("로그인", "<p>로그인을 앱에서 처음부터 다시 해 주세요.</p>")
323     return _login_page(state)                       ← 298-303줄: 아이디·비밀번호를 화면에 보여 줌
...
326 @router.post("/naver/mock/login", include_in_schema=False)
327 async def mock_login(request: Request):
...
330     if state not in _pending:                       ← 여기도 같음
```

**고치는 방향**
- (가) 권장안: **네이버 계정은 ticket으로 확인합니다.**
  - `CheckRequest`에 `ticket: str | None`을 더합니다.
  - `owner_key`가 `"naver:"`로 시작하면, `auth.router._results[ticket]`이 있고 `"naver:" + profile["id"] == owner_key`일 때만 받습니다. 아니면 `403 OWNER_KEY_MISMATCH`입니다.
  - auth 쪽에 `profile_id_of(ticket) -> str | None` 함수를 두고 owner_check가 그것만 부르게 합니다. `_results`를 직접 만지지 않게 합니다.
  - 앱(`mobile/src/lib/ownerCheck.ts:46-51`, `OwnerCheck.tsx:84`)이 로그인 때 받은 ticket을 함께 보내게 고칩니다.
  - ticket은 30분 뒤 사라집니다(`KEEP`). 가입 중 30분이 넘으면 "다시 로그인해 주세요"로 돌려보냅니다.
  - `"phone:"` 계정(전화번호 가입)은 지금 서버가 확인할 수단이 없습니다. 그대로 두고 문서에 "아직 확인 안 함"으로 적습니다.
- 다른 방법: ticket 대신 서버가 서명한 owner 토큰을 로그인 결과(`/naver/result/{ticket}`)에 실어 주기. 더 튼튼하지만 앱 저장 구조를 바꿔야 합니다. 배포 단계에서 고려합니다.
- (나) 권장안: 임시 로그인 두 함수(`mock_login_page`, `mock_login`) 첫 줄에 `if _real_naver() and not settings.dev_tools_enabled: 404`를 둡니다.
  - 대시보드를 켠 로컬 시연에서는 계속 쓸 수 있고, 배포(키 있음, 대시보드 꺼짐)에서는 막힙니다.
  - `naver_callback`의 `_mock_codes` 처리(115-120줄)도 같은 조건으로 막습니다.

**같이 볼 곳**
- `app/modules/auth/router.py:179-217` 근처의 `test_logout`(180줄), `test_withdraw`(196줄)도 `login_id`만 받고 확인 없이 그 계정 가게 설정을 지우거나 연결을 끊습니다. 테스트 계정 전용이라 (나)와 같은 조건(진짜 키 + 대시보드 꺼짐이면 404)을 걸면 됩니다.
- `app/modules/stores/router.py`의 등록·로고·리뷰 불러오기도 인증이 없습니다. 이건 지금 설계("로그인이 생기면 store_selection에서 막는다")라 이 수정 범위 밖입니다.

**고친 뒤 확인**
- `server/tests/modules/test_owner_check.py`
  - `test_owner_key_must_match_login_ticket`: 시험 계정 로그인으로 ticket을 받습니다(`test_naver_login.py`의 흐름). 남의 owner_key + 그 ticket으로 신청하면 403입니다. 맞는 owner_key면 접수됩니다.
  - 기존 `test_sample_values_pass_and_link_account_to_store`(34줄) 등은 ticket을 함께 보내도록 고칩니다.
- `server/tests/modules/test_naver_login.py`
  - `test_mock_login_is_closed_when_real_naver_keys_are_set`: `settings.naver_login_client_id/secret`을 채우고 `dev_tools_enabled=False`로 둡니다. `/naver/mock/login?state=...`가 404입니다.
  - 기존 `test_without_keys_goes_to_test_login_page`(36줄)는 그대로 통과해야 합니다.
- 명령: `server/.venv/bin/python -m pytest server/tests/modules/test_owner_check.py server/tests/modules/test_naver_login.py -q`

**주의**
- 앱도 함께 바꿔야 합니다(ticket 보내기). 서버만 먼저 바꾸면 지금 앱의 사장님 확인이 모두 403이 됩니다. 한동안 ticket이 없으면 받아 주고 경고만 남기는 식으로 단계를 나누는 것도 방법입니다.
- 심사나 발표에서 진짜 키를 넣고도 `dona_demo`로 시연할 계획이면, (나)의 조건을 그 계획에 맞춰야 합니다. 예: `DEV_TOOLS_ENABLED=true`로 켜기.
- 전체 API 무인증은 문서에 정한 지금 설계입니다. 이 수정으로 바꾸지 않습니다.

---


## A10. 예약 상태 바꾸기가 확인과 저장 사이에 끊겨 있음

- 심각도: 낮음, 확신: 코드로 확인
- A8을 고치면서 넣은 상태 확인에 남은 틈입니다.

**무엇이 잘못되나**
- 같은 예약 문의(`REQUESTED`)를 두 기기에서 거의 동시에 처리합니다. 한쪽은 '받기'(CONFIRMED), 다른 쪽은 '어렵다고 답하기'(DECLINED)를 누릅니다.
- 두 요청 모두 `REQUESTED`를 읽어 상태 확인을 통과합니다. 나중에 실행된 UPDATE가 앞의 결과를 덮습니다.
- 결과적으로 CONFIRMED가 DECLINED로 바뀌어, A8에서 막으려던 "이미 정한 예약을 다시 바꾸기"가 일어납니다. 두 요청 모두 성공 응답을 받습니다.

**왜 생기나**
1. `set_status`는 `get()`으로 지금 상태를 읽고, 파이썬에서 `CHANGES`로 허용 여부를 봅니다.
2. 그다음 다른 연결에서 조건 없는 `UPDATE ... WHERE reservation_id = ?`를 실행합니다.
3. 읽기와 쓰기 사이에 다른 요청이 끼어들 수 있습니다. FastAPI 동기 라우트는 스레드풀에서 동시에 돕니다.

**문제 코드**

`server/app/data_pipeline/reservations.py:106-118`
```python
106 def set_status(reservation_id: int, status: str) -> dict:
...
111     row = get(reservation_id)                                        # ← 읽기 (연결 1)
112     if row is None:
113         raise ReservationError("NOT_FOUND", "예약을 찾지 못했어요")
114     if row["status"] != status and ((row["status"], status) not in CHANGES or (status == "CANCELED" and row["source"] != "OWNER")):
115         raise ReservationError("BAD_TRANSITION", "이미 정한 예약이에요")
116     with _db() as conn:
117         conn.execute("UPDATE reservations SET status = ?, updated_at = ? WHERE reservation_id = ?", (status, now_seoul().isoformat(), reservation_id))   # ← 조건 없는 쓰기 (연결 2)
118     return get(reservation_id)
```

**고치는 방향**
- 권장안: **UPDATE에 읽은 상태를 조건으로 붙이고, 바뀐 줄이 없으면 거절합니다.**
  ```python
  if row["status"] == status:
      return row  # 같은 상태로 다시 누름: 그대로 성공 (A8에서 정한 동작)
  with _db() as conn:
      cur = conn.execute(
          "UPDATE reservations SET status = ?, updated_at = ? WHERE reservation_id = ? AND status = ?",
          (status, now_seoul().isoformat(), reservation_id, row["status"]),
      )
  if cur.rowcount == 0:  # 그 사이 다른 요청이 먼저 바꿨다
      raise ReservationError("BAD_TRANSITION", "이미 정한 예약이에요")
  return get(reservation_id)
  ```
- SQLite UPDATE 한 문장은 원자적이라, 이것만으로 두 요청 중 하나만 성공합니다.
- 같은 상태로 다시 누르는 경우를 UPDATE 앞에서 먼저 돌려보내야 합니다. 그러지 않으면 `status = ?` 조건 때문에 rowcount가 0이 되어 거절됩니다.

**같이 볼 곳**
- 라우터(`server/app/modules/reservations/router.py`의 `_change`)는 `ReservationError`를 `_fail`로 넘겨 422 `BAD_TRANSITION`으로 바꿉니다(`router.py:40-42`). 라우터는 바꿀 필요가 없습니다.
- A8에서 더한 시험 `test_canceled_or_declined_reservation_cannot_be_confirmed`, `test_reservation_cannot_be_changed_from_other_store`(`server/tests/modules/test_reservations.py`)는 그대로 통과해야 합니다.

**고친 뒤 확인**
- `server/tests/modules/test_reservations.py`에 시험을 더합니다.
  - `test_status_change_loses_if_status_changed_meanwhile`: 예약 문의를 만든 뒤 `reservations.get`을 바꿔 끼워 `REQUESTED`를 돌려주게 합니다. 실제 DB는 먼저 `DECLINED`로 바꿔 둡니다. 그다음 `set_status(id, "CONFIRMED")`를 부릅니다. assert: `ReservationError("BAD_TRANSITION")`이 나고, DB 상태는 `DECLINED` 그대로입니다.
  - `test_same_status_again_still_succeeds`: CONFIRMED를 두 번 보내도 두 번째가 성공합니다.
- 명령: `server/.venv/bin/python -m pytest server/tests/modules/test_reservations.py -q`

**주의**
- 데모 규모에서는 일어나기 어렵습니다. 다만 네이버 예약을 실제로 이어 붙이면(네이버 쪽 응답과 사장님 앱이 같은 예약을 바꿈) 흔해질 수 있습니다.
