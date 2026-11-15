"""도나 에이전트 하네스. 설계: jh/agent_harness_design.md

LLM 기능을 CLOVA X function calling 에이전트로 돌리는 틀이다. 기존 서버 코드(app/)는 import 만 하고 고치지 않는다.
v0.2.0 음성 백엔드(server/voice/)가 runner, 검사기, LLM 검토(reply_critic)를 가져다 쓴다 (docs/v0.2.0-voice-agent-handoff.md).
기존 서버 흐름(스냅샷 계산, 화면 API)에는 아직 연결되지 않았다. 연결은 store_snapshot_cache 등에서 아래 입구를 부르면 된다.

입구
  runner.run(spec, task, ctx)                      에이전트 하나를 돌려 Proposal(제안) 또는 None 을 받는다
  agents.reply_agent.draft(item, ctx)               리뷰 답글 초안 / 재주문 인사
  agents.reply_agent.rewrite(text, ctx, ...)        사장님이 보고 있는 답글 다시 쓰기
  agents.complaint_agent.diagnose(item, ctx)        반복 불만 원인 분석
  agents.campaign_agent.plan_campaign(item, ctx)    메뉴판 후보 + 포스터 멘트
  supervisor.coordinate_batch(batch, proposals, ctx) 알림 묶음 안의 충돌 조율

부품
  clova_tools.py   CLOVA v3 Chat Completions + tools 호출 (기존 clova.ask 는 그대로 둔다)
  spec.py          AgentSpec, Tool, Budget, RunContext, Proposal
  runner.py        도구 호출 루프: 최종 답도 submit 도구로 받고, 검사에 걸리면 거절 이유를 돌려준다
  tools.py         도구 정의 도우미, 결과 직렬화(개인정보 가림)
  store_tools.py   StoreSnapshot 을 읽는 공용 도구 (읽기 전용)
  guards.py        규칙 검사 (기존 금지어 정규식을 가져다 쓴다)
  grounding.py     근거 장부와 근거 대조
  limiter.py       서버 전체 CLOVA 동시 호출 한도, 429 대기
  cache.py         (에이전트, 가게, 입력 해시, 프롬프트 버전) → 제안
  trace.py         실행 기록 (run_id, parent_run_id, 단계, 도구). 기존 clova_usage_log 는 고치지 않으므로 따로 둔다
  conflicts.py     알림 묶음 안 충돌 찾기 (규칙, LLM 없음)
  supervisor.py    충돌이 있는 묶음만 LLM 으로 조율, 일꾼 에이전트를 도구로 감싼다(agent_tool)
"""
