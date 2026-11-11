"""키워드 규칙 리뷰 분류 (app/analysis/review/keyword_rules.py).

정답은 tests/analysis/sample_inputs/review_label_cases.example.json 30건과,
목업 생성기(db/mock/generate.py)의 문장 목록으로 정답을 알 수 있는 db/mock/out/<매장>/reviews.csv 이다.
"""

import csv
import json
import re
from pathlib import Path

import pytest

from app.analysis.review.complaint_groups import groups_of, is_quick
from app.analysis.review.keyword_rules import classify_by_keywords

HERE = Path(__file__).parent
CASES = json.loads((HERE / "sample_inputs" / "review_label_cases.example.json").read_text(encoding="utf-8"))["cases"]
PLANNER_INPUTS = HERE.parent / "planner" / "sample_inputs" / "demo_week_inputs.example.json"
MOCK_OUT = HERE.parents[1] / "db" / "mock" / "out"
# 생성기 리뷰 종류 → 정답 불만 유형. mixed(칭찬 + 아쉬움)는 문장마다 달라 검사에서 뺀다.
EXPECTED_BY_KIND = {
    "positive": [], "taste": ["TASTE"], "delay": ["DELIVERY_DELAY"],
    "portion": ["PORTION"], "service": ["SERVICE"], "hygiene": ["HYGIENE"], "mixed": None,
}


def test_all_complaint_cases_are_quick():
    """정답에 불만 유형이 있는 리뷰는 키워드 규칙만으로도 모두 빠른 응대 대상이 된다."""
    missed = [
        case["review_id"]
        for case in CASES
        if case["expected"]["complaint_types"] and not is_quick(groups_of(classify_by_keywords(case["text"])[1]))
    ]
    assert not missed, f"빠른 응대로 잡지 못한 불만 리뷰: {missed}"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["review_id"])
def test_complaint_types_match_cases(case):
    _, types = classify_by_keywords(case["text"])
    assert types == case["expected"]["complaint_types"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["review_id"])
def test_sentiment_matches_cases(case):
    sentiment, _ = classify_by_keywords(case["text"])
    assert sentiment == case["expected"]["sentiment"]


def test_demo_cases_use_same_text_as_planner_inputs():
    """rv_ 정답은 계획 엔진 테스트 입력의 리뷰 본문과 같은 문장이다."""
    planner_texts = {r["review_id"]: r["text"] for r in json.loads(PLANNER_INPUTS.read_text(encoding="utf-8"))["reviews"]}
    for case in CASES:
        if case["review_id"].startswith("rv_"):
            assert planner_texts[case["review_id"]] == case["text"], case["review_id"]


@pytest.mark.parametrize("text", [
    "늦지 않게 왔어요.",
    "양이 적지 않아요.",
    "사진이랑 다르지 않아요.",
    "위생적이고 깔끔해요.",
    "사장님이 친절해요.",
    "양도 많고 가성비 최고입니다.",
])
def test_negations_and_praise_are_not_complaints(text):
    assert classify_by_keywords(text)[1] == []


@pytest.mark.parametrize("store_id", ["s001", "s002", "s003"])
def test_mock_reviews_follow_generator_templates(store_id):
    """목업 리뷰는 그 매장의 생성기 문장 목록(review_pools) 중 하나로 만들어졌다. 그 목록이 정답이다."""
    from db.mock.generate import STORES, review_pools

    reviews_csv = MOCK_OUT / store_id / "reviews.csv"
    if not reviews_csv.exists():
        pytest.skip("목업 리뷰 CSV 가 없다")

    def template_re(template: str) -> re.Pattern:
        return re.compile(re.escape(template).replace(re.escape("{menu}"), ".+").replace(re.escape("{side}"), ".+"))

    cfg = next(c for c in STORES if c["store"]["store_id"] == store_id)
    expected_by_template = [(template_re(t), EXPECTED_BY_KIND[kind])
                            for kind, templates in review_pools(cfg).items() for t in templates]

    with reviews_csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    wrong = []
    for row in rows:
        expected = next(types for pattern, types in expected_by_template if pattern.fullmatch(row["content"]))
        if expected is not None and classify_by_keywords(row["content"])[1] != expected:
            wrong.append(row["content"])
    assert not wrong, f"{store_id} 목업 리뷰 {len(rows)}건 중 틀린 것: {wrong}"
