"""포스터 그림 만들기.

openai (기본): OpenAI 이미지 API(OPENAI_API_KEY)에 프롬프트와 첨부 그림(로고, 메뉴 사진)을 보낸다. 첨부가 있으면 /v1/images/edits
    (첨부 그림을 참고로 그린다), 없으면 /v1/images/generations. 모델·품질·크기는 POSTER_OPENAI_MODEL·QUALITY·SIZE.
    그림 한 장마다 요금이 든다. 응답의 usage 로 값을 셈해 로그에 남긴다 (last_cost).
codex: 이 컴퓨터에서 ChatGPT 계정으로 로그인한 Codex CLI(`codex login`)에 프롬프트와 첨부 그림을 주고,
    Codex 의 그림 만들기 도구(gpt-image-2)로 만든다. 구독제 사용량으로 그려서 API 키가 필요 없다 (데모용).
    만든 그림은 Codex 가 $CODEX_HOME/generated_images/<대화 id>/ 에 둔다. 그 파일을 읽는다.
mock: 받은 사진과 로고를 합쳐 스토리 크기 그림만 만든다 (시험용, 글자 없음).

만든 그림은 to_story 로 인스타 스토리 크기(1080 × 1920)에 맞춘다. 비율이 다르면 같은 그림을 흐리게 깔고 가운데에 그대로 놓는다.
"""

import base64
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageFilter

from app.core.config import settings

logger = logging.getLogger(__name__)

STORY = (1080, 1920)


class PosterEngineError(RuntimeError):
    """그림을 만들지 못했다. 글은 사장님께 그대로 보여 준다."""


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


OPENAI_URL = "https://api.openai.com/v1/images"
# OpenAI 이미지 값 (1백만 토큰당 달러, 2026-11-18 developers.openai.com/api/docs/pricing). 모르는 모델이면 값을 세지 않는다
OPENAI_PRICES = {
    "gpt-image-2": {"text_in": 5.0, "image_in": 8.0, "image_out": 30.0},
    "gpt-image-1.5": {"text_in": 5.0, "image_in": 8.0, "image_out": 32.0},
    "gpt-image-1-mini": {"text_in": 2.0, "image_in": 2.5, "image_out": 8.0},
}
CODEX_ONLY = "Use the built-in image generation tool"  # prompt.build 의 Codex 에게만 하는 말 (이미지 API 에는 빼고 보낸다)
post = httpx.post  # 테스트에서 가짜를 넣는다
last_cost: dict | None = None  # 마지막 그림의 usage 와 달러 값 (로그·개발자 확인용)


def engine_status() -> dict:
    """{"engine", "ready", "note"}: 그림을 만들 수 있는지 (OpenAI 키, Codex 로그인 확인)"""
    if settings.poster_image_engine == "mock":
        return {"engine": "mock", "ready": True, "note": "시험용 그림 (글자 없음)"}
    if settings.poster_image_engine == "openai":
        if not settings.openai_api_key:
            return {"engine": "openai", "ready": False, "note": "OPENAI_API_KEY 가 비어 있어요"}
        return {"engine": "openai", "ready": True,
                "note": f"OpenAI {settings.poster_openai_model} ({settings.poster_openai_quality}, {settings.poster_openai_size})로 그려요"}
    binary = shutil.which(settings.codex_bin) or (settings.codex_bin if Path(settings.codex_bin).exists() else None)
    if not binary:
        return {"engine": "codex", "ready": False, "note": "이 컴퓨터에 Codex CLI 가 없어요"}
    try:
        out = subprocess.run([binary, "login", "status"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return {"engine": "codex", "ready": False, "note": "Codex CLI 를 실행하지 못했어요"}
    text = (out.stdout + out.stderr).strip()
    if "ChatGPT" in text and "Logged in" in text:
        return {"engine": "codex", "ready": True, "note": "ChatGPT 계정(구독제)으로 그려요"}
    return {"engine": "codex", "ready": False, "note": "ChatGPT 계정으로 로그인해 주세요 (터미널에서 codex login)"}


def to_story(raw: bytes) -> bytes:
    """인스타 스토리 1080 × 1920 PNG 로 맞춘다"""
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = STORY
    if abs(image.width / image.height - w / h) < 0.01:
        fitted = image.resize(STORY, Image.LANCZOS)
    else:
        cover = max(w / image.width, h / image.height)
        back = image.resize((round(image.width * cover), round(image.height * cover)), Image.LANCZOS)
        left, top = (back.width - w) // 2, (back.height - h) // 2
        fitted = back.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(40))
        fitted = Image.blend(fitted, Image.new("RGB", STORY, (20, 14, 10)), 0.25)
        contain = min(w / image.width, h / image.height)
        front = image.resize((round(image.width * contain), round(image.height * contain)), Image.LANCZOS)
        fitted.paste(front, ((w - front.width) // 2, (h - front.height) // 2))
    out = io.BytesIO()
    fitted.save(out, "PNG", optimize=True)
    return out.getvalue()


def generate(prompt: str, images: list[Path]) -> bytes:
    """프롬프트와 첨부 그림으로 포스터 그림(원본 크기 PNG/JPG 바이트)을 만든다"""
    if settings.poster_image_engine == "mock":
        return _mock(images)
    if settings.poster_image_engine == "openai":
        return _openai(prompt, images)
    return _codex(prompt, images)


def cost_of(model: str, usage: dict | None) -> float | None:
    """응답 usage → 달러. {input_tokens_details: {text_tokens, image_tokens}, output_tokens}"""
    price = OPENAI_PRICES.get(model)
    if not price or not usage:
        return None
    details = usage.get("input_tokens_details") or {}
    text_in = details.get("text_tokens", usage.get("input_tokens", 0) if not details else 0)
    image_in = details.get("image_tokens", 0)
    return (text_in * price["text_in"] + image_in * price["image_in"] + usage.get("output_tokens", 0) * price["image_out"]) / 1_000_000


def _openai(prompt: str, images: list[Path]) -> bytes:
    global last_cost
    status = engine_status()
    if not status["ready"]:
        raise PosterEngineError(status["note"])
    model = settings.poster_openai_model
    text = "\n".join(line for line in prompt.splitlines() if not line.startswith(CODEX_ONLY))
    fields = {"model": model, "prompt": text, "size": settings.poster_openai_size, "quality": settings.poster_openai_quality, "n": "1"}
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        if images:  # 첨부 그림을 참고로 그린다 (로고는 그대로, 메뉴는 같은 음식으로)
            files = [("image[]", (p.name, p.read_bytes(), "image/png" if p.suffix.lower() == ".png" else "image/jpeg")) for p in images]
            response = post(f"{OPENAI_URL}/edits", headers=headers, data=fields, files=files, timeout=settings.poster_image_timeout)
        else:
            response = post(f"{OPENAI_URL}/generations", headers=headers, json=fields, timeout=settings.poster_image_timeout)
    except httpx.TimeoutException:
        raise PosterEngineError("그림이 너무 오래 걸려요. 잠시 뒤 다시 해 주세요") from None
    except httpx.HTTPError as error:
        raise PosterEngineError("OpenAI 에 닿지 못했어요. 잠시 뒤 다시 해 주세요") from error
    if response.status_code != 200:
        try:
            error = response.json().get("error") or {}
        except ValueError:
            error = {}
        logger.warning("OpenAI 그림 실패 %s: %s", response.status_code, str(error.get("message") or response.text)[:300])
        if response.status_code == 401:
            raise PosterEngineError("OpenAI API 키가 맞지 않아요")
        if response.status_code == 429:
            raise PosterEngineError("OpenAI 사용량 한도에 걸렸어요. 잠시 뒤 다시 해 주세요")
        if error.get("code") == "moderation_blocked":
            raise PosterEngineError("이 내용으로는 그림을 만들 수 없어요. 문구를 바꿔 주세요")
        raise PosterEngineError("그림을 만들지 못했어요. 다시 해 주세요")
    body = response.json()
    try:
        raw = base64.b64decode(body["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise PosterEngineError("그림을 만들지 못했어요. 다시 해 주세요") from None
    usage = body.get("usage")
    last_cost = {"model": model, "quality": settings.poster_openai_quality, "size": settings.poster_openai_size,
                 "usage": usage, "usd": cost_of(model, usage)}
    logger.info("OpenAI 그림 %s %s %s: usage %s, 약 $%s", model, settings.poster_openai_quality, settings.poster_openai_size,
                usage, f"{last_cost['usd']:.4f}" if last_cost["usd"] is not None else "?")
    return raw


def _mock(images: list[Path]) -> bytes:
    canvas = Image.new("RGB", (1024, 1536), (43, 26, 15))
    photos = [Image.open(p).convert("RGBA") for p in images]
    if photos:
        main = photos[-1]
        main.thumbnail((1024, 1100))
        canvas.paste(main, ((1024 - main.width) // 2, 200), main)
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()


def _codex(prompt: str, images: list[Path]) -> bytes:
    status = engine_status()
    if not status["ready"]:
        raise PosterEngineError(status["note"])
    binary = shutil.which(settings.codex_bin) or settings.codex_bin
    with tempfile.TemporaryDirectory(prefix="dona-poster-") as work:
        command = [binary, "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "-C", work]
        for image in images:
            command += ["-i", str(image)]
        command.append("-")  # 프롬프트는 표준 입력으로 (-i 가 여러 개라 뒤 글자를 그림으로 읽지 않게)
        try:
            run = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=settings.poster_image_timeout)
        except subprocess.TimeoutExpired:
            raise PosterEngineError("그림이 너무 오래 걸려요. 잠시 뒤 다시 해 주세요") from None
        except OSError as error:
            raise PosterEngineError("Codex CLI 를 실행하지 못했어요") from error
    thread_id, message, failure = None, "", ""
    for row in run.stdout.splitlines():
        try:
            event = json.loads(row)
        except ValueError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        item = event.get("item") or {}
        if item.get("type") == "agent_message":
            message = item.get("text") or message
        if event.get("type") in ("turn.failed", "error"):
            failure = json.dumps(event, ensure_ascii=False)[:300]
    path = _latest_image(thread_id) or _path_in(message)
    if path is None:
        logger.warning("Codex 그림 없음 (exit %s): %s %s %s", run.returncode, failure, message[:200], run.stderr[-300:])
        if "usage" in (failure + run.stderr).lower() or "limit" in (failure + run.stderr).lower():
            raise PosterEngineError("ChatGPT 사용량을 다 썼어요. 잠시 뒤 다시 해 주세요")
        raise PosterEngineError("그림을 만들지 못했어요. 다시 해 주세요")
    return path.read_bytes()


def _latest_image(thread_id: str | None) -> Path | None:
    if not thread_id:
        return None
    folder = codex_home() / "generated_images" / thread_id
    files = sorted((p for p in folder.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    return files[-1] if files else None


def _path_in(message: str) -> Path | None:
    text = message.strip().strip("`")
    path = Path(text)
    home = codex_home() / "generated_images"
    return path if text and path.is_file() and home in path.parents else None
