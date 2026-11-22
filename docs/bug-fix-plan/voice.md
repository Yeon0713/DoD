# server/voice 버그 수정 계획 (V7, V10~V13)

2026-11-22 · 기준 코드: 브랜치 `jiho/feat-hr-demo-docs`, 커밋 `d497f97`에 이번 수정 22건을 더한 작업 트리(아직 커밋 전) · 줄 번호는 이 작업 트리 기준입니다. 코드가 바뀌었으면 함수 이름으로 찾아 주세요.

- V1~V6, V8, V9는 2026-11-22에 고쳐서 이 문서에서 뺐습니다.
- V10~V13은 그 수정을 다시 리뷰하다 찾은 것입니다. V10·V12는 그 수정에서 생겼고, V11·V13은 그 수정 뒤에도 남은 틈입니다.
- 지금 시험: `voice/tests` 455 통과, 2 건너뜀 (`cd server && .venv/bin/python -m pytest voice/tests -q`). miniconda python 에는 pytest 가 없으니 꼭 `.venv` 로 돌립니다.

| # | 버그 | 심각도 | 확신 | 파일 |
|---|---|---|---|---|
| V7 | 자정을 넘겨 영업하는 가게의 시간 계산이 조용히 틀어짐 | 중간 | 코드로 확인 (24:00 은 가능성 있음) | `api/account.py:110-117`, `hours.py`, 문 닫는 시각을 쓰는 5곳 |
| V10 | 묻는 중 표시가 오래 남아 있으면 새 리뷰 알림에 한 "도나야, 진행해"가 엉뚱한 질문의 대답이 됨 | 중간 | 코드로 확인 | `dialog/turn.py:403, 439` |
| V11 | 알바생 할 일 묶음 승인이 그 사이 접힌 제안도 넣음 | 낮음 | 코드로 확인 | `jobs/batch_ask.py:235-242` |
| V12 | 앱이 알림을 연 턴에서도 미뤄 둔 말과 수첩 질문이 버려짐 | 낮음 | 코드로 확인 | `dialog/turn.py:427-432` |
| V13 | 날짜가 바뀌어도 세션의 '묻는 중' 표시가 남음 | 낮음 | 코드로 확인 | `dialog/turn.py:379-380` |

**뿌리가 같은 것**
- V10·V13: 앱이 보내는 `session_id`(`donna-voice/app/src/lib/api.ts:273` `SESSION_ID = newId('sess')`)는 앱을 켤 때 한 번 만들어지고 날짜와 상관없이 이어집니다. 세션에 남은 `last_type`과 '묻는 중' 표시가 오래 살아남습니다. 둘 다 세션에 시각·날짜를 적는 수정이라 같이 고치면 좋습니다.
- V12는 V4·V6 수정의 부작용입니다. 고치는 방향에 따라 V4·V6이 다시 생길 수 있어, 먼저 정할 것이 있습니다.

---

## V7. 자정을 넘겨 영업하는 가게의 시간 계산이 조용히 틀어짐
- 심각도: 중간, 확신: 코드로 확인 (자정 넘김) / 가능성 있음 ("24:00")

**무엇이 잘못되나**
- 네이버 장사 시간은 자정을 넘기면 닫는 시각이 여는 시각보다 이릅니다. 예: 17:00 ~ 02:00. 응답 형식 주석에 그렇게 적혀 있습니다 (`server/app/modules/naver/response_format.py:12`: `close: str  # "22:00". 자정을 넘기면 "03:00" 처럼 오픈보다 이르다`).
- 음성 서버는 이 값을 그대로 가게 문서에 넣고, 문 닫는 시각을 늘 '같은 날 그 시각'으로 계산합니다. 그래서 그 가게에서는 다음처럼 됩니다.
  - 영업 중 아쉬운 리뷰 알림이 한 번도 돌지 않음: `in_alert_hours`가 `start <= moment < 같은 날 02:00`이라 늘 거짓 → 인턴·사원이어도 알림·묶음 창 없이 바로 답하기 길로 감 (`review_loop.on_new_review`)
  - "브리핑에서 못 물은 할 일"을 묻지 않음 (`unasked_today`가 02:00 뒤엔 늘 '문 닫음')
  - 사후 취소 기간(`_open_now`)이 늘 지난 것으로 계산돼 강등하지 않음
  - 묶음 창 알림 시각(`hr_batch._due`)이 닫는 시각에 맞춰지지 않음
  - 홈 가게 상태(`api/home.py:41`), 알바생 화면 구간(`staff.py:233`)도 틀림
- 사장님이 설정에서 시간을 고치려 해도 `apply_week`가 "닫는 시간이 여는 시간보다 늦어야 해요"로 거절합니다 (`hours.py:72-74`).
- 메인 앱은 같은 경우를 `OVERNIGHT_STORE_NOT_SUPPORTED`로 분명히 막습니다 (`app/data_pipeline/analysis_to_plan_inputs.py:74-80`). 음성 서버만 말없이 받습니다.
- 네이버가 24시간 가게에 "24:00"을 준다면 `at_time`이 `dt.datetime(..., 24, 0)`으로 `ValueError`를 내 브리핑 준비 등이 실패합니다. 실제로 "24:00"이 오는지는 확인하지 못했습니다.

**왜 생기나**
1. 앱으로 가입한 가게는 `account.ensure`가 네이버 `weekly_hours`를 그대로 `naver_hours`로 저장합니다 (`api/account.py:110-121`). 닫는 시각이 여는 시각보다 이른지 보지 않습니다.
2. `hours.on`은 그날 `{"open", "close"}` 글자를 그대로 돌려줍니다 (`hours.py:50-54`).
3. 쓰는 곳마다 `at_time(같은 날, close)`로 계산합니다. `at_time`은 날짜와 "HH:MM"을 그대로 합칩니다 (`app/core/seoul_time.py:34-37`).

**문제 코드**

`api/account.py:110-117`
```python
110      days = []
111      for code in WEEKDAY_CODES:
112          hours = place.weekly_hours.get(code)
113          days.append({"open": hours.open, "close": hours.close} if hours else None)   # ← "17:00"~"02:00" 그대로
114      if not any(days):  # 네이버에 장사 시간이 없으면 가게 파일의 것
115          days = [...]
116                  for i in range(7)]
117      open_time, close_time = _usual(days)
```

`jobs/review_loop.py:47-52`
```python
47  def in_alert_hours(store: dict, moment: dt.datetime) -> bool:
48      today = hours.on(store, moment.date())
49      if today is None:
50          return False
51      start = at_time(moment.date(), today["open"]) - config.ALERT_BEFORE_OPEN
52      return start <= moment < at_time(moment.date(), today["close"])    # ← 같은 날 02:00 → 늘 거짓
```

같은 모양의 다른 곳
```python
# jobs/staff_tasks.py:93
    if not today or now >= at_time(now.date(), today["close"]):
# jobs/done_report.py:92
    return bool(today) and now < at_time(now.date(), today["close"])
# jobs/hr_batch.py:29
        close = at_time(now.date(), today["close"])
# api/home.py:41
    if t < time_of(today["close"]):
# voice/staff.py:233
    return "open" if t < today_["close"] else "closing"
```

`hours.py:72-74`
```python
72      for d in days:
73          if d and minutes(d["open"]) >= minutes(d["close"]):
74              raise ValueError("닫는 시간이 여는 시간보다 늦어야 해요")
```

**고치는 방향** (권장안: 먼저 정할 것 하나)
- 먼저 사람이 정합니다: 자정 넘김 가게를 (가) 지원하거나 (나) 메인 앱처럼 막고 알리거나.
- (가) 지원 (권장. 시간 계산 한 곳만 고치면 됨)
  1. `hours.py`에 함수 둘을 더합니다.
     - `close_at(day, today) -> datetime`: `close <= open`이면 `at_time(day + 1일, close)`, `"24:00"`이면 `at_time(day + 1일, "00:00")`, 아니면 `at_time(day, close)`
     - `open_at(day, today)`도 같은 자리에 둠 (`"24:00"` 대비)
  2. 위 "같은 모양" 5곳과 `in_alert_hours`를 `hours.close_at(...)`로 바꿉니다. 글자로 비교하는 `api/home.py:41`, `staff.py:233`은 분 단위(자정 넘으면 +1440)로 바꿉니다.
  3. 새벽 01:00 처럼 '어제 영업의 연장'인 시각은 `hours.on(store, 어제)`도 봐야 맞습니다. 영업 중 판정 함수(`in_alert_hours`, `unasked_today`, `_open_now`)에서는 `today`와 `yesterday` 둘을 봅니다.
  4. `apply_week`의 거절은 `close == open`만 막도록 풉니다 (자정 넘김 허용).
- (나) 막기 (작게)
  1. `account.ensure`에서 `close <= open`인 요일이 있으면 알림 기능을 끄는 표시를 두고, 설정 화면이나 가입 응답으로 알립니다.
  2. 최소한 `at_time`이 "24:00"에서 터지지 않도록 `"24:00"` → `"23:59"`로 바꿔 저장합니다.

**같이 볼 곳**
- `queue.next_prepare_at`(`jobs/queue.py`)은 여는 시각만 써서 영향이 없습니다.
- `schedule.slots`(식사 피크)는 여는 날만 보므로 영향이 작습니다.
- `instagram/posts.py:119`은 표시용 글자라 그대로 둬도 됩니다.
- 메인 앱의 같은 판단: `app/data_pipeline/db_rows_to_analysis_inputs.py:89` (`close_time < open_time`이면 +하루). 고칠 때 이 규칙과 맞춥니다.

**고친 뒤 확인**
- `voice/tests/test_hours.py`가 없으므로 새로 만들거나 `test_holidays.py`에 넣습니다.
  - `test_close_after_midnight_is_next_day`: `hours.close_at(2026-11-17, {"open": "17:00", "close": "02:00"}) == 2026-11-18T02:00+09:00`
  - `test_alert_hours_for_overnight_store`: 가게 `weekly_hours` 7칸 모두 17:00~02:00 → `review_loop.in_alert_hours(store, 23:30) is True`, `(다음 날 01:30) is True`, `(03:00) is False`
  - `test_24_00_does_not_crash`: `"close": "24:00"`이어도 `in_alert_hours`가 예외 없이 돎
- 명령: `cd server && .venv/bin/python -m pytest voice/tests -q` (시간 계산을 쓰는 시험이 넓게 퍼져 있어 전체를 돌립니다)

**주의**
- 시연 가게(s001, s005)는 자정을 넘기지 않으니 동작이 바뀌지 않아야 합니다. 전체 시험이 그대로 통과하는지가 기준입니다.
- 쉬는 날(`hours.on`이 None) 다음 날 새벽은 '어제 연장'으로 보지 않도록, 3번에서 어제가 쉬는 날이면 건너뜁니다.

---


## V10. 묻는 중 표시가 오래 남아 있으면 새 리뷰 알림에 한 "도나야, 진행해"가 엉뚱한 질문의 대답이 됨
- 심각도: 중간, 확신: 코드로 확인
- V1을 고치면서 생겼습니다.

**무엇이 잘못되나**
- 아침 브리핑 끝에 도나가 "인스타에 올릴까요?"(`type: "ask"`)라고 물었고, 사장님이 대답하지 않았습니다.
- 오후에 아쉬운 리뷰가 들어와 알림이 떴습니다. 사장님은 알림을 열지 않고 "도나야, 진행해"라고 말합니다.
- 그러면 이 말이 리뷰 알림의 대답이 되지 않습니다. 몇 시간 전 인스타 업로드 질문의 승인으로 처리됩니다.
- `ask_holiday`(휴무 질문), `ask_staff`(알바생 질문)가 남아 있을 때도 같습니다.

**왜 생기나**
1. V1 수정 전에는 리뷰 알림을 뒤로 미루는 질문이 `ask_permission`, `show_detail`, `ask_tasks` 셋뿐이었습니다.
2. V1 수정에서 이 목록을 `ASKING_TYPES` 전체로 넓혔습니다. 그래서 `ask`, `ask_holiday`, `ask_staff`도 리뷰 알림보다 먼저 처리됩니다.
3. `last_type`은 사장님 말이 무시되거나(`ignore`) 못 알아들은(`not_understood`) 턴을 빼고 매번 덮어씁니다(`turn.py:438-439`). 사장님이 대답하지 않으면 그대로 남습니다.
4. 앱의 `session_id`는 날짜와 상관없이 이어집니다(V13). 그래서 언제 물었는지와 상관없이, 마지막 질문이 리뷰 알림 처리를 막습니다.
5. 지금 코드에는 질문을 언제 했는지 적어 두는 칸이 없습니다. "알림이 그 질문보다 나중에 왔다"는 것을 알 수가 없습니다.

**문제 코드**

`server/voice/dialog/turn.py:400-405`
```python
400         addressed = bool(utterance.get("addressed"))
401         # 묻고 있는 아쉬운 리뷰가 있으면 "도나야, 진행해"도 그 대답이다 (다른 질문을 묻는 중이면 그쪽이 먼저)
402         live = review_loop.pending(store_id) if addressed else None
403         other_question = session.get("last_type") in ASKING_TYPES and session.get("last_type") != "ask_action"   # ← 언제 물었는지 안 봄
404         if live and not other_question:
405             session["last_type"] = "ask_action"
```

`server/voice/dialog/turn.py:53`, `438-439`
```python
 53 ASKING_TYPES = ("ask_action", "ask_staff", "ask_permission", "ask_tasks", "ask_holiday", "ask", "show_detail")
...
438     if response["type"] not in ("ignore", "not_understood"):
439         session["last_type"] = response.get("keep_context") or response["type"]   # ← 시각을 같이 적지 않음
```

**고치는 방향**
- 권장안: **알림과 질문 가운데 나중에 생긴 쪽이 대답을 받게 합니다.**
  1. `last_type`을 적는 곳(`turn.py:439`)에서 `session["last_at"] = iso(clock.now())`도 함께 적습니다. `iso`·`parse`는 `voice.clock`에서 가져옵니다(`review_loop.py:27`과 같은 import).
  2. 403줄 판정에 시각 비교를 더합니다.
     ```python
     asked_at = session.get("last_at")
     other_question = (session.get("last_type") in ASKING_TYPES and session.get("last_type") != "ask_action"
                       and (asked_at is None or live is None or parse(asked_at) >= parse(live["created_at"])))
     ```
     - 알림(`live["created_at"]`)이 마지막 질문보다 나중에 왔으면 리뷰 알림의 대답으로 봅니다.
     - 질문이 알림보다 나중이면 지금처럼 그 질문의 대답입니다. V1 상황(반려한 알림이 먼저, 휴무 질문이 나중)이 여기에 해당합니다.
     - `last_at`이 없는 예전 세션은 지금처럼 다른 질문이 먼저입니다(안전한 쪽).
- 다른 안: 목록을 V1 전처럼 좁히고 `ask_holiday`만 더하기. 코드는 작지만 `ask`·`ask_staff`가 V1과 같은 문제를 다시 냅니다. 권장하지 않습니다.

**같이 볼 곳**
- `_missed_tasks`(`turn.py:353-359`)도 같은 `last_type in ASKING_TYPES`로 "다른 것을 묻는 중"을 봅니다. 오래된 `last_type`이 남아 있으면 "그 전에 하나만요"(못 물은 할 일)도 뜨지 않습니다. V13에서 함께 풉니다.
- `review_loop.pending`(`jobs/review_loop.py:298-307`)은 최근 2시간(`LOOK_BACK`) 안 알림만 돌려줍니다. 그래서 `live["created_at"]`은 늘 2시간 안입니다.

**고친 뒤 확인**
- `server/voice/tests/test_loop_negative.py`에 시험을 더합니다.
  - `test_newer_alert_wins_over_old_unanswered_question`: 세션에 `last_type: "ask"`(인스타 질문)과 한 시간 전 `last_at`을 넣어 둡니다. 새 리뷰로 알림을 만든 뒤 `addressed` "도나야, 진행해"를 보냅니다. assert: 의도가 `action.approve`이고 리뷰 `reply_status == "posted"`입니다.
  - 기존 V1 시험 `test_called_yes_to_another_question_is_not_a_review_answer`, `test_called_yes_to_a_staff_question_is_not_a_review_answer`는 그대로 통과해야 합니다. 두 시험은 질문이 알림보다 나중인 경우입니다.
- 명령: `cd server && .venv/bin/python -m pytest voice/tests/test_loop_negative.py voice/tests/test_hr_flow.py -q`. 그다음 voice 전체를 돌립니다.

**주의**
- 시험 시계(`voice.clock`)를 쓰는 시험이 많습니다. `last_at`은 꼭 `clock.now()`로 적어야 시험 시계와 맞습니다.
- 앱이 알림을 연 턴(`event: "notice"`)은 이 판정을 지나지 않습니다(`turn.py:383-397`). 바뀌는 것은 사장님이 알림을 열지 않고 바로 말한 경우뿐입니다.

---

## V11. 알바생 할 일 묶음 승인이 그 사이 접힌 제안도 넣음
- 심각도: 낮음, 확신: 코드로 확인 (일어나는 틈은 짧음)
- V2·V9를 고친 뒤 남은 틈입니다.

**무엇이 잘못되나**
- 사원 직급 묶어 묻기에 교정 카드 제안(알바생 할 일)이 들어 있습니다. 같은 제안을 작업 큐의 25분 시간 넘김(`review_loop.fallback`)이 V2 수정으로 접을 수 있습니다(`_decline_card`).
- 두 일이 거의 같은 때 일어나면 이렇게 됩니다.
  1. 사장님이 "응"이라고 합니다.
  2. `_settle`이 `_task_pending`으로 제안이 아직 살아 있다고 봅니다.
  3. 바로 그 뒤 작업 큐가 제안을 `declined`로 바꿉니다.
  4. `_task_approve` → `proposals.apply`가 상태를 보지 않고 알바생 할 일을 넣습니다. 제안은 `applied`가 되고, 인사과에는 `approved`가 남습니다.
- V9에서 리뷰 답글 결재 네 함수는 "작업 큐가 먼저 정했으면 False"로 고쳤습니다. 할 일 제안 승인만 늘 True를 돌려줍니다.
- 리뷰에서는 "`_settle`이 턴 시작 때 읽은 오래된 view로 본다"고 했지만, 다시 보니 아닙니다. `_task_pending`은 저장소에서 제안을 새로 읽습니다(`batch_ask.py:211-213`). 그래서 틈은 `_task_pending`과 `apply` 사이의 짧은 순간뿐입니다.

**왜 생기나**
1. `proposals.apply`는 `applied`만 확인하고, `declined`·`expired`도 그대로 넣습니다(`proposals.py:67-85`). 반려한 뒤 "도나야, 진행해"로 다시 열면 카드를 넣으려고 일부러 그렇게 둔 것입니다(`review_loop._decline_card` docstring, 시험 `test_reopen_after_cancel_still_pins_the_card`).
2. `_task_approve`는 이 `apply`를 그대로 부르고 늘 True를 돌려줍니다.
3. `_task_reject`의 주석은 "apply·decline 이 락 안에서 상태를 다시 본다"고 하지만, `apply`는 상태를 다시 보지 않습니다. 주석이 틀렸습니다.

**문제 코드**

`server/voice/jobs/batch_ask.py:235-242`
```python
235 def _task_approve(view: VoiceStore, ref: str) -> bool:
236     proposals.apply(ref, "owner_yes")                  # ← 상태를 보지 않고 넣음
237     return True
238
239
240 def _task_reject(view: VoiceStore, ref: str) -> bool:
241     proposals.decline(ref, "owner_no")  # 제안은 apply·decline 이 락 안에서 상태를 다시 본다   ← apply 는 아님
242     return True
```

`server/voice/jobs/batch_ask.py:309-315`
```python
309 def _settle(view: VoiceStore, items: list[dict], approve: bool, said: str | None) -> None:
310     for i in items:
311         if not KINDS[i["job"]].pending(view, i["ref"]):    # ← 락 밖에서 확인
312             continue  # 다른 기기에서 먼저 정했다
313         if not (KINDS[i["job"]].approve if approve else KINDS[i["job"]].reject)(view, i["ref"]):
314             continue  # 말 처리를 시작한 뒤 작업 큐가 먼저 정했다 (올렸다 등)
315         hr.record(view.store_id, i["job"], i["ref"], "approved" if approve else "rejected", said)
```

`server/voice/proposals.py:67-72`
```python
67 def apply(pid: str, trigger: str) -> dict:
68     """승인한 제안을 알바생 할 일로 넣는다. 이미 넣었으면 그 할 일을 돌려준다 (두 번 넣지 않는다)."""
69     with repo._lock:
70         found = get(pid)
71         if found["state"] == "applied":                  # ← declined·expired 는 그대로 지나감
72             return next(...)
```

**고치는 방향**
- 권장안: **묶음 승인에서만 락 안에서 상태를 확인합니다.** `proposals.apply`는 바꾸지 않습니다(다시 열기 길 때문).
  ```python
  def _task_approve(view: VoiceStore, ref: str) -> bool:
      with repo._lock:  # RLock 이라 apply 안에서 다시 잡아도 된다
          found = proposals.get(ref)
          if not found or found["state"] not in proposals.LIVE:
              return False  # 그 사이 작업 큐가 접었다
          proposals.apply(ref, "owner_yes")
      return True


  def _task_reject(view: VoiceStore, ref: str) -> bool:
      with repo._lock:
          found = proposals.get(ref)
          if not found or found["state"] not in proposals.LIVE:
              return False
          proposals.decline(ref, "owner_no")
      return True
  ```
- `repo._lock`은 `threading.RLock`입니다(`voice/repo.py:29`). 그래서 `apply`·`decline` 안에서 다시 잡아도 막히지 않습니다.
- 틀린 주석(241줄)도 함께 고칩니다.

**같이 볼 곳**
- V9에서 고친 `_neg_approve`·`_neg_reject`·`_pos_approve`·`_pos_reject`(`batch_ask.py` 위쪽)가 같은 모양입니다. 새로 읽고 → 조건부로 쓰고 → bool을 돌려줍니다.
- `review_loop.decide`의 `action.approve`는 다시 열기 길이라 `apply`가 상태를 보지 않아야 합니다. 건드리지 않습니다.

**고친 뒤 확인**
- `server/voice/tests/test_hr_flow.py`에 시험을 더합니다.
  - `test_batch_task_approve_skips_proposal_declined_meanwhile`: 제안을 만든 뒤 `proposals.decline(pid, "timeout")`으로 접어 둡니다. 그다음 `batch_ask._task_approve(view, pid)`를 부릅니다. assert: 돌려준 값이 False이고, 제안 상태가 `declined` 그대로이고, 알바생 할 일이 늘지 않습니다.
  - `test_reopen_after_cancel_still_pins_the_card`(`test_loop_negative.py`)는 그대로 통과해야 합니다.
- 명령: `cd server && .venv/bin/python -m pytest voice/tests/test_hr_flow.py voice/tests/test_loop_negative.py -q`

**주의**
- 묶음 응답 말("알바생 할 일을 넣었어요")은 건너뛴 것이 있어도 지금처럼 나갑니다. V9와 같은 한계이고, 이번 범위 밖입니다.

---

## V12. 앱이 알림을 연 턴에서도 미뤄 둔 말과 수첩 질문이 버려짐
- 심각도: 낮음, 확신: 코드로 확인
- V4·V6을 고치면서 생겼습니다. **먼저 정할 것이 있습니다** (아래 "고치는 방향").

**무엇이 잘못되나**
- 사장님: "도나야, 내일 쉬어" → 도나: "그 전에 하나만요. 알바생 할 일 넣을까요?"(`ask_tasks`). "내일 쉬어"는 `deferred_text`에 남습니다.
- 그 사이 사장님이 아쉬운 리뷰 알림을 엽니다(`event: "notice"`). 응답 type이 `ask_action`이라 `deferred_text`가 지워집니다.
- 그 뒤 할 일에 대답해도 "내일 쉬어"는 실행되지 않습니다. 사장님에게 따로 알려 주지도 않습니다.
- "어느 규칙을 지울까요?"(`notebook_pending`) 뒤에 알림을 열어도 같은 방식으로 수첩 질문이 사라집니다.

**왜 생기나**
- 지우는 조건이 응답 type만 봅니다. 사장님이 실제로 말한 턴인지(`utterance`가 있는지)는 보지 않습니다.

**문제 코드**

`server/voice/dialog/turn.py:427-432`
```python
427     if response["type"] not in ("ask_tasks", "ignore", "not_understood") and not answered:
428         session.pop("deferred_text", None)  # "그 전에 하나만요"에 대답하지 않고 넘어갔다. 원래 말은 버린다
429     staff_tasks.remember_asked(response, session)
430     batch_ask.remember(response, session)
431     if not response.get("notebook_ask") and response["type"] not in ("ignore", "not_understood"):
432         session.pop("notebook_pending", None)  # "어느 규칙을 지울까요?"에 대답하지 않고 넘어갔다
```

**고치는 방향**
- 먼저 정합니다: **알림이 끼어들면 그 전에 묻던 것을 버릴지.**
- 권장안: **지금 동작(버리기)을 유지하고, 시험으로 의도를 고정합니다.** 까닭은 이렇습니다.
  - 알림 턴 뒤에는 `last_type`이 `ask_action`이 됩니다. 할 일 질문도, 수첩 질문도 더는 '묻는 중'이 아닙니다.
  - 이 상태에서 `deferred_text`를 남기면, 나중에 할 일에 대답하는 턴(예: 다음 브리핑)에서 실행됩니다. V6이 다시 생깁니다.
  - `notebook_pending`을 남기면 나중의 "두 번째 답글 지워"를 가로챕니다. V4가 다시 생깁니다.
- 다른 안 (나): 사장님이 말하지 않은 턴(`utterance is None`)에서는 지우지 않기. 이렇게 하려면 알림 대답이 끝난 뒤 할 일 질문을 다시 띄우는 처리까지 함께 넣어야 V6이 돌아오지 않습니다. 변경이 큽니다.
- 다른 안 (다): 알림 턴이 `deferred_text`를 버릴 때 응답 끝에 "아까 말씀하신 건 다시 말해 주세요" 한 줄을 붙이기. 사장님이 말을 잃었다는 것은 알 수 있습니다.

**같이 볼 곳**
- V4·V6 시험: `test_unanswered_cut_in_does_not_replay_the_call_later`, `test_unanswered_cut_in_is_not_replayed_by_a_later_briefing_the_same_day`(`test_staff_tasks.py`), `test_unanswered_remove_question_does_not_take_a_later_undo`(`test_notebook.py`). 어느 안이든 이 시험들은 그대로 통과해야 합니다.

**고친 뒤 확인**
- 권장안이면 `server/voice/tests/test_staff_tasks.py`에 시험을 더합니다.
  - `test_notice_between_cut_in_and_answer_drops_the_call`: "도나야, 내일 쉬어" → 끼어든 할 일 질문 → `event: "notice"` 턴 → "응, 넣어". assert: 휴무가 적히지 않고, 응답에 휴무 말이 없습니다.
- 명령: `cd server && .venv/bin/python -m pytest voice/tests/test_staff_tasks.py voice/tests/test_notebook.py -q`

**주의**
- (나)를 고르면 V6 재현 순서(끼어든 질문 → 대답 없음 → 다음 날 할 일 대답)를 꼭 다시 시험합니다.

---

## V13. 날짜가 바뀌어도 세션의 '묻는 중' 표시가 남음
- 심각도: 낮음, 확신: 코드로 확인
- V4·V6의 뿌리입니다. V4·V6 수정은 다른 턴이 하나라도 끼면 표시를 지우지만, 사이에 턴이 하나도 없는 경우는 남습니다.

**무엇이 잘못되나**
- 어제 도나의 마지막 말이 "어느 규칙을 지울까요?"였고, 사장님이 대답하지 않고 앱을 닫았습니다.
- 오늘 첫 말이 "도나야, 두 번째 답글 지워"면, 그 말이 수첩 규칙 지우기로 갑니다.
- 같은 방식으로 어제 남은 `last_type`(V10), `batch`, `tasks_pending`, `holiday_pending`, `staff_pending`도 오늘 첫 말을 가로챌 수 있습니다.

**왜 생기나**
- 앱의 `session_id`(`donna-voice/app/src/lib/api.ts:273`, `SESSION_ID = newId('sess')`)는 앱을 켤 때 한 번 만들어지고, 날짜와 상관없이 이어집니다.
- 서버는 세션을 날짜로 나누지 않습니다. `session_id`가 없을 때만 `sess_<날짜>_<가게>`를 씁니다(`turn.py:379`).

**문제 코드**

`server/voice/dialog/turn.py:379-380`
```python
379     session_id = request.get("session_id") or f"sess_{clock.now():%Y%m%d}_{store_id}"   # ← 앱이 보낸 id 는 날짜를 넘김
380     session = repo.get("session", session_id) or {"id": session_id, "store_id": store_id, "step": None, "mode": "idle", "last_type": None}
```

**고치는 방향**
- 권장안: **세션에 날짜를 적고, 날짜가 바뀌면 묻는 중 칸을 비웁니다.** 380줄 바로 뒤에 넣습니다.
  ```python
  ASKING_KEYS = ("notebook_pending", "deferred_text", "batch", "tasks_pending", "holiday_pending", "staff_pending",
                 "alert_id", "story_id", "hr_batch")
  today = clock.now().date().isoformat()
  if session.get("day") != today:
      for key in ASKING_KEYS:
          session.pop(key, None)
      if session.get("last_type") in ASKING_TYPES:
          session["last_type"] = None
      session["day"] = today
  ```
- 세션 칸 이름은 `voice` 안에서 `session["..."]`로 쓰는 것을 모아 고른 것입니다. `mode`, `step`(브리핑 진행)은 브리핑 쪽이 따로 다루므로 여기서는 건드리지 않습니다.
- 날짜는 가게 영업일이 아니라 달력 날짜로 봅니다. V7(자정 넘김 영업)을 지원하게 되면 영업일로 바꿔야 합니다.

**같이 볼 곳**
- V10의 `last_at`과 같은 곳(세션)을 만집니다. 같이 고치면 좋습니다.
- `_missed_tasks`(`turn.py:353-359`)는 오늘 첫 말에서 `last_type`이 비면 "그 전에 하나만요"를 제대로 띄웁니다.

**고친 뒤 확인**
- `server/voice/tests/test_notebook.py`에 시험을 더합니다.
  - `test_remove_question_does_not_survive_the_night`: "어느 규칙을 지울까요?"까지 간 뒤 시험 시계를 다음 날로 옮깁니다. 같은 `session_id`로 "도나야, 두 번째 답글 지워"를 보냅니다. assert: 수첩 규칙이 그대로입니다.
- `server/voice/tests/test_staff_tasks.py`에 시험을 더합니다.
  - `test_deferred_text_cleared_on_new_day`: 끼어든 할 일 질문 뒤 다음 날로 옮기고 같은 세션으로 말합니다. assert: `deferred_text`가 없습니다.
- 명령: `cd server && .venv/bin/python -m pytest voice/tests -q` (세션을 쓰는 시험이 넓게 퍼져 있어 전체를 돌립니다)

**주의**
- 기존 시험 가운데 시계를 다음 날로 옮기고 같은 세션의 묻는 중 표시를 이어 쓰는 시험이 있으면 깨집니다. 깨지면 그 시험이 버그 동작에 기대고 있는지 먼저 봅니다.
