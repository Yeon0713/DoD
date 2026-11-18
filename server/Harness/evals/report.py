"""평가 실행 하나의 결과 폴더와 result.json.

  run = report.start("reply", config={...}, systems=["A", "B"])
  ... run.add_metric(metrics.metric(...)); run.add_case({...})
  run.finish()   # result.json 을 쓰고 경로를 돌려준다

start() 가 하는 일
  - db/app_data/harness_eval/<suite>-<YYYYMMDD-HHMMSS>/ 를 만든다 (같은 초에 또 만들면 -2, -3 …)
  - clova_usage_log.LOG_PATH, trace.TRACE_PATH 를 그 폴더의 clova_usage.db, harness_trace.db 로 바꿔 끼운다.
    측정 프로세스 안에서만 바뀐다 (기존 critic_eval, live_eval 과 같은 방식). 운영 기록과 섞이지 않는다.
  - config 에 git(커밋, 브랜치, 고친 파일이 있는지)을 적는다

캐시는 disable_cache() 로 끈다. 같은 입력을 3번 돌려도 매번 새로 부르게 하려는 것이다.
사례 하나의 호출 수와 토큰은 CountingPost 로, 거절 이유는 rejections(run_id) 로 그 실행의 harness_trace.db 에서 모은다.
(live_eval 의 CountingPost·_reason 과 같은 일을 하고 토큰도 센다. live_eval 이 이 모듈을 쓰게 바꾸는 것은 담당과 협의 중이다)

result.json 모양 (schema 1): schema, suite, started_at, finished_at, git, config, systems, metrics, cases, validation.
스위트가 표를 더 남기면(EvalRun.tables, 예: 분류 혼동 행렬) tables 가 붙는다. 비어 있으면 넣지 않는다.
지표 한 줄은 metrics.metric() 모양이다. cases[].output 은 전문을 남긴다.
"""

import datetime as dt
import hashlib
import json
import subprocess
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core import clova_usage_log
from app.core.clova import Post
from app.core.seoul_time import SEOUL
from Harness import cache, trace

SCHEMA = 1
SERVER_DIR = Path(__file__).resolve().parents[2]
OUT_ROOT = SERVER_DIR / "db" / "app_data" / "harness_eval"
BASELINE = False  # all --baseline 이 켠다. 켜져 있으면 start() 가 config.baseline = true 를 적는다



def real_now() -> dt.datetime:
    """실제 서울 시각. 개발용 시계 앞당김(now_seoul)은 쓰지 않는다 (결과 폴더 이름과 시작·끝 시각이 실제 시각이어야 한다)."""
    return dt.datetime.now(SEOUL)


__all__ = ["CountingPost", "EvalRun", "OUT_ROOT", "SCHEMA", "disable_cache", "file_sha256", "git_info", "prompt_hashes",
           "real_now", "rejection_reason", "rejections", "sha256_of", "start"]


def sha256_of(value: object) -> str:
    """값의 sha256. 글자는 그대로, 그 밖에는 JSON(키 정렬)으로 바꿔서. 파생 세트 해시에 쓴다."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prompt_hashes(paths: Iterable[Path]) -> dict[str, str]:
    """프롬프트 파일 이름 → sha256. 프롬프트를 고친 뒤 결과가 바뀌었는지 비교할 때 쓴다."""
    return {Path(path).name: file_sha256(path) for path in paths}


def _git(*args: str, cwd: Path) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def git_info(cwd: Path = SERVER_DIR) -> dict:
    """{"commit": 짧은 해시, "branch": 브랜치, "dirty": 추적 중인 파일에 고친 것이 있는지}. git 이 없으면 값이 None."""
    status = _git("status", "--porcelain", "--untracked-files=no", cwd=cwd)
    return {
        "commit": _git("rev-parse", "--short", "HEAD", cwd=cwd),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd),
        "dirty": None if status is None else bool(status),
    }


def disable_cache() -> Callable[[], None]:
    """하네스 결과 캐시를 끈다. 되돌리는 함수를 돌려준다 (측정 스크립트는 되돌리지 않아도 된다).
    파일 층도 끈다: 측정용 가짜 가게의 결과가 실제 캐시 파일(db/app_data/harness_cache.db)에 쌓이지 않게."""
    original, original_path = cache.get, cache.CACHE_PATH
    cache.clear()
    cache.get = lambda key: None
    cache.CACHE_PATH = None

    def restore() -> None:
        cache.get = original
        cache.CACHE_PATH = original_path

    return restore


class CountingPost:
    """CLOVA 호출 수와 토큰을 세는 post. 사례마다 하나씩 만들어 RunContext.post 로 넘긴다.

    tokens 는 [입력, 출력] 합이다. 응답에 usage 가 없으면 더하지 않는다.
    """

    def __init__(self, post: Post = httpx.post):
        self.calls = 0
        self.tokens = [0, 0]
        self._post = post
        self._lock = threading.Lock()

    def __call__(self, url, **kwargs):
        with self._lock:
            self.calls += 1
        response = self._post(url, **kwargs)
        try:
            usage = response.json()["result"].get("usage") or {}
        except (ValueError, KeyError, TypeError, AttributeError):
            usage = {}
        with self._lock:
            self.tokens[0] += usage.get("promptTokens") or 0
            self.tokens[1] += usage.get("completionTokens") or 0
        return response


def rejection_reason(detail: str) -> str:
    """trace 는 긴 detail 을 잘라 저장하므로, JSON 이 깨졌으면 reason 뒤의 글자를 그대로 쓴다."""
    try:
        return json.loads(detail)["reason"]
    except (ValueError, KeyError, TypeError):
        return detail.split('"reason": "', 1)[-1]


def rejections(run_id: str) -> list[str]:
    """그 실행(과 그 아래 일꾼 실행)에서 거절된 제출의 이유들. 지금 trace.TRACE_PATH 에서 읽는다."""
    return [rejection_reason(step["detail"]) for step in trace.steps_of(run_id)
            if step["kind"] == "submit" and step["detail"] and '"accepted": false' in step["detail"]]


@dataclass
class EvalRun:
    suite: str
    out: Path
    started_at: str
    config: dict = field(default_factory=dict)
    systems: list[str] = field(default_factory=list)
    git: dict = field(default_factory=dict)
    metrics: list[dict] = field(default_factory=list)
    cases: list[dict] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)  # 지표 줄로 담기 어려운 표 (혼동 행렬 등)

    def add_metric(self, row: dict) -> None:
        self.metrics.append(row)

    def add_case(self, row: dict) -> None:
        self.cases.append(row)

    def as_dict(self, finished_at: str) -> dict:
        body = {"schema": SCHEMA, "suite": self.suite, "started_at": self.started_at, "finished_at": finished_at,
                "git": self.git, "config": self.config, "systems": self.systems, "metrics": self.metrics,
                "cases": self.cases, "validation": self.validation}
        if self.tables:
            body["tables"] = self.tables
        return body

    def finish(self) -> Path:
        """result.json 을 쓰고 그 경로를 돌려준다. 다시 불러도 된다 (덮어쓴다)."""
        path = self.out / "result.json"
        body = self.as_dict(real_now().isoformat(timespec="seconds"))
        path.write_text(json.dumps(body, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return path


def _new_folder(root: Path, suite: str, at: dt.datetime) -> Path:
    base = f"{suite}-{at.strftime('%Y%m%d-%H%M%S')}"
    root.mkdir(parents=True, exist_ok=True)
    for n in range(1, 100):
        out = root / (base if n == 1 else f"{base}-{n}")
        try:
            out.mkdir()
            return out
        except FileExistsError:
            continue
    raise RuntimeError(f"결과 폴더를 만들 수 없어요: {root / base}")


def start(suite: str, *, config: dict | None = None, systems: list[str] | None = None, root: Path | None = None,
          swap_logs: bool = True) -> EvalRun:
    """결과 폴더를 만들고 (swap_logs 면) CLOVA 사용 기록과 실행 기록을 그 폴더로 돌린다."""
    at = real_now()
    out = _new_folder(root or OUT_ROOT, suite, at)
    if swap_logs:
        clova_usage_log.LOG_PATH = out / "clova_usage.db"
        trace.TRACE_PATH = out / "harness_trace.db"
    config = dict(config or {})
    if BASELINE:
        config["baseline"] = True
    return EvalRun(suite=suite, out=out, started_at=at.isoformat(timespec="seconds"), config=config,
                   systems=list(systems or []), git=git_info())


def reopen(out: Path, previous: dict, *, systems: list[str] | None = None, swap_logs: bool = True) -> EvalRun:
    """끊긴 결과 폴더를 다시 연다 (result.json 의 config·started_at 을 이어 쓴다)."""
    if swap_logs:
        clova_usage_log.LOG_PATH = out / "clova_usage.db"
        trace.TRACE_PATH = out / "harness_trace.db"
    return EvalRun(suite=previous["suite"], out=out, started_at=previous["started_at"],
                   config=dict(previous.get("config") or {}), systems=list(systems or previous.get("systems") or []),
                   git=git_info())
