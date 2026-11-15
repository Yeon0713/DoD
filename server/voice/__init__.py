"""도나 v0.2.0 음성 앱의 에이전트 백엔드. 명세: docs/v0.2.0-voice-agent-handoff.md

기존 서버(app/)와 따로 도는 FastAPI 앱이다 (python -m voice.run_voice → :8100).
LLM 은 Harness(server/Harness)의 runner 로 돌리고, 답글(F3·F6), 고칠 점(F4), 규칙으로 못 가른 말(F8)에만 쓴다.
브리핑 단계 응답은 미리 만들어 두고(F7) 말할 때는 꺼내기만 한다 (LLM 없음, 1초 안).

  api/      /v1/home, /v1/turn, /v1/settings, /v1/dev/*
  dialog/   뜻 알아듣기(규칙) + 브리핑 진행 상태
  jobs/     미리 해 두는 일: 리뷰 나누기, 바로 답하기, 고칠 점, 좋아한 점, 답글 예약, 브리핑 묶음, 작업 큐
  agents/   Harness AgentSpec: 답글, 고칠 점, 뜻 판정
  repo.py   sqlite 저장소 (db/app_data/voice.db)
  clock.py  백엔드가 아는 '지금' (dev/clock 으로 움직인다)
  width.py  화면 글자 폭 한도
"""
