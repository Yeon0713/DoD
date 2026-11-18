"""report.ErrorLogPost / http_error_row: 실패 응답의 요청 모양만 남긴다 (intent·noise·voice·reply 공통)."""

import json

import httpx

from Harness.evals import report


def reply(status):
    return lambda url, **kwargs: httpx.Response(status, json={"status": {"code": str(status)}}, request=httpx.Request("POST", url))


BODY = {"messages": [{"role": "system", "content": "비밀 프롬프트"}, {"role": "user", "content": "사장님 말"},
                     {"role": "assistant", "content": "", "toolCalls": [{"id": "1"}]}],
        "tools": [{"type": "function", "function": {"name": "submit", "parameters": {
            "type": "object", "properties": {"a": {"type": "string", "enum": ["x", "y"]}, "b": {"type": "string"}}, "required": ["a"]}}}],
        "toolChoice": "auto", "maxTokens": 1024, "temperature": 0}


def test_only_failures_except_429_are_written(tmp_path):
    log = tmp_path / "http_errors.jsonl"
    for status in (200, 429):
        report.ErrorLogPost(reply(status), log)("https://x/v3/chat-completions/HCX-005", json=BODY)
    assert not log.exists()
    post = report.ErrorLogPost(reply(500), log)
    post.context = {"case_id": "c1"}
    post("https://x/v3/chat-completions/HCX-005", json=BODY)
    (row,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert row["case_id"] == "c1" and row["model"] == "HCX-005" and row["status"] == 500 and post.count == 1
    assert row["roles"] == ["system", "user", "assistant+toolCalls"] and row["tool_choice"] == "auto"
    assert row["tool_shapes"]["submit"] == {"params": {"a": {"type": "string", "enum": 2}, "b": {"type": "string"}}, "required": ["a"]}
    assert row["other"] == {"maxTokens": 1024, "temperature": 0} and row["seconds"] is not None
    assert "비밀 프롬프트" not in log.read_text(encoding="utf-8") and "사장님 말" not in log.read_text(encoding="utf-8")


def test_should_log():
    assert [report.should_log_http_error(s) for s in (200, 400, 429, 503)] == [False, True, False, True]
