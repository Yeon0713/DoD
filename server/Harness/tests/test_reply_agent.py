"""① 리뷰 응대 에이전트와 LLM 검토(reply_critic)."""

from app.core import clova
from Harness.agents import quote_judge, reply_agent, reply_critic
from Harness.tests.fakes import FakeClova, call

R1 = "REVISIT_REPLY:r1:2026-11-15"
GOOD = "국물이 싱거우셨다니 정말 죄송합니다. 잔치국수 국물 간을 매일 다시 확인하겠습니다. 다음에는 꼭 제맛으로 드릴게요."
FIX = "잔치국수 국물 간을 매일 다시 확인하겠습니다."


def item(snapshot, plan_id):
    return next(i for i in snapshot.plan.plan_items if i.plan_id == plan_id)


def submit(text=GOOD, quoted=("국물이 너무 싱거웠어요",), menus=("잔치국수",), facts=()):
    return call("submit_reply", {"text": text, "quoted_review_words": list(quoted), "menus_mentioned": list(menus), "facts_used": list(facts)})


def judged(*quotes):
    """좁은 질문의 답: 해당하는 부분들 (없으면 없음)."""
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


fixed = judged  # 고칠 점 질문의 답. 읽기 쉽게 이름만 따로 둔다
unasked = judged  # 마지막 질문(리뷰와 상관없는 말)의 답


def test_reply_with_tools_and_critic_pass(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([call("get_customer_pattern", {}), call("get_recent_same_complaints", {})], [submit()], judged(), fixed(FIX), judged(), judged(), judged(), unasked())
    proposal = reply_agent.draft(item(snapshot, R1), make_ctx(fake))
    assert proposal.source == "AGENT" and proposal.content == {"kind": "REPLY", "text": GOOD}
    pattern, complaints = fake.tool_messages(1)
    assert "cx1" not in pattern  # 손님 키는 모델에게 주지 않는다
    assert '"other_reviews_last_7_days": 2' in complaints and "***-****-****" in complaints  # 전화번호 가림
    judge = fake.requests[2]  # 보상 판별: 리뷰와 답글을 주고 보상 제안이 있는지만 검증하게 한다
    assert judge["toolChoice"] == {"type": "function", "function": {"name": "submit_judgement"}} and judge["temperature"] == 0
    asked = judge["messages"][1]["content"]
    assert asked.startswith('리뷰: "국물이 너무 싱거웠어요.')  # 무엇에 대한 대답인지 알게 리뷰를 함께 준다
    assert f'답글: "{GOOD}"' in asked and asked.endswith("이 답글에 보상 제안이 있는지 검증해 줘.")
    asks = [fake.requests[n]["messages"][1]["content"].splitlines()[-1] for n in (3, 4, 5, 6, 7)]
    assert asks == ["이 답글이 리뷰의 불만을 고치겠다고 말했는지 검증해 줘.", "이 답글에 가게 사정을 말한 부분이 있는지 검증해 줘.",
                    "이 답글에 변명하거나 남 탓을 한 부분이 있는지 검증해 줘.", "이 답글에 손님을 아는 척한 부분이 있는지 검증해 줘.",
                    "이 답글에 손님이 리뷰에서 말하지 않은 이야기를 꺼낸 부분이 있는지 검증해 줘."]
    assert all(len(fake.requests[n]["messages"]) == 2 for n in range(2, 8))  # 답글을 쓴 대화와 섞지 않는다
    # 팀이 다듬어 온 답글 프롬프트 + 도구 사용 안내
    system = fake.requests[0]["messages"][0]["content"]
    assert "'테스트국수'의 사장님" in system and "[도구 사용]" in system


def test_critic_rejection_is_fed_back_and_rewritten(snapshot, make_ctx, frozen_clock):
    bad = "늦어서 정말 죄송합니다. 잔치국수 국물을 다시 확인할게요. 다음 주문 땐 면 한 그릇 더 넣어 드릴게요."
    fake = FakeClova([submit(bad)], judged("다음 주문 땐 면 한 그릇 더 넣어 드릴게요."), [submit()], judged(), fixed(FIX), judged(), judged(), judged(), unasked())
    proposal = reply_agent.draft(item(snapshot, R1), make_ctx(fake))
    assert proposal.content["text"] == GOOD
    # 보상 문장이 있고 사장님 지시가 없으면 코드가 거절한다. 나머지 기준 검토는 보상을 뺀 뒤에 부른다
    assert "검토에서 걸렸어요: 보상 약속 '다음 주문 땐 면 한 그릇 더 넣어 드릴게요.'" in fake.tool_messages(2)[0]


def test_greetings_and_promises_are_not_unasked_topics(snapshot, make_ctx, frozen_clock):
    # 실제 CLOVA 가 감사 인사·앞으로 할 일을 '리뷰에 없는 이야기'로 옮겨 와도 코드가 뺀다
    fake = FakeClova([submit()], judged(), fixed(FIX), judged(), judged(), judged(),
                     unasked("국물이 싱거우셨다니 정말 죄송합니다.", "잔치국수 국물 간을 매일 다시 확인하겠습니다."))
    proposal = reply_agent.draft(item(snapshot, R1), make_ctx(fake))
    assert proposal.source == "AGENT" and proposal.notes == []
    # 리뷰에 없는 이야기(묻지 않은 환불)는 거절
    reply = "불편을 드려 죄송합니다. 환불은 배달앱 고객센터에서만 가능해요. 국물 간을 다시 점검하겠습니다."
    fake = FakeClova(judged(), fixed("국물 간을 다시 점검하겠습니다"), judged(), judged(), judged(), unasked("환불은 배달앱 고객센터에서만 가능해요"))
    verdict_ = reply_critic.inspect(reply, make_ctx(fake), review_text="국물이 싱거웠어요", has_complaint=True)
    assert verdict_.violations[0].describe().startswith("리뷰와 상관없는 말 '환불은 배달앱 고객센터에서만 가능해요'")
    assert reply_critic.small_talk("주문해 주셔서 감사합니다. 늘 최선을 다하겠습니다.")


def test_critic_unavailable_marks_unchecked_and_uses_old_rules(snapshot, make_ctx, frozen_clock):
    refund = "국물이 싱거우셨다니 죄송합니다. 잔치국수는 환불해 드릴게요. 국물 간을 다시 확인하겠습니다."
    fake = FakeClova([submit(refund)], 500, [submit()], 500, 500, 500, 500, 500, 500)  # 여섯 질문 모두 실패
    proposal = reply_agent.draft(item(snapshot, R1), make_ctx(fake))
    assert "보상 약속 '잔치국수는 환불해 드릴게요.'" in fake.tool_messages(2)[0]  # 판별을 못 부르면 기존 금지어로 거른다
    assert proposal.content["text"] == GOOD and proposal.notes == ["검토 안 됨"]


def test_code_checks_before_critic(snapshot, make_ctx, frozen_clock):
    fake = FakeClova(
        [submit(quoted=("맛이 최악",))],
        [submit(menus=("짜장면",))],
    )
    proposal = reply_agent.draft(item(snapshot, R1), make_ctx(fake))
    assert "'맛이 최악' 는 리뷰에 글자 그대로 없어요. 리뷰 원문 \"국물이 너무 싱거웠어요." in fake.tool_messages(1)[0]
    assert proposal is None  # 두 번 거절 → 물러나기, 기존 함수도 (conftest 에서) 실패해 초안 없음
    assert fake.done()  # 코드 검사에서 걸려 LLM 검토는 부르지 않았다


def test_store_facts_only_from_memo(snapshot, make_ctx, frozen_clock):
    fact = "국내산 돼지고기만 써요"
    fake = FakeClova([submit(facts=(fact,))], [submit()], judged(), fixed(FIX), judged(), judged(), judged(), unasked())
    reply_agent.draft(item(snapshot, R1), make_ctx(fake))
    assert "목록에 없는 가게 사실" in fake.tool_messages(1)[0]
    fake = FakeClova([call("get_store_facts", {})], [submit(facts=(fact,))], judged(), fixed(FIX), judged(), judged(), judged(), unasked())
    proposal = reply_agent.draft(item(snapshot, "REVISIT_REPLY:r1:2026-11-15"), make_ctx(fake, store_facts=[fact]))
    assert proposal.source == "AGENT" and fact in fake.tool_messages(1)[0]


def test_nudge_uses_existing_rules_without_critic(snapshot, make_ctx, frozen_clock):
    no_menu = "늘 찾아 주셔서 감사해요. 이번 주말에도 든든한 한 끼 어떠세요?"
    with_menu = "늘 찾아 주셔서 감사해요. 이번 주말엔 새콤달콤한 비빔국수 한 그릇 어떠세요?"
    fake = FakeClova([submit(no_menu, quoted=(), menus=())], [submit(with_menu, quoted=(), menus=("비빔국수",))])
    proposal = reply_agent.draft(item(snapshot, "REORDER_NUDGE:c1:2026-11-15"), make_ctx(fake))
    assert proposal.content == {"kind": "NUDGE", "text": with_menu}
    assert "가게 메뉴 이름이 없음" in fake.tool_messages(1)[0]
    assert fake.done()  # 재주문 인사는 리뷰 답글이 아니라 LLM 검토를 부르지 않는다


def test_nudge_cache_is_per_customer(snapshot, make_ctx, frozen_clock):
    """다른 손님의 재주문 인사는 앞 손님 결과를 캐시에서 받지 않는다 (H2)."""
    from app.planner.data_shapes import Basis

    text = "늘 찾아 주셔서 감사해요. 이번 주말엔 새콤달콤한 비빔국수 한 그릇 어떠세요?"
    c1 = item(snapshot, "REORDER_NUDGE:c1:2026-11-15")
    c2 = c1.model_copy(update={"plan_id": "REORDER_NUDGE:c2:2026-11-15", "basis": Basis(kind="CUSTOMER", ref_id="c2")})
    fake = FakeClova([submit(text, quoted=(), menus=("비빔국수",))], [submit(text, quoted=(), menus=("비빔국수",))])
    reply_agent.draft(c1, make_ctx(fake))
    second = reply_agent.draft(c2, make_ctx(fake))
    assert len(fake.requests) == 2 and second.task_id == c2.plan_id
    again = reply_agent.draft(c2, make_ctx(fake))  # 같은 할 일은 캐시가 맞는다
    assert again is second and len(fake.requests) == 2


def test_rewrite_keeps_owner_numbers_and_owner_promise_is_allowed(snapshot, make_ctx, frozen_clock):
    current = "죄송합니다. 12월부터 국물을 바꿀게요."
    allowed = "정말 죄송합니다. 12월부터 국물을 바꾸고, 다음 주문 때 음료 하나 드릴게요."
    fake = FakeClova(
        [submit("정말 죄송합니다. 겨울부터 국물을 바꿀게요.", quoted=())],
        [submit(allowed, quoted=())], judged("다음 주문 때 음료 하나 드릴게요"), judged("음료 하나 드린다고"), fixed("12월부터 국물을 바꾸고"), judged(), judged(), judged(), 500,
        # 답글의 보상 → 사장님 지시도 보상인지 → 고칠 점 → 가게 사정 → 변명 → 아는 척 → 나머지 검토 실패
    )
    proposal = reply_agent.rewrite(current, make_ctx(fake), instruction="다음 주문 때 음료 하나 드린다고 해 줘", review_id="r1")
    assert "숫자" in fake.tool_messages(1)[0]
    assert proposal.content["text"] == allowed and proposal.notes == ["검토 안 됨"]  # 사장님 지시의 보상은 허용
    assert "사장님 지시: 다음 주문 때 음료 하나 드린다고 해 줘" in fake.requests[0]["messages"][1]["content"]


def test_fallback_uses_existing_writer(snapshot, make_ctx, frozen_clock, monkeypatch):
    monkeypatch.setattr(clova, "ask", lambda *args, **kwargs: "국물이 싱거우셨다니 죄송해요. 간을 다시 맞추겠습니다.")
    proposal = reply_agent.draft(item(snapshot, R1), make_ctx(FakeClova(500)))
    assert proposal.source == "FALLBACK" and proposal.content["text"].startswith("국물이 싱거우셨다니")


def test_supervisor_note_reaches_the_worker(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([submit()], judged(), fixed(FIX), judged(), judged(), judged(), unasked())
    reply_agent.draft(item(snapshot, R1), make_ctx(fake), supervisor_note="점검 카드의 '저녁 7시 몰림'과 같은 개선을 말해")
    assert "조율 지시(같은 알림에 함께 가는 다른 할 일과 맞추기): 점검 카드의" in fake.requests[0]["messages"][1]["content"]


def test_quote_judge_parse_keeps_only_real_quotes():
    reply = "죄송합니다! 간을 맞출게요. 다음엔 음료 드릴게요."
    assert quote_judge.sentences("죄송합니다! 간을 맞출게요.\n다음엔 음료 드릴게요") == ["죄송합니다!", "간을 맞출게요.", "다음엔 음료 드릴게요"]
    assert quote_judge.parse({"found": False, "quotes": []}, reply) == []
    assert quote_judge.parse({"found": True, "quotes": ["“다음엔 음료 드릴게요”", "없는 말"]}, reply) == ["다음엔 음료 드릴게요"]
    assert quote_judge.parse({"found": True, "quotes": ["없는 말"]}, reply) is None  # 있다면서 근거가 없으면 다시 묻는다
    assert quote_judge.parse({"found": "yes", "quotes": []}, reply) is None
    assert quote_judge.parse({"found": True, "quotes": ["다른 글"]}, reply, needs_quote=False) == [reply]  # 예·아니오만 보는 질문
    question = quote_judge.QUESTIONS["compensation"]
    assert quote_judge.user_message(question, "답이에요.", "맛있어요") == '리뷰: "맛있어요"\n답글: "답이에요."\n\n이 답글에 보상 제안이 있는지 검증해 줘.'


def test_owner_compensation_is_allowed_only_when_instructed(snapshot, make_ctx):
    reply = "국물이 싱거우셨다니 죄송합니다. 다음 주문 때 음료 하나 드릴게요."
    # 지시가 없으면 판별기가 찾은 보상 문장으로 바로 거절 (나머지 검토는 부르지 않는다)
    fake = FakeClova(judged("다음 주문 때 음료 하나 드릴게요."))
    verdict_ = reply_critic.inspect(reply, make_ctx(fake))
    assert not verdict_.ok and verdict_.violations[0].quote == "다음 주문 때 음료 하나 드릴게요." and fake.done()
    # 지시가 보상과 무관하면 거절
    fake = FakeClova(judged("다음 주문 때 음료 하나 드릴게요."), judged())
    verdict_ = reply_critic.inspect(reply, make_ctx(fake), owner_instruction="더 짧게 써 줘")
    assert not verdict_.ok and fake.done()
    # 지시에 보상이 있으면 통과시키고 나머지 기준을 검토한다
    fake = FakeClova(judged("다음 주문 때 음료 하나 드릴게요."), judged("음료 하나 드린다고"), judged(), judged(), judged(), unasked())
    verdict_ = reply_critic.inspect(reply, make_ctx(fake), owner_instruction="음료 하나 드린다고 해 줘")
    assert verdict_.ok and fake.done()


def test_complaint_reply_needs_a_fix_but_not_an_apology(snapshot, make_ctx):
    # 사과 없이 고칠 점만 있어도 통과 (나머지 기준 검토로 넘어간다)
    reply = "맛있게 드셔 주셔서 감사해요. 짜게 느끼신 부분은 간을 조금 줄여 보겠습니다."
    fake = FakeClova(judged(), fixed("간을 조금 줄여 보겠습니다"), judged(), judged(), judged(), unasked())
    assert reply_critic.inspect(reply, make_ctx(fake), review_text="맛있어요 근데 좀 짜요", has_complaint=True).ok
    # 고칠 점이 없으면 코드가 거절하고, 나머지 검토는 부르지 않는다
    reply = "불편을 드려 죄송합니다. 앞으로 더 노력하겠습니다."
    fake = FakeClova(judged(), fixed())
    verdict_ = reply_critic.inspect(reply, make_ctx(fake), review_text="너무 짜요", has_complaint=True)
    assert not verdict_.ok and verdict_.violations[0].kind == "NO_APOLOGY_OR_FIX" and fake.done()
    # 불만이 없는 리뷰(칭찬)는 고칠 점을 묻지 않는다
    fake = FakeClova(judged(), judged(), judged(), judged(), unasked())
    assert reply_critic.inspect("맛있게 드셔 주셔서 감사해요.", make_ctx(fake), review_text="맛있어요").ok
    assert fake.done()


def test_alt_shape_is_read():
    reply = "죄송해요. 배달 기사님이 늦으셨어요."
    # 400 뒤 다른 모양(quotes 만)으로 받은 답도 읽는다
    assert quote_judge.parse({"quotes": ["배달 기사님이 늦으셨어요"]}, reply) == ["배달 기사님이 늦으셨어요"]
    assert quote_judge.parse({"quotes": []}, reply) == []
    assert quote_judge.alt_tool(quote_judge.QUESTIONS["fix"]).name == "submit_judgement"  # 다른 모양도 이름이 같아야 강제가 유지된다


def test_store_claims_must_be_registered_and_memory_only_for_regulars(snapshot, make_ctx):
    claim = "저희는 매일 아침 직접 손질한 국내산 고기만 쓰는데 굽는 시간을 다시 보겠습니다."
    # 등록한 사실이 없으면 가게 사정은 거절
    fake = FakeClova(judged(), fixed("굽는 시간을 다시 보겠습니다"), judged("저희는 매일 아침 직접 손질한 국내산 고기만 쓰는데"))
    verdict_ = reply_critic.inspect(claim, make_ctx(fake), review_text="고기가 질겼어요", has_complaint=True)
    assert verdict_.violations[0].kind == "MADE_UP_FACT" and fake.done()
    # 등록한 사실과 같은 말이면 통과 (사실의 끝말만 달라도 된다)
    ok_claim = "국내산 돼지고기만 쓰고 있지만 굽는 시간을 다시 맞춰 보겠습니다."
    fake = FakeClova(judged(), fixed("굽는 시간을 다시 맞춰 보겠습니다"), judged("국내산 돼지고기만 쓰고 있지만"), judged(), judged(), unasked())
    ctx = make_ctx(fake, store_facts=["국내산 돼지고기만 써요"])
    assert reply_critic.inspect(ok_claim, ctx, review_text="고기가 질겼어요", has_complaint=True).ok
    # 다시 찾아 준 것에 고마워하는 말은 단골에게만
    thanks = "비빔국수 양념을 좋아해 주셔서 기뻐요. 자주 찾아 주셔서 감사해요."
    fake = FakeClova(judged(), judged(), judged(), judged("자주 찾아 주셔서 감사해요"))
    assert reply_critic.inspect(thanks, make_ctx(fake), review_text="맛있어요").violations[0].kind == "FAKE_MEMORY"
    fake = FakeClova(judged(), judged(), judged(), judged("자주 찾아 주셔서 감사해요"), unasked())
    assert reply_critic.inspect(thanks, make_ctx(fake), review_text="맛있어요", regular=True).ok
    # 단골이어도 자리·지난 주문을 아는 척하면 거절
    seat = "늘 같은 자리에 앉으시던 손님이시죠? 맛있게 드셔 주셔서 감사해요."
    fake = FakeClova(judged(), judged(), judged(), judged("늘 같은 자리에 앉으시던 손님이시죠?"))
    assert not reply_critic.inspect(seat, make_ctx(fake), review_text="맛있어요", regular=True).ok


def test_future_promises_are_not_store_claims_and_review_can_say_regular(snapshot, make_ctx):
    # 실제 CLOVA 가 앞으로 하겠다는 말을 가게 사정으로 옮겨 와도 코드가 뺀다
    reply = "국물이 싱거우셨다니 죄송합니다. 국물 간을 매일 다시 확인하겠습니다."
    fake = FakeClova(judged(), fixed("국물 간을 매일 다시 확인하겠습니다"), judged("국물 간을 매일 다시 확인하겠습니다"), judged(), judged(), unasked())
    assert reply_critic.inspect(reply, make_ctx(fake), review_text="국물이 싱거웠어요", has_complaint=True).ok
    # 손님이 리뷰에 "늘 시켜 먹는데"라고 썼으면 다시 찾아 준 것에 고마워해도 된다
    thanks = "늘 찾아 주셔서 감사해요. 오늘도 맛있게 드셨다니 기쁩니다."
    fake = FakeClova(judged(), judged(), judged(), judged("늘 찾아 주셔서 감사해요"), unasked())
    assert reply_critic.inspect(thanks, make_ctx(fake), review_text="늘 시켜 먹는데 오늘도 맛있네요").ok


def test_only_promises_keeps_claims_glued_to_promises():
    assert reply_critic.only_promises("국물 간을 매일 다시 확인하겠습니다")
    assert reply_critic.only_promises("든든하게 드실 수 있게 준비할게요")
    assert not reply_critic.only_promises("저희는 매일 아침 직접 손질한 국내산 고기만 쓰는데 굽는 시간을 다시 보겠습니다")
    assert not reply_critic.only_promises("가끔 기준에 맞지 않게 조리되는 경우가 있습니다")


def test_owner_instruction_has_its_own_question_and_word_fallback(snapshot, make_ctx):
    reply = "국물이 싱거우셨다니 죄송합니다. 다음 주문 시에는 만두 서비스를 드리겠습니다."
    # 하네스에서 더한 정규식이 "만두 서비스 드린다고"를 잡아 LLM 에게 묻지 않는다
    fake = FakeClova(judged("다음 주문 시에는 만두 서비스를 드리겠습니다."), fixed(), )
    verdict_ = reply_critic.inspect(reply, make_ctx(fake), review_text="싱거워요", has_complaint=True,
                                    owner_instruction="다음 주문 때 만두 서비스 드린다고 해 줘")
    assert verdict_.violations[0].kind == "NO_APOLOGY_OR_FIX"  # 보상은 통과하고 다음 기준(고칠 점)에서 걸렸다
    # 정규식에 안 걸리는 지시는 지시 전용 질문으로 묻는다
    gift = "국물이 싱거우셨다니 죄송합니다. 다음 주문 때 음료 하나 드릴게요."
    fake = FakeClova(judged("다음 주문 때 음료 하나 드릴게요."), judged("음료 하나 드린다고"), fixed(), )
    reply_critic.inspect(gift, make_ctx(fake), review_text="싱거워요", has_complaint=True,
                         owner_instruction="음료 하나 드린다고 해 줘")
    asked = fake.requests[1]["messages"][1]["content"]
    assert asked == '사장님 지시: "음료 하나 드린다고 해 줘"\n\n이 지시에 손님에게 보상을 주라는 내용이 있는지 검증해 줘.'
    # 지시 질문을 부를 수 없으면 같은 낱말("음료")로 본다. 낱말이 겹치지 않으면 거절
    fake = FakeClova(judged("다음 주문 때 음료 하나 드릴게요."), 500, fixed())
    verdict_ = reply_critic.inspect(gift, make_ctx(fake), review_text="싱거워요", has_complaint=True,
                                    owner_instruction="음료 하나 드린다고 해 줘")
    assert verdict_.violations[0].kind == "NO_APOLOGY_OR_FIX"
    assert not reply_critic.shares_word("더 짧게 써 줘", ["다음 주문 때 음료 하나 드릴게요."])


def test_extra_promise_patterns():
    from Harness.guards import promise_hit
    assert promise_hit("만두 서비스 드린다고 해 줘") and promise_hit("면 한 그릇 더 넣어 드릴게요")
    assert not promise_hit("더 정확한 서비스를 제공하겠습니다")


def test_excuses_are_rejected_but_promises_are_not(snapshot, make_ctx):
    reply = "배달앱 시스템 오류로 주문이 제대로 안 넘어온 것 같아요. 다음엔 꼭 확인할게요."
    fake = FakeClova(judged(), fixed("다음엔 꼭 확인할게요"), judged(), judged("배달앱 시스템 오류로 주문이 제대로 안 넘어온 것 같아요"))
    verdict_ = reply_critic.inspect(reply, make_ctx(fake), review_text="만두가 안 왔어요", has_complaint=True)
    assert verdict_.violations[0].kind == "BLAME" and fake.done()
    # 앞으로 하겠다는 말을 변명으로 옮겨 와도 코드가 뺀다
    reply = "오래 기다리시게 해서 죄송합니다. 바쁜 시간에도 늦지 않게 조리 순서를 다시 정하겠습니다."
    fake = FakeClova(judged(), fixed("조리 순서를 다시 정하겠습니다"), judged(), judged("바쁜 시간에도 늦지 않게 조리 순서를 다시 정하겠습니다"), judged(), unasked())
    assert reply_critic.inspect(reply, make_ctx(fake), review_text="배달이 늦었어요", has_complaint=True).ok


def test_quote_judge_survives_trace_failure(snapshot, make_ctx, monkeypatch):
    """실행 기록 DB 가 잠겨도 답글 검사(좁은 질문)는 답을 돌려준다 (H5)."""
    import sqlite3

    from Harness import trace

    def locked():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(trace, "_db", locked)
    reply = "배달앱 오류였던 것 같아요. 다음엔 확인할게요."
    fake = FakeClova(judged("배달앱 오류였던 것 같아요"))
    assert quote_judge.ask("excuse", reply, make_ctx(fake), "안 왔어요") == ["배달앱 오류였던 것 같아요"]


def test_quote_judge_tells_wrong_quotes_and_asks_again(snapshot, make_ctx):
    reply = "배달앱 오류였던 것 같아요. 다음엔 확인할게요."
    fake = FakeClova(judged("응대"), judged("배달앱 오류였던 것 같아요"))
    assert quote_judge.ask("excuse", reply, make_ctx(fake), "안 왔어요") == ["배달앱 오류였던 것 같아요"]
    assert "옮긴 부분 ['응대'] 가 답글에 글자 그대로 없어요" in fake.requests[1]["messages"][-1]["content"]
