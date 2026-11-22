"""CLOVA Studio v3 Chat Completions 를 function calling(tools)으로 부른다.

기존 app/core/clova.py 의 ask() 는 system + user 한 번만 보내므로, 대화 목록과 도구를 보내는 함수를 여기 따로 둔다.
공식 문서: https://api.ncloud-docs.com/docs/clovastudio-chatcompletionsv3-fc

지키는 제약
  - maxTokens 는 1024 이상 (function calling 요청의 하한)
  - system 메시지는 요청당 1개. 부르는 쪽(runner)이 맨 앞에 하나만 둔다
  - 메시지 content 는 문자열로 보낸다 (문서 예시와 같은 모양)
  - 응답 toolCalls[].function.arguments 는 JSON 객체로 온다. 문자열로 오면 JSON 으로 읽어 본다
  - repetitionPenalty / stop 은 문서 표기가 섞여 있어 보내지 않는다

호출마다 기존 clova_usage_log.record_call 로 기록을 남긴다 (feature 는 "agent:<에이전트 이름>").

평가 심판(Harness/evals/judge.py)이 쓰는 선택 인자. 넘기지 않으면 예전과 똑같이 보낸다.
  - model: 주소에 넣을 모델 (기본 settings.clova_studio_model)
  - thinking_effort: 추론 모델(HCX-007)의 thinking.effort. "none" 이면 추론을 끈 채 도구를 쓴다.
    그 밖의 값이면 추론을 켜는 요청이라 도구를 함께 보낼 수 없다(tools 는 비워야 한다).
  - log_prefix: 사용 기록 feature 앞에 붙이는 말 (기본 "agent:")

추론 모델(REASONING_MODELS, 지금은 HCX-007) 요청 모양 (CLOVA Studio 추론 문서)
  - maxTokens 를 쓸 수 없다. effort 와 상관없이 maxCompletionTokens(추론 + 답, 최대 32,768)를 보낸다.
    도구를 보내는 요청은 function calling 하한(1024) 이상으로 둔다.
  - thinking 을 빼면 기본 effort 가 low(추론 켜짐)라 도구와 같이 보내면 400 이다. 그래서 도구를 보낼 때는
    thinking.effort 를 언제나 "none" 으로 적는다.
  - HCX-005 등 다른 모델의 요청 모양은 예전과 같다 (maxTokens, thinking 없음).
"""

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

import httpx

from app.core import clova_usage_log
from app.core.clova import Post
from app.core.config import settings
from Harness import limiter

logger = logging.getLogger(__name__)

MIN_MAX_TOKENS = 1024
MIN_CALL_SECONDS = 0.5  # 자리를 기다린 뒤 남은 제한 시간의 최소값 (runner.MIN_CALL_SECONDS 와 같게)
MAX_COMPLETION_TOKENS = 32768  # 추론 모델 한도 (추론 + 답)
REASONING_MODELS = ("HCX-007",)  # maxTokens 대신 maxCompletionTokens 를 쓰는 모델 (이름이 이것으로 시작하면)

_local = threading.local()  # 이 스레드가 마지막으로 남긴 사용 기록 id


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None  # 출력 토큰 중 추론에 쓴 수. 추론 글(thinkingContent)은 읽지 않는다

    def as_assistant_message(self) -> dict:
        """다음 요청에 그대로 붙일 assistant 메시지 (toolCalls 포함)."""
        message: dict = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["toolCalls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return message


def is_reasoning_model(model: str) -> bool:
    return model.startswith(REASONING_MODELS)


def is_enabled() -> bool:
    return bool(settings.clova_studio_api_key)


def _arguments(raw) -> dict:
    """arguments 는 객체가 정상이다. 문자열이면 JSON 으로 읽고, 읽을 수 없으면 빈 객체."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def parse_reply(response: httpx.Response) -> ToolReply | None:
    """v3 응답에서 답 글자, 도구 호출, 끝난 이유, 토큰 수를 꺼낸다. 모양이 다르면 None."""
    try:
        result = response.json()["result"]
        message = result["message"]
    except (ValueError, KeyError, TypeError):
        return None
    content = message.get("content") or ""
    if isinstance(content, list):  # 글자 조각 목록으로 올 때
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    calls = []
    for raw in message.get("toolCalls") or []:
        function = raw.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        calls.append(ToolCall(id=str(raw.get("id") or uuid.uuid4().hex), name=name, arguments=_arguments(function.get("arguments"))))
    usage = result.get("usage") or {}
    return ToolReply(
        content=content if isinstance(content, str) else "",
        tool_calls=calls,
        finish_reason=result.get("finishReason") or ("tool_calls" if calls else "stop"),
        input_tokens=usage.get("promptTokens"),
        output_tokens=usage.get("completionTokens"),
        thinking_tokens=(usage.get("completionTokensDetails") or {}).get("thinkingTokens"),
    )


def _last_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("content"):
            return str(message["content"])
    return ""


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    *,
    feature: str,
    store_id: str | None,
    tool_choice: str | dict = "auto",
    max_tokens: int = MIN_MAX_TOKENS,
    temperature: float = 0.3,
    timeout: float = 20,
    post: Post = httpx.post,
    alt_tools: list[dict] | None = None,
    model: str | None = None,
    thinking_effort: str | None = None,
    log_prefix: str = "agent:",
    retry: bool = True,
) -> ToolReply | None:
    """대화와 도구 목록으로 한 번 묻는다. 키가 없거나, 연결이 실패하거나, 200 이 아니면(429 는 한 번 기다렸다 다시) None.

    도구를 강제한 요청이 400(40009 "Unsupported function")이면 조건을 바꿔 다시 묻는다.
    실제 CLOVA 에서 같은 입력은 매번 같은 곳에서 실패했고(temperature 0), 그대로 다시 묻거나 temperature 를 올려도 소용없었다.
    잘 들은 것은 (1) "반드시 ○○ 도구로 내" 한 줄을 덧붙이기, (2) 결과 모양이 다른 도구(alt_tools, 이름은 같게)로 묻기였다.
    예전에는 auto 로 다시 물었는데, 그러면 모델이 글로 답해 쓸 수 없었다.
    retry=False 면 429·강제 제출 400 에 다시 묻지 않고 None (시간 예산이 빠듯한 음성 뜻 판정, Budget.strict).
    """
    if not is_enabled():
        return None
    model = model or settings.clova_studio_model
    reasoning = thinking_effort not in (None, "none")
    if reasoning and tools:
        raise ValueError("추론(thinking)을 켠 요청에는 도구를 보낼 수 없어요")
    body = {
        "messages": messages,
        "tools": tools,
        "toolChoice": tool_choice,
        "maxTokens": max(max_tokens, MIN_MAX_TOKENS),
        "temperature": temperature,
        "topP": 0.8,
    }
    if is_reasoning_model(model) or reasoning:
        limit = max(max_tokens, MIN_MAX_TOKENS) if tools else max_tokens
        del body["maxTokens"]
        body["maxCompletionTokens"] = min(limit, MAX_COMPLETION_TOKENS)
    if is_reasoning_model(model) and tools:
        body["thinking"] = {"effort": "none"}  # 빼면 기본이 추론 켜짐(low)이라 도구와 같이 쓸 수 없다
    elif thinking_effort is not None:
        body["thinking"] = {"effort": thinking_effort}
    if reasoning or (is_reasoning_model(model) and not tools):
        del body["tools"], body["toolChoice"]
    feature = f"{log_prefix}{feature}"
    request_text = _last_text(messages)
    for attempt in range(limiter.RATE_LIMIT_RETRIES + 1):
        started = time.perf_counter()
        response = _post(post, body, timeout, model, wait=None if retry else timeout)
        if response is None:
            _log(feature, model, store_id, started, "connection_error", None, None, request_text)
            return None
        if response.status_code == 429 and retry and attempt < limiter.RATE_LIMIT_RETRIES:
            _log(feature, model, store_id, started, "http_error", 429, None, request_text)
            limiter.wait_after_429(response.headers)  # 헤더의 다시 부를 때를 따른다 (없으면 RATE_LIMIT_WAIT_SECONDS)
            continue
        if response.status_code == 400 and retry and body.get("toolChoice", "auto") != "auto":
            name = body["toolChoice"]["function"]["name"]
            nudge = {"role": "user", "content": f"답은 반드시 {name} 도구로 내."}
            retries = [{**body, "messages": [*messages, nudge]}]
            if alt_tools:
                retries.append({**body, "tools": alt_tools})
            for retry in retries:
                logger.warning("CLOVA(도구) 강제 호출 400, 조건을 바꿔 다시 묻는다: %s", response.text[:200])
                _log(feature, model, store_id, started, "http_error", 400, None, request_text)
                started = time.perf_counter()
                response = _post(post, retry, timeout, model)
                if response is None:
                    _log(feature, model, store_id, started, "connection_error", None, None, request_text)
                    return None
                if response.status_code != 400:
                    break
        if response.status_code != 200:
            logger.warning("CLOVA(도구) 응답 %s: %s", response.status_code, response.text[:300])
            _log(feature, model, store_id, started, "http_error", response.status_code, None, request_text)
            return None
        reply = parse_reply(response)
        _log(feature, model, store_id, started, "ok" if reply else "bad_shape", 200, reply, request_text)
        return reply
    return None


def _post(post: Post, body: dict, timeout: float, model: str, wait: float | None = None) -> httpx.Response | None:
    """자리 하나를 잡고 보낸다. 연결이 실패하면 None.
    wait 가 있으면(엄격한 예산) 자리를 그만큼만 기다리고 못 잡으면 None, 잡으면 기다린 만큼 제한 시간에서 뺀다 (H4)."""
    try:
        with limiter.slot(wait) as waited:
            if wait is not None and waited:
                timeout = max(MIN_CALL_SECONDS, timeout - waited)
            return post(
                # .env 의 주소 끝에 '/' 가 있으면 '…com//v3/…' 가 되어 모든 요청이 400 이다 (2026-11-17 실제로 겪음)
                f"{settings.clova_studio_base_url.rstrip('/')}/v3/chat-completions/{model}",
                headers={
                    "Authorization": f"Bearer {settings.clova_studio_api_key}",
                    "Content-Type": "application/json",
                    "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
                },
                json=body,
                timeout=timeout,
            )
    except limiter.SlotBusy:
        logger.warning("CLOVA(도구) 자리를 %.1f초 안에 잡지 못했어요", wait)
        return None
    except httpx.HTTPError as error:
        logger.warning("CLOVA(도구) 연결 실패: %s", error)
        return None


def _log(feature: str, model: str, store_id: str | None, started: float, status: str, http_status: int | None,
         reply: ToolReply | None, request_text: str) -> None:
    answer = None
    if reply is not None:
        answer = reply.content or json.dumps(
            [{"name": c.name, "arguments": c.arguments} for c in reply.tool_calls], ensure_ascii=False
        )
    try:
        _local.last_call_id = clova_usage_log.record_call(
            feature=feature,
            model=model,
            store_id=store_id,
            input_tokens=reply.input_tokens if reply else None,
            output_tokens=reply.output_tokens if reply else None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            status=status,
            http_status=http_status,
            request_text=request_text,
            answer_text=answer,
        )
    except Exception:  # 기록이 실패해도 답은 그대로 쓴다
        _local.last_call_id = None
        logger.exception("CLOVA(도구) 사용 기록 실패")


def last_call_id() -> int | None:
    """이 스레드에서 마지막으로 부른 CLOVA(도구) 기록 id."""
    return getattr(_local, "last_call_id", None)


def mark_verdict(call_id: int | None, accepted: bool, reason: str | None) -> None:
    """사용 기록 call_id 에 통과/버림을 붙인다 (개발자 대시보드 'AI 품질').

    기존 clova_usage_log.set_verdict 는 '이 스레드의 마지막 기록'에 붙이는데, 검사 도중 LLM 검토가 CLOVA 를
    한 번 더 부르면 마지막 기록이 바뀐다. 그래서 기록 id 를 기억해 두었다가 그 기록을 마지막으로 되돌린 뒤 붙인다.
    (clova_usage_log 를 고치지 않으려고 그 모듈의 스레드 저장소를 직접 쓴다)
    """
    if call_id is None:
        return
    try:
        clova_usage_log._local.last_id = call_id
        clova_usage_log.set_verdict(accepted, reason)
    except Exception:
        logger.exception("CLOVA(도구) 판정 기록 실패")
