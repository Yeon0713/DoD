"""평가 지표 요약: 결과 폴더들에서 질문 1~5 의 대표 지표만 뽑아 마크다운 표 하나로 쓴다. CLOVA 를 부르지 않는다.

python -m Harness.evals summary --results 폴더1,폴더2,… --out 평가지표-요약.md
  --results 는 결과 폴더 경로나 report.OUT_ROOT 아래 폴더 이름. 비우면 결과 폴더 뿌리의 모든 실행에서 고른다.
  지표마다 그 스위트에서 그 지표가 있는 가장 최근 실행을 쓴다 (판정기를 나눠 돌린 guards 처럼 시스템마다 다를 수 있다).
  --out 을 비우면 지금 폴더에 평가지표-요약-<YYYY-MM-DD>.md 를 쓴다. 저장소 안에는 쓰지 않는다 (작업 공간 폴더를 준다).

지표·계산·목표는 scorecard.py 에 있다 (대시보드 평가 탭 맨 위 카드와 같은 계산).
  분모 MIN_DENOMINATOR(10) 미만은 "표본 부족", 결과가 없으면 "안 돌림". 95% 구간은 사례 단위 Wilson 구간.
"""

import argparse
import json
from pathlib import Path

from Harness.evals import report, scorecard

NOT_RUN = "안 돌림"
TOO_FEW = "표본 부족"
HEADER = ("질문", "세부 지표", "시스템", "분자/분모", "값", "95% 구간", "목표", "통과", "결과 폴더", "커밋", "비고")


def load(folder: Path) -> dict | None:
    path = Path(folder) / "result.json"
    if not path.is_file():
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    body["_folder"] = Path(folder)
    return body


def resolve(name: str, root: Path) -> Path:
    path = Path(name)
    return path if path.is_dir() else root / name


def all_folders(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if (path / "result.json").is_file()) if root.is_dir() else []


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}초"


def commit_of(cell: dict) -> str:
    if not cell.get("commit"):
        return "-"
    return f"{cell['commit']}+수정" if cell.get("dirty") else cell["commit"]


def cells(item: dict, cell: dict) -> list[str]:
    """[분자/분모, 값, 95% 구간, 목표, 통과, 결과 폴더, 커밋, 비고]"""
    target = item["target"] or ("낮을수록 (기준 없음)" if item["lower_better"] else "높을수록 (기준 없음)")
    notes = [text for text in (item["note"], cell.get("note")) if text]
    if cell["status"] == "not_run":
        return ["-", NOT_RUN + (" (사람 표본 없음)" if item["optional"] else ""), "-", target, "-", "-", "-", " · ".join(notes)]
    if item["kind"] == "latency":
        fraction = f"n={cell['n']}"
        value = TOO_FEW if cell["status"] == "too_few" else f"p50 {seconds(cell['p50'])} · p95 {seconds(cell['p95'])}"
        interval = "-"
    elif item["kind"] == "f1":
        fraction, value, interval = "-", f"{cell['value']:.2f}", "- (F1 은 구간 없음)"
    else:
        fraction = f"{cell['numerator']}/{cell['denominator']}"
        if cell["status"] == "too_few":
            value, interval = TOO_FEW, "-"
        else:
            value = percent(cell["value"])
            interval = f"{percent(cell['interval'][0])} ~ {percent(cell['interval'][1])}" if cell["interval"] else "-"
    if cell.get("run_fraction"):
        notes.append(f"회차 합 {cell['run_fraction']}")
    if cell.get("recomputed"):
        notes.append("cases 에서 다시 셈")
    if cell.get("baseline_diff") is not None:
        diff = cell["baseline_diff"]
        shown = f"{diff * 100:+.1f}%p" if item["kind"] == "ratio" else f"{diff:+.2f}" + ("초" if item["kind"] == "latency" else "")
        notes.append(f"기준점 대비 {shown}")
    passed = "-" if cell["passed"] is None else ("통과" if cell["passed"] else "미달")
    return [fraction, value, interval, target, passed, cell["folder"] or "-", commit_of(cell), " · ".join(notes)]


def table(card: dict) -> list[list[str]]:
    lines = []
    for question in card["questions"]:
        for item in question["items"]:
            for cell in item["cells"]:
                lines.append([question["title"], f"{item['group']} · {item['label']}", cell["system"], *cells(item, cell)])
    return lines


def render(card: dict, made_at) -> str:
    lines = [
        f"# 평가 지표 요약 ({made_at:%Y-%m-%d %H:%M})",
        "",
        f"95% 구간은 사례 단위 Wilson 구간이다 (회차를 여러 번 돌렸으면 사례마다 다수결, 반반이면 나쁜 쪽). "
        f"분모가 {card['min_denominator']} 미만이면 \"{TOO_FEW}\", 돌리지 않은 지표는 \"{NOT_RUN}\". 통과는 표본이 충분하고 목표가 있을 때만.",
        f"응답 시간은 {scorecard.SERVER_TIME}이다. TTS 시간은 따로 재고, 둘을 더하면 체감 시간(네트워크 제외)이다. "
        f"말 알아듣기 강도별 정확도는 {scorecard.MOCK_NOISE}로 잰 것이다.",
        "",
        "| " + " | ".join(HEADER) + " |",
        "|" + "|".join("---" for _ in HEADER) + "|",
    ]
    lines += ["| " + " | ".join(str(cell).replace("|", "\\|") for cell in line) + " |" for line in table(card)]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> Path:
    root = report.OUT_ROOT
    names = [part.strip() for part in (getattr(args, "results", "") or "").split(",") if part.strip()]
    folders = [resolve(name, root) for name in names] if names else all_folders(root)
    results = []
    for folder in folders:
        body = load(folder)
        if body is None:
            raise SystemExit(f"result.json 이 없는 폴더예요: {folder}")
        results.append(body)
    card = scorecard.scorecard(results)
    used = sorted({cell["folder"] for q in card["questions"] for item in q["items"] for cell in item["cells"] if cell["folder"]})
    print("쓴 결과 폴더: " + (", ".join(used) or "없음"), flush=True)
    made_at = report.real_now()
    out = Path(args.out) if getattr(args, "out", None) else Path.cwd() / f"평가지표-요약-{made_at:%Y-%m-%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = render(card, made_at)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"요약: {out}")
    return out
