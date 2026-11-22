# server/Harness 버그 수정 계획 (H9, H10)

2026-11-22 · 기준 코드: 브랜치 `jiho/feat-hr-demo-docs`, 커밋 `d497f97`에 이번 수정 22건을 더한 작업 트리(아직 커밋 전) · 줄 번호는 이 작업 트리 기준입니다. 코드가 바뀌었으면 함수 이름으로 찾아 주세요.

- H1~H8은 2026-11-22에 고쳐서 이 문서에서 뺐습니다.
- H9·H10은 그 수정을 다시 리뷰하다 찾은 것입니다. H9는 H1 수정에서 생겼고, H10은 H6 수정에 남은 문제입니다.
- 시험 명령은 모두 `cd server` 에서 돕니다. 지금 `.venv/bin/python -m pytest Harness/tests -q` 는 327개 모두 통과합니다.

| # | 버그 | 심각도 | 확신 | 주요 파일 |
|---|---|---|---|---|
| H9 | 제안 하나의 모양이 틀리면 그 가게의 에이전트 실행 전체가 멈춤 | 낮음 | 코드로 확인 (지금 그런 값이 오는 길은 못 찾음) | `app_bridge.py:145` |
| H10 | 근거 trace 줄의 길이 상한(4000자)이 모자라 평가가 근거 있는 숫자를 '근거 없음'으로 셈 | 중간 (평가 지표만) | 가능성 있음 | `runner.py:36, 55, 130`, `trace.py:68` |

**고치는 순서 제안**
1. H10: batch 평가를 다시 돌리기 전에 고칩니다. 그래야 다시 돌린 결과를 믿을 수 있습니다.
2. H9: 작고 독립적이라 언제 해도 됩니다.

---

## H9. 제안 하나의 모양이 틀리면 그 가게의 에이전트 실행 전체가 멈춤

- 심각도: 낮음, 확신: 코드로 확인 (지금 Proposal이 아닌 값이 오는 길은 찾지 못함)
- H1을 고치면서 생겼습니다.

**무엇이 잘못되나**
- `run_all`이 할 일 하나의 결과로 Proposal이 아닌 값을 받으면, `_remember`가 `TypeError`를 던집니다.
- 이 예외는 할 일별 try 밖에서 나서 `run_all` 전체를 빠져나갑니다. 그러면 이렇게 됩니다.
  - 남은 할 일(예: 뒤쪽 REVISIT_REPLY·POSTER)이 돌지 않습니다.
  - supervisor 조율(`_coordinate`)이 돌지 않습니다.
  - `_run_safely`가 가게 상태를 `failed`로 적고, 앞서 끝난 결과만 남습니다.
- 같은 `_remember`를 `_coordinate`에서는 try 안에서 부르므로, 거기서는 묶음 하나만 건너뜁니다. 두 곳의 처리가 다릅니다.

**왜 생기나**
1. H1에서 `_remember` 맨 앞에 "Proposal이 아니면 TypeError"를 넣었습니다. 모양이 틀린 값이 `_proposals`에 들어가 대시보드 `status()`까지 깨지는 것을 막으려는 것입니다.
2. `run_all`의 try는 에이전트 호출만 감싸고, `_remember` 호출(145행)은 감싸지 않습니다.
3. 수정 전에는 틀린 값이 `_proposals`에 그대로 들어가 대시보드가 깨졌습니다. 지금은 가게 전체 실행이 멈춥니다. 증상이 옮겨 갔을 뿐, 할 일 하나의 문제가 가게 전체로 번지는 것은 같습니다.
4. 지금 코드에서 에이전트가 Proposal이 아닌 값을 돌려주는 길은 찾지 못했습니다. H1 수정 뒤 캐시는 Proposal로 되살아나고, 예전 형식의 중첩 항목은 빗나감(None)으로 봅니다. 그래서 확신은 "코드로 확인", 심각도는 낮음입니다.

**문제 코드**

`server/Harness/app_bridge.py:131-146`
```python
131     for number, item in enumerate(items, 1):
132         _update(store_id, current=f"{item.task_type} {item.plan_id}")
133         ctx = RunContext(snapshot=snapshot, now=snapshot.computed_at)
134         try:
135             if item.task_type in ("REVISIT_REPLY", "REORDER_NUDGE"):
136                 proposal = reply_agent.draft(item, ctx)
...
141         except Exception:
142             logger.exception("%s 에이전트 실패: %s", store_id, item.plan_id)
143             proposal = None
144         if proposal is not None:
145             _remember(snapshot, item, proposal)           # ← try 밖: TypeError 가 run_all 전체를 멈춤
146         _update(store_id, done=number)
```

`server/Harness/app_bridge.py:153-157`
```python
153 def _remember(snapshot, item, proposal: Proposal) -> None:
...
156     if not isinstance(proposal, Proposal):  # 모양이 틀린 값을 기억하면 대시보드(status)까지 깨진다. 기억하기 전에 실패시킨다 (H1)
157         raise TypeError(f"{item.plan_id} 제안이 Proposal 이 아니에요 ({type(proposal).__name__})")
```

**고치는 방향**
- 권장안: **`_remember` 호출을 할 일별 try 안으로 옮깁니다.** `_coordinate`(183-197행)와 같은 방식입니다.
  ```python
          try:
              if item.task_type in ("REVISIT_REPLY", "REORDER_NUDGE"):
                  proposal = reply_agent.draft(item, ctx)
              ...
              if proposal is not None:
                  _remember(snapshot, item, proposal)
          except Exception:
              logger.exception("%s 에이전트 실패: %s", store_id, item.plan_id)
          _update(store_id, done=number)
  ```
- `_remember`의 TypeError 확인은 그대로 둡니다. 대시보드를 지키는 데 필요합니다.

**같이 볼 곳**
- `_coordinate`(`app_bridge.py:171-199`): 이미 try 안에서 `_remember`를 부릅니다.
- H1에서 더한 시험 `test_bad_supervisor_result_does_not_stop_other_batches`(`Harness/tests/test_app_bridge.py`)가 `_coordinate` 쪽을 확인합니다. 같은 모양으로 `run_all` 쪽 시험을 만듭니다.

**고친 뒤 확인**
- `server/Harness/tests/test_app_bridge.py`에 시험을 더합니다.
  - `test_bad_agent_result_does_not_stop_other_items`: `reply_agent.draft`를 바꿔 끼워 첫 할 일에는 dict를, 나머지에는 정상 Proposal을 돌려주게 합니다. `run_all`을 부릅니다. assert: 예외 없이 끝나고, 나머지 할 일의 제안이 `_proposals`에 있고, supervisor가 불렸습니다(`_batches`에 기록).
- 명령: `cd server && .venv/bin/python -m pytest Harness/tests/test_app_bridge.py -q`

**주의**
- 이 수정 뒤 `run_all`의 진행 상태는 실패한 할 일이 있어도 `done`으로 끝납니다. 실패는 로그에만 남습니다. 지금 에이전트 실패(141-143행)와 같은 처리입니다.

---

## H10. 근거 trace 줄의 길이 상한(4000자)이 모자라 평가가 근거 있는 숫자를 '근거 없음'으로 셈

- 심각도: 중간 (평가 지표만), 확신: 가능성 있음 (코드로 확인)
- H6을 고치면서 남은 문제입니다.

**무엇이 잘못되나**
- H6은 평가가 근거를 다시 셀 때 잘린 trace를 쓰지 않도록, 근거 줄(start 입력, 도구 결과)의 상한을 `EVIDENCE_DETAIL_LENGTH = MAX_RESULT_CHARS + 1000`(3000 + 1000 = 4000자)으로 키웠습니다.
- 그런데 실제 근거 줄은 4000자를 넘을 수 있습니다.
  - **start 줄**: `{"input": user}`의 user 메시지는 길이 제한이 없습니다. supervisor는 묶음의 할 일·제안·충돌을 모두 넣으므로 할 일 수에 비례해 길어집니다.
  - **도구 줄**: `{"args": ..., "result": result}`를 `json.dumps`로 한 번 더 감쌉니다. result는 최대 3000자이지만, result가 JSON 글자면 따옴표마다 `\`가 붙고 줄바꿈은 `\n` 두 글자가 됩니다. args도 더해집니다.
- 4000자를 넘은 줄은 잘려 JSON이 깨집니다. H6 수정 뒤 `batch_eval.tool_evidence`는 깨진 줄을 경고만 남기고 건너뜁니다.
- 러너는 검사할 때 원래 근거를 다 봤는데, 평가는 그 근거를 못 봅니다. 그래서 초안의 숫자를 '근거 없는 숫자'(`ungrounded_numbers`)로 잘못 셉니다. B 시스템 점수가 실제보다 낮게 나옵니다.

**왜 생기나**
1. 상한을 도구 결과 길이(`MAX_RESULT_CHARS`)만 기준으로 잡았습니다. 감싼 뒤의 길이와 start 입력 길이는 고려하지 않았습니다.
2. `trace.record`는 `limit`가 정수일 때만 동작합니다. "자르지 않음"을 뜻하는 값이 없습니다.

**문제 코드**

`server/Harness/runner.py:36`, `55`, `129-130`
```python
 36 EVIDENCE_DETAIL_LENGTH = MAX_RESULT_CHARS + 1000  # 근거(입력, 도구 결과)를 남기는 trace 줄은 자르지 않게 (평가가 다시 센다, H6)   ← 4000자
...
 55     log(step=0, kind="start", name=task_id, detail={"input": user}, limit=EVIDENCE_DETAIL_LENGTH)   # ← user 길이 제한 없음
...
129                 log(step=step, kind="tool", name=call.name, detail={"args": call.arguments, "result": result},
130                     limit=EVIDENCE_DETAIL_LENGTH)     # ← json.dumps 로 감싸며 길어짐
```

`server/Harness/trace.py:62-69`
```python
62 def record(
63     *, run_id: str, parent_run_id: str | None, agent: str, store_id: str | None, step: int, kind: str,
64     name: str | None = None, detail: object = None, limit: int = DETAIL_LENGTH,
65 ) -> None:
...
67     text = detail if isinstance(detail, str) or detail is None else json.dumps(detail, ensure_ascii=False, default=str)
68     if text is not None and len(text) > limit:                 # ← limit=None 을 받지 못함
69         text = text[:limit] + "…"
```

`server/Harness/evals/batch_eval.py:142-146`
```python
142             try:
143                 detail = json.loads(step["detail"])
144             except (TypeError, ValueError):
145                 logger.warning("잘린 실행 기록은 근거로 쓰지 않아요: ...")   # ← 잘린 줄의 근거가 빠짐
146                 continue
```

**고치는 방향**
- 권장안: **근거 줄은 자르지 않습니다.**
  1. `trace.record`의 `limit`가 `None`이면 자르지 않게 합니다: `limit: int | None = DETAIL_LENGTH`, 68행을 `if text is not None and limit is not None and len(text) > limit:`로 바꿉니다.
  2. `runner.py`의 두 곳(55, 130행)에 `limit=None`을 넘기고, `EVIDENCE_DETAIL_LENGTH` 상수는 지웁니다.
- 다른 안: 직렬화한 길이 기준으로 상한을 크게 잡기(예: 20000자). 아주 긴 입력이 오면 같은 문제가 다시 생기므로 권장하지 않습니다.

**같이 볼 곳**
- `Harness/tools.py:12`의 `MAX_RESULT_CHARS = 3000`: 도구 결과 자체를 자르는 곳입니다. 이 값은 바꾸지 않습니다(LLM에 넘기는 길이).
- `trace.recent_runs`는 대시보드용으로 최근 5000줄을 읽습니다. 줄이 길어지면 대시보드가 조금 느려질 수 있습니다(H5 보고에서 적은 것과 같음).

**고친 뒤 확인**
- `server/Harness/tests/test_eval_batch.py`에 시험을 더합니다.
  - `test_tool_evidence_keeps_very_long_input`: user 메시지가 6000자이고 그 안에 근거 숫자가 끝쪽에 있는 실행을 runner로 돌립니다. assert: `tool_evidence([run_id])`에 그 숫자가 들어 있고, 초안의 `ungrounded_numbers == []`입니다.
  - `test_record_without_limit_keeps_full_text`(`test_core.py`): `trace.record(..., detail="x" * 10000, limit=None)` 뒤 `steps_of`로 읽은 길이가 10000입니다.
  - 기존 `test_tool_evidence_keeps_long_results_and_input`은 그대로 통과해야 합니다.
- 명령: `cd server && .venv/bin/python -m pytest Harness/tests/test_eval_batch.py Harness/tests/test_core.py -q`

**주의**
- trace DB가 커집니다. 실행 하나당 근거 줄 몇 개가 수천~수만 자가 될 수 있습니다. 데모 규모에서는 괜찮지만, 오래 쓰면 trace DB 정리(오래된 줄 지우기)를 따로 생각해야 합니다.
- 고친 뒤 batch 평가를 다시 돌려야 합니다(H6 수정 뒤에도 아직 돌리지 않았음). 실제 CLOVA를 부릅니다.
