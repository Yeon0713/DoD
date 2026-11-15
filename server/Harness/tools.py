"""도구 정의 도우미와 도구 결과 직렬화.

도구 결과는 tool 메시지의 content(문자열)로 보낸다. json.dumps(ensure_ascii=False) 로 바꾸고 (파이썬 str(dict) 는 쓰지 않는다),
전화번호와 @닉네임을 가리고, 너무 길면 자른다.
"""

import json
from pathlib import Path

from app.analysis.review.hcx_classifier import mask_personal_info

MAX_RESULT_CHARS = 3000
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, store: dict) -> str:
    """Harness/prompts/<name> 을 읽어 {가게이름}, {업종} 을 채운다. 매번 읽으므로 파일을 고치면 바로 반영된다."""
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    return text.replace("{가게이름}", store["name"]).replace("{업종}", store["category"])


def string(description: str, enum: list[str] | None = None) -> dict:
    schema = {"type": "string", "description": description}
    if enum:
        schema["enum"] = enum
    return schema


def integer(description: str) -> dict:
    return {"type": "integer", "description": description}


def array(items: dict, description: str) -> dict:
    return {"type": "array", "items": items, "description": description}


def obj(properties: dict, required: list[str] | None = None, description: str | None = None) -> dict:
    schema = {"type": "object", "properties": properties, "required": list(properties) if required is None else required}
    if description:
        schema["description"] = description
    return schema


NO_ARGS = obj({})


def to_content(result: object) -> str:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    text = mask_personal_info(text)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "…(잘림)"
    return text
