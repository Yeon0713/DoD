"""장부(지호 DB) → 서버 → 분석(태성) → 서버 → 계획 엔진 → 화면용 API 를 잇는 곳.

- read_store_db.py                 DB 에 들어가는 유일한 문. 한 가게 데이터만 꺼낸다
- db_rows_to_analysis_inputs.py    DB 행을 태성 분석 입력(AnalysisInputs) 모양으로 번역한다
- analysis_to_plan_inputs.py       태성 분석 결과를 계획 엔진 입력(PlanInputs) 모양으로 바꾼다
- store_snapshot_cache.py          분석과 계획을 돌린 결과를 가게별로 보관하고, 정해진 간격마다 다시 계산한다
- store_selection.py               어느 가게를 보여 줄지 정한다 (로그인이 생기면 여기서 사장님 가게로 바꾼다)
"""
