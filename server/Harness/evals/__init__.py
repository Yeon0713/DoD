"""에이전트 평가 공통 틀. 실제 CLOVA 를 부르는 측정을 같은 결과 모양으로 남긴다.

사용 (server/ 에서):
  python -m Harness.evals --help                     스위트 목록
  python -m Harness.evals <suite> [--runs 3] [--systems A,B] [--ids …] [--workers 4] [--concurrency 2]
                                  [--judge-mode tools|thinking]

부품
  report.py   결과 폴더 harness_eval/<suite>-<시각>/ 만들기, CLOVA 사용 기록·실행 기록 경로 바꿔 끼우기, 캐시 끄기,
              git 커밋·브랜치·dirty, 프롬프트·세트 sha256, result.json (schema 1) 쓰기
  metrics.py  비율(분모 0 이면 null), 정밀도·재현율·F1, Macro-F1, 3회 모두 통과(pass^k), 중앙값·최댓값·예산 안 비율
  systems.py  비교할 시스템. "B" = 지금 멀티 에이전트 하네스, "A" = 단일 에이전트(Harness/agents/single_agent.py)
  judge.py    CLOVA X 심판 (조건마다 따로, 3표 다수결, 답글에서 글자 그대로 옮긴 문제 문구)
  prompts/    심판 프롬프트 (judge_policy.txt 공통 정책, judge_cond_<조건>.txt, judge_json_answer.txt)
  cli.py      스위트 이름 → 실행 함수

결과는 db/app_data/harness_eval/ 아래에만 남는다 (git 에 올라가지 않는다). 운영 기록(clova_usage.db, harness_trace.db)과 섞지 않는다.
정답지(review_gold_*.xlsx)는 저장소에 넣지 않는다. 스위트가 --gold 또는 DONA_EVAL_GOLD 로 읽는다.
"""
