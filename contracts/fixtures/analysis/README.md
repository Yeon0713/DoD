# C2 분석 결과 고정 샘플 (데모 주간)

분석 줄(태성)이 손으로 만든 C2 고정 샘플이다. 분석 코드가 나오기 전에도 계획 엔진, API, 화면이 이 파일로 먼저 만든다.
열의 뜻은 [`../../schema.md`](../../schema.md)의 C2 절, 모양 정의는 `server/app/analysis/result_shapes.py`에 있다.

- 파일 하나 = 테이블 하나(`<테이블>.example.json`). 예시 데이터라서 이름에 `.example`을 붙였다. `{"_설명": "...", "rows": [...]}` 모양이고, `_설명`은 사람이 읽는 설명이다.
- 원본(C1) 리뷰 본문, 매장 설정, 행사, 경기는 여기 없다. 지금은 `server/tests/planner/sample_inputs/demo_week_inputs.example.json`(여헌)에 있는 것을 쓴다.
- 확인: `server/` 에서 `python -m pytest tests/analysis -v`. 이 샘플로 계획 엔진을 돌린 결과가 계획 엔진 테스트 입력으로 돌린 결과와 같은지도 본다.

## 데모 주간 정답과 샘플 대응

정답은 `server/tests/planner/test_demo_week.py`(리뷰 답글 토요일 규칙 반영)를 따른다.

| 알림 | 만드는 샘플 행 |
|---|---|
| 11/16 10:00 주간 예고 | calendar_day 11/16~22 전체 (11/18 SEASON 시작, 11/19 GAME, 11/21 EVENT) |
| 11/16 14:00 경기 포스터 승인 | calendar_day 11/19 DINNER·NIGHT HIGH, GAME `game_031` |
| 11/17 14:00 배달 지연 리뷰 답글 (1) | review_label `rv_118` (DELIVERY_DELAY, is_quick) |
| 11/17 14:00 배달 지연 개선 (2) | risk_signal `risk_004` (rv_105, rv_111, rv_118, detected_at 13:50) |
| 11/17 14:00 메뉴판 계절 전환 (3) | calendar_day 11/18 SEASON `season_winter` 새로 붙음 |
| 11/18 10:00 어제 점심 매출 +35% | sales_anomaly 11/17 LUNCH (known_reasons 비어 있음), sales_daily 11/17 LUNCH 810,000 |
| 11/18 14:00 메뉴판 경기, 축제 포스터 | calendar_day 11/19 GAME, 11/21 EVENT `event_012` |
| 11/19 14:00 메뉴판 경기 끝 | calendar_day 11/20 GAME 빠짐 |
| 11/20 14:00 메뉴판 축제 | calendar_day 11/21 EVENT 붙음 |
| 11/20 21:30 맛 불만 리뷰 답글 (1) | review_label `rv_131` (TASTE, is_quick) |
| 11/21 10:00 리뷰 답글 4건, c_m01 재주문 권유 | review_label `rv_109`, `rv_112`, `rv_121`, `rv_126`(불만 아님), customer_cycle `c_m01` MONTHLY + `rv_087` |
| 11/22 14:00 메뉴판 축제 끝 | calendar_day 11/23 EVENT 빠짐 |
| 11/18 야구는 어디에도 없음 | calendar_day 11/18 DINNER 에 GAME 태그 없음 (`game_028`) |

## 가정으로 둔 것 (받으면 바꾼다)

- 재계산은 알림 시각 10분 전이다(13:50, 21:20). `labeled_at`, `detected_at`이 이 시각이다.
- SEASON 은 효과가 +5%여도 붙는다(±10% 규칙 예외).
- 예상 매출은 반올림하지 않는다(820,000 × 1.26 = 1,033,200).
- `c_m01`의 마지막 주문은 10/23 19:00이다. 간격은 `[29, 35, 28]`로 두었다(계획 엔진 테스트 입력은 `[28, 35]`).
- 리뷰 ID는 `rv_` + 숫자 세 자리다. 목업 DB(정수 ID)와 겹치는 문제는 목업 v2에서 정한다.
