"""HyperCLOVA X 리뷰 분류 (app/analysis/review/hcx_classifier.py). 실제로 호출하지 않고 가짜 응답으로 확인한다."""

import httpx
import pytest

from app.analysis.review import hcx_classifier
from app.analysis.review.hcx_classifier import (
    RATE_LIMIT_WAIT_SECONDS,
    classify_with_hcx,
    mask_personal_info,
    parse_answer,
)


def reply(content: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"status": {"code": "20000"}, "result": {"message": {"role": "assistant", "content": content}}})


class FakePost:
    """httpx.post 대신 넣는다. 미리 정한 응답(또는 예외)을 차례로 돌려주고, 보낸 요청 내용을 남긴다."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.bodies = []

    def __call__(self, url, *, headers, json, timeout):
        self.bodies.append(json)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setattr(hcx_classifier.settings, "clova_studio_api_key", "test-key")


GOOD = '{"sentiment": "NEGATIVE", "complaint_types": ["DELIVERY_DELAY"]}'


# ── 답 읽기 ──


def test_parse_plain_json():
    assert parse_answer(GOOD) == ("NEGATIVE", ["DELIVERY_DELAY"])


def test_parse_json_inside_code_block_and_text():
    assert parse_answer(f"답입니다.\n```json\n{GOOD}\n```") == ("NEGATIVE", ["DELIVERY_DELAY"])


@pytest.mark.parametrize("answer", [
    "",
    "JSON 이 아닌 답",
    '{"sentiment": "NEUTRAL", "complaint_types": []}',
    '{"sentiment": "NEGATIVE", "complaint_types": ["PRICE"]}',
    '{"sentiment": "NEGATIVE", "complaint_types": "TASTE"}',
    '{"sentiment": "NEGATIVE"}',
    '["NEGATIVE"]',
])
def test_parse_rejects_wrong_shape(answer):
    assert parse_answer(answer) is None


def test_parse_sorts_types_and_fixes_positive_with_complaints():
    answer = '{"sentiment": "POSITIVE", "complaint_types": ["SERVICE", "TASTE", "SERVICE"]}'
    assert parse_answer(answer) == ("MIXED", ["TASTE", "SERVICE"])


# ── 개인정보 가리기 ──


def test_mask_phone_and_mention():
    masked = mask_personal_info("@국수러버 님 010-1234-5678 로 연락 주세요. 01098765432")
    assert "010-1234-5678" not in masked and "01098765432" not in masked and "국수러버" not in masked


def test_masked_text_is_sent_with_prompt():
    post = FakePost(reply(GOOD))
    classify_with_hcx("늦게 왔어요 010-1234-5678", post=post)
    system, user = post.bodies[0]["messages"]
    assert system["role"] == "system" and "complaint_types" in system["content"][0]["text"]
    assert "010-1234-5678" not in user["content"][0]["text"]


# ── 호출과 다시 시도 ──


def test_first_good_answer_is_used():
    post = FakePost(reply(GOOD))
    assert classify_with_hcx("배달이 늦어요", post=post) == ("NEGATIVE", ["DELIVERY_DELAY"])
    assert len(post.bodies) == 1


def test_wrong_answer_is_asked_once_more():
    post = FakePost(reply("모르겠어요"), reply(GOOD))
    assert classify_with_hcx("배달이 늦어요", post=post) == ("NEGATIVE", ["DELIVERY_DELAY"])
    assert len(post.bodies) == 2


def test_two_wrong_answers_give_none():
    post = FakePost(reply("모르겠어요"), reply("여전히 모르겠어요"))
    assert classify_with_hcx("배달이 늦어요", post=post) is None


def test_rate_limit_waits_then_retries():
    waited = []
    post = FakePost(reply("", status=429), reply(GOOD))
    assert classify_with_hcx("배달이 늦어요", post=post, sleep=waited.append) == ("NEGATIVE", ["DELIVERY_DELAY"])
    assert waited == [RATE_LIMIT_WAIT_SECONDS]


def test_connection_error_then_retry():
    post = FakePost(httpx.ConnectError("연결 실패"), reply(GOOD))
    assert classify_with_hcx("배달이 늦어요", post=post) == ("NEGATIVE", ["DELIVERY_DELAY"])


def test_server_errors_give_none():
    post = FakePost(reply("", status=500), reply("", status=500))
    assert classify_with_hcx("배달이 늦어요", post=post) is None


def test_no_api_key_skips_call(monkeypatch):
    monkeypatch.setattr(hcx_classifier.settings, "clova_studio_api_key", "")
    post = FakePost()
    assert classify_with_hcx("배달이 늦어요", post=post) is None
    assert post.bodies == []
