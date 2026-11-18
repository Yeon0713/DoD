"""CLOVA Voice 실시간 합성 시간을 측정한다. 실행하면 API 호출 비용이 발생한다."""

import argparse
import statistics
import time
from collections.abc import Callable, Iterable

from Harness.evals import metrics, report

QUESTION = 5
SENTENCES = (
    "오늘 일정 브리핑 준비했어요.",
    "저녁 7시에 단체 손님 열두 분이 오세요.",
    "강남 페스티벌이 저녁 6시에 있어요.",
    "한국시리즈가 저녁 6시 반에 시작해요.",
    "저녁 예약은 네 팀이에요.",
    "밤사이 리뷰 5개를 읽어 뒀어요.",
    "아쉬운 리뷰가 2개 있어요.",
    "아쉬운 리뷰에 제가 바로 답할까요?",
    "네, 앞으로는 제가 바로 답할게요.",
    "방금 답글을 달았어요.",
    "손님들이 국물 맛을 좋아하세요.",
    "좋은 리뷰 답글 3개를 예약했어요.",
    "토요일 오전 11시에 올릴게요.",
    "브리핑은 여기까지예요.",
    "다시 말씀드릴게요.",
    "내일 예약은 두 팀이에요.",
    "목요일에 비 소식이 있어요.",
    "그건 아직 몰라요.",
    "인스타에 인기 메뉴를 올릴까요?",
    "잘 못 들었어요. 한 번 더 말씀해 주세요.",
)

timer = time.perf_counter  # 테스트에서 바꾼다
Synth = Callable[[str], Iterable]


def unavailable_reason() -> str | None:
    """TTS 를 쓸 수 없는 까닭. 쓸 수 있으면 None."""
    from voice import tts

    if not tts.ENABLED:
        return "VOICE_TTS=false 로 꺼져 있음"
    if not tts.available():
        return "CLOVA Voice 인증 정보가 없음"
    return None


def synthesizer() -> Synth:
    from voice import tts

    def synth(text: str) -> Iterable:
        yield tts.synthesize(tts.spoken(text))

    return synth


def measure(synth: Synth, sentences: Iterable[str] = SENTENCES, *, runs: int = 1, warm_up: bool = True) -> list[dict]:
    sentences = list(sentences)
    if warm_up and sentences:
        try:
            for _ in synth(sentences[0]):
                pass
        except Exception:  # 데우기 실패는 아래 첫 문장에서 다시 드러난다
            pass
    rows = []
    for run in range(1, runs + 1):
        for number, text in enumerate(sentences, 1):
            started, first, chunks, error = timer(), None, 0, None
            try:
                for _ in synth(text):
                    if first is None:
                        first = timer() - started
                    chunks += 1
                if chunks == 0:
                    error = "오디오 조각이 없음"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            total = timer() - started
            ok = error is None
            rows.append({"case_id": f"tts:{number}", "system": "tts", "run": run, "text": text,
                         "first_seconds": round(first, 4) if ok and first is not None else None,
                         "total_seconds": round(total, 4) if ok else None, "chunks": chunks, "error": error})
    return rows


def score(rows: list[dict]) -> list[dict]:
    out = []
    for field, label in (("first_seconds", "첫 소리"), ("total_seconds", "전체 합성")):
        values = [row[field] for row in rows if row[field] is not None]
        short = field.split("_")[0]
        for name, value in (("p50", statistics.median(values) if values else None),
                            ("p95", metrics.percentile(values, 95))):
            out.append(metrics.value_metric(f"tts_{short}_{name}", f"TTS {label} 시간 {name}", question=QUESTION, system="tts",
                                            value=value, unit="seconds"))
    out.append(metrics.metric("tts_error_rate", "TTS 합성 실패 비율", question=QUESTION, system="tts",
                              numerator=sum(1 for row in rows if row["error"]), denominator=len(rows), higher_is_better=False))
    return out


def run(args: argparse.Namespace, synth: Synth | None = None):
    """python -m Harness.evals tts [--runs 1]. TTS 를 쓸 수 없으면 '안 돌림'을 출력하고 결과 폴더를 만들지 않는다."""
    from voice import tts

    if synth is None:
        reason = unavailable_reason()
        if reason:
            print(f"안 돌림: TTS 를 쓸 수 없어요 ({reason})", flush=True)
            return None
        try:
            synth = synthesizer()
        except Exception as exc:
            print(f"안 돌림: TTS 모델을 올리지 못했어요 ({type(exc).__name__}: {exc})", flush=True)
            return None
    print(f"TTS 합성 시간: 문장 {len(SENTENCES)}개 × 회차 {args.runs}", flush=True)
    config = {"runs": args.runs, "sentences": len(SENTENCES), "model": tts.MODEL, "speaker": tts.SPEAKER,
              "cache": "쓰지 않음 (늘 새로 만듦)", "warm_up": "첫 문장을 한 번 먼저 만들고 버림 (첫 요청 제외)"}
    eval_run = report.start("tts", config=config, systems=["tts"])
    print(f"결과 폴더: {eval_run.out}", flush=True)
    rows = measure(synth, runs=args.runs)
    eval_run.cases, eval_run.metrics = rows, score(rows)
    path = eval_run.finish()
    for metric in eval_run.metrics:
        print(f"  {metric['id']}: {metric['value']}", flush=True)
    print(f"result.json: {path}")
    return path
