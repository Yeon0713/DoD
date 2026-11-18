"""답글 유사도 측정(diversity_eval)의 측정 함수와 측정 데이터. CLOVA 없이 돈다."""

from Harness import diversity_eval as de
from Harness.agents import reply_agent
from Harness.spec import Proposal, RunContext
from Harness.tests.fakes import NOW


def test_같은_답글은_유사도_1_다른_답글은_낮다():
    same = "국물이 짜셨다니 죄송합니다. 간을 다시 맞추겠습니다."
    report = de.similarity_report([same, same])
    assert report["avg_similarity"] == 1.0

    other = de.similarity_report([same, "포장까지 꼼꼼하게 봐 주셔서 고마워요!"])
    assert other["avg_similarity"] < 0.1


def test_같은_시작과_끝과_표현을_센다():
    texts = [
        "정말 죄송합니다. 국물 간을 다시 맞추겠습니다. 더 신경 쓰겠습니다.",
        "정말 죄송합니다! 배달 순서를 살피겠습니다. 더 신경 쓰겠습니다.",
        "맛있게 드셔 주셔서 감사해요. 또 찾아 주세요.",
    ]
    report = de.similarity_report(texts)
    assert report["openings"] == [["정말 죄송합니다", 2]]
    assert report["endings"] == [["신경 쓰겠습니다", 2]]
    assert ["정말 죄송합니다", 2] in report["common_phrases"]
    assert report["top_pairs"][0]["a"] in texts[:2] and report["top_pairs"][0]["b"] in texts[:2]


def test_측정용_리뷰는_모두_답글_할_일로_이어진다():
    snapshot = de.make_snapshot()
    ctx = RunContext(snapshot=snapshot, now=NOW)
    assert len(snapshot.plan.plan_items) == len(de.REVIEWS)
    for item, review in zip(snapshot.plan.plan_items, de.REVIEWS):
        task = reply_agent.task_for_plan_item(item, ctx)
        found = reply_agent.find_review(ctx, task["review_id"])
        assert found is not None and found.text == review[2]


def test_바퀴마다_따로_재고_출처를_센다():
    def fake_draft(item, ctx):
        text = "정말 죄송합니다. 다시 살피겠습니다." if item.basis.ref_id.startswith("n") else None
        return Proposal("reply_agent", item.plan_id, {"text": text}, "AGENT", "x") if text else None

    results = de.collect(rounds=2, workers=2, draft=fake_draft)
    summary = de.summarize(results)
    assert len(summary["rounds"]) == 2
    assert summary["rounds"][0]["count"] == 5  # 불만 리뷰 5건만 답글이 나옴
    assert summary["avg_similarity"] == 1.0
    assert summary["sources"] == {"AGENT": 10, "NONE": 14}
