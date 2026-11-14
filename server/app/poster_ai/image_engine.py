"""포스터 그림 만들기.

codex (기본): 이 컴퓨터에서 ChatGPT 계정으로 로그인한 Codex CLI(`codex login`)에 프롬프트와 첨부 그림(로고, 메뉴 사진)을 주고,
    Codex 의 그림 만들기 도구(gpt-image-2)로 만든다. 구독제 사용량으로 그려서 API 키가 필요 없다 (데모용. 나중에 OpenAI API 로 옮긴다).
    만든 그림은 Codex 가 $CODEX_HOME/generated_images/<대화 id>/ 에 둔다. 그 파일을 읽는다.
mock: 받은 사진과 로고를 합쳐 스토리 크기 그림만 만든다 (시험용, 글자 없음).

만든 그림은 to_story 로 인스타 스토리 크기(1080 × 1920)에 맞춘다. 비율이 다르면 같은 그림을 흐리게 깔고 가운데에 그대로 놓는다.
"""

import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter

from app.core.config import settings

logger = logging.getLogger(__name__)

STORY = (1080, 1920)


class PosterEngineError(RuntimeError):
    """그림을 만들지 못했다. 글은 사장님께 그대로 보여 준다."""


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def engine_status() -> dict:
    """{"engine", "ready", "note"}: 그림을 만들 수 있는지 (Codex 로그인 확인)"""
    if settings.poster_image_engine == "mock":
        return {"engine": "mock", "ready": True, "note": "시험용 그림 (글자 없음)"}
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
    return _codex(prompt, images)


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
