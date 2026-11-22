"""포스터 그림 만들기 일감. 그림 하나에 30초~2분이 걸려서 뒤에서 만들고, 앱은 다 됐는지 묻는다.

한 번에 하나씩 만든다 (구독 사용량을 한꺼번에 쓰지 않게). 결과와 기록은 db/app_data/posters/<일감 id>.png / .json (git 에 올라가지 않는다).
서버를 다시 켜도 다 만든 그림은 남는다. 만들던 일감은 서버가 꺼지면 실패로 본다.
"""

import base64
import binascii
import io
import datetime as dt
import json
import re
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core import naver_place
from app.core.seoul_time import now_seoul
from app.data_pipeline import store_logo
from app.poster_ai import image_engine, prompt as prompt_builder
from app.poster_ai.situation import Situation

POSTER_DIR = Path(__file__).resolve().parents[2] / "db" / "app_data" / "posters"
MAX_PHOTOS = 3
MAX_UPLOAD = 8 * 1024 * 1024
DATA_URL = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", re.S)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="poster-ai")
_running: dict[str, dict] = {}
_guard = threading.Lock()


class PhotoError(ValueError):
    pass


def _meta_path(job_id: str) -> Path:
    return POSTER_DIR / f"{job_id}.json"


def image_path(job_id: str) -> Path | None:
    path = POSTER_DIR / f"{job_id}.png"
    return path if re.fullmatch(r"[0-9a-f]{32}", job_id) and path.exists() else None


def _save_meta(job: dict) -> None:
    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    _meta_path(job["job_id"]).write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")


def get(job_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return None
    with _guard:
        if job_id in _running:
            return dict(_running[job_id])
    path = _meta_path(job_id)
    if not path.exists():
        return None
    job = json.loads(path.read_text(encoding="utf-8"))
    if job["status"] == "RUNNING":  # 서버가 꺼지는 바람에 끝나지 못한 일감
        job.update(status="FAILED", error="서버가 다시 켜져서 멈췄어요. 다시 만들어 주세요")
    return job


def _photo_bytes(source: str) -> bytes:
    match = DATA_URL.match(source.strip())
    if match:
        try:
            raw = base64.b64decode(match.group(2))
        except (binascii.Error, ValueError):
            raise PhotoError("사진을 읽지 못했어요") from None
        if len(raw) > MAX_UPLOAD:
            raise PhotoError("8MB 보다 작은 사진으로 골라 주세요")
        return raw
    raw = naver_place._image(source)  # 네이버 사진(pstatic.net)만 받는다
    if not raw:
        raise PhotoError("사진을 받지 못했어요")
    return raw


def _normalized(raw: bytes, path: Path) -> Path:
    """그림 모델에 보낼 사진: 긴 변 1600 JPG 로 줄인다 (보내는 양을 줄이고, 파일 이름으로 종류를 알게)"""
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise PhotoError("사진을 읽지 못했어요") from None
    image = image.convert("RGB")
    image.thumbnail((1600, 1600))
    image.save(path, "JPEG", quality=90)
    return path


def start(situation: Situation, choice: prompt_builder.PosterChoice, photos: list[tuple[str, str]], plan_id: str) -> dict:
    """photos: [(사진 이름, 주소 또는 data URL)]. 사진을 먼저 받아 두고(실패하면 바로 알림) 그림은 뒤에서 만든다."""
    if not photos:
        raise PhotoError("사진을 하나 이상 골라 주세요")
    work = Path(tempfile.mkdtemp(prefix="dona-poster-in-"))
    files: list[Path] = []
    logo = store_logo.path_of(situation.store_id) if choice.has_logo else None
    if logo:
        files.append(logo)
    try:
        for i, (_, source) in enumerate(photos[:MAX_PHOTOS]):
            files.append(_normalized(_photo_bytes(source), work / f"photo-{i + 1}.jpg"))
    except Exception:
        shutil.rmtree(work, ignore_errors=True)  # 뒤에서 만들 일감이 없으니 여기서 지운다
        raise
    choice.has_logo = logo is not None
    choice.photo_labels = tuple(label for label, _ in photos[:MAX_PHOTOS])
    text = prompt_builder.build(situation, choice)
    job = {
        "job_id": uuid.uuid4().hex,
        "store_id": situation.store_id,
        "plan_id": plan_id,
        "status": "RUNNING",
        "created_at": now_seoul().isoformat(timespec="seconds"),
        "finished_at": None,
        "engine": image_engine.engine_status()["engine"],
        "headline": choice.headline,
        "line": choice.line,
        "extra": choice.extra,
        "style": choice.style,
        "prompt": text,
        "error": None,
    }
    with _guard:
        _running[job["job_id"]] = job
    _save_meta(job)
    _executor.submit(_run, job["job_id"], text, files, work)
    return dict(job)


def _run(job_id: str, text: str, files: list[Path], work: Path) -> None:
    with _guard:
        job = _running[job_id]
    try:
        raw = image_engine.generate(text, files)
        POSTER_DIR.mkdir(parents=True, exist_ok=True)
        (POSTER_DIR / f"{job_id}.png").write_bytes(image_engine.to_story(raw))
        job.update(status="DONE")
    except image_engine.PosterEngineError as error:
        job.update(status="FAILED", error=str(error))
    except Exception:  # 그림이 깨졌거나 예상 못 한 실패
        job.update(status="FAILED", error="그림을 만들지 못했어요. 다시 해 주세요")
    finally:
        job["finished_at"] = now_seoul().isoformat(timespec="seconds")
        _save_meta(job)
        with _guard:
            _running.pop(job_id, None)
        for path in work.glob("*"):
            path.unlink(missing_ok=True)
        work.rmdir()


def elapsed_seconds(job: dict) -> int:
    started = dt.datetime.fromisoformat(job["created_at"])
    ended = dt.datetime.fromisoformat(job["finished_at"]) if job.get("finished_at") else now_seoul()
    return max(0, round((ended - started).total_seconds()))
