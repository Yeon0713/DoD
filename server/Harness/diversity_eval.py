"""리뷰 답글이 서로 얼마나 비슷한지 잰다. 실제 CLOVA 를 부르므로 비용이 든다 (한 바퀴 12건, 약 100~150원).

사용 (server/ 에서):
  python -m Harness.diversity_eval              # 리뷰 12건에 답글 한 번씩
  python -m Harness.diversity_eval --rounds 3   # 같은 12건을 세 바퀴 (바퀴마다 따로 재고 평균)

- 가상 가게 t001 (Harness/tests/fakes.py) 에 서로 다른 리뷰 12건(불만 5, 섞임 3, 칭찬 4)을 더해 reply_agent.draft 로 답글을 쓴다.
- 측정 중에는 캐시를 쓰지 않는다. 물러나기(FALLBACK) 답글도 사장님이 보게 되므로 함께 잰다.
- 재는 것 (similarity_report)
  avg_similarity  답글 두 개씩 짝지어 본 글자 3-gram 겹침(Jaccard)의 평균. 0 이면 전혀 다르고 1 이면 같다
  top_pairs       가장 비슷한 짝 3개
  openings        첫 문장 앞 두 어절이 같은 답글 수 (예: "정말 죄송합니다" 로 시작하는 답글 5개)
  endings         끝 문장 뒤 두 어절이 같은 답글 수 (예: "더 신경 쓰겠습니다" 로 끝나는 답글 6개)
  common_phrases  답글 여러 개(4분의 1 이상, 최소 2개)에 나온 두 어절 표현
- 결과(답글 전문, 측정값)는 db/app_data/harness_eval/diversity-<시각>/result.json 에 남는다. 고치기 전후를 이 파일로 비교한다.
"""

import argparse
import dataclasses
import datetime as dt
import itertools
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.core import clova_usage_log
from app.core.config import settings
from Harness import cache, limiter, trace
from Harness.live_eval import OUT_ROOT, _tokens, rate_limited

# (리뷰 id, 별점, 글, 분위기, 불만 종류, 손님 구분, 손님 키)
REVIEWS = [
    ("n1", 2, "잔치국수 국물이 너무 짰어요. 물을 부어서 먹었네요", "NEGATIVE", ["TASTE"], "BASIC", "dn1"),
    ("n2", 1, "1시간 넘게 걸려서 면이 다 불어서 왔어요", "NEGATIVE", ["DELIVERY_DELAY"], "BASIC", "dn2"),
    ("n3", 2, "비빔국수 양이 전보다 확 줄었어요. 이 가격에 이 양은 좀 아쉽네요", "NEGATIVE", ["PORTION"], "BASIC", "dn3"),
    ("n4", 2, "전화로 주문했는데 너무 퉁명스럽게 받으셔서 기분이 상했어요", "NEGATIVE", ["SERVICE"], "BASIC", "dn4"),
    ("n5", 1, "만두에서 머리카락이 나왔어요", "NEGATIVE", ["HYGIENE"], "BASIC", "dn5"),
    ("x1", 3, "만두는 맛있는데 잔치국수 면이 좀 퍼졌어요", "MIXED", ["TASTE"], "BASIC", "dx1"),
    ("x2", 3, "맛은 좋은데 배달이 40분 넘게 걸렸어요", "MIXED", ["DELIVERY_DELAY"], "BASIC", "dx2"),
    ("x3", 4, "비빔국수 양념은 최고인데 양이 조금 적어요", "MIXED", ["PORTION"], "BASIC", "dx3"),
    ("p1", 5, "국물이 진하고 깔끔해요. 추운 날 먹기 딱이에요", "POSITIVE", [], "BASIC", "dp1"),
    ("p2", 5, "만두 속이 꽉 차 있어서 놀랐어요. 다음에 또 시킬게요", "POSITIVE", [], "BASIC", "dp2"),
    ("p3", 5, "비빔국수 매콤달콤해서 너무 맛있어요", "POSITIVE", [], "WEEKLY", "c1"),
    ("p4", 5, "포장도 꼼꼼하고 배달도 빨랐어요. 잘 먹었습니다", "POSITIVE", [], "BASIC", "dp4"),
]

SENTENCE_RE = re.compile(r"[^.!?~\n]+[.!?~]*")
NOT_WORD_RE = re.compile(r"[^\w가-힣]")


# ── 측정 (CLOVA 없이 도는 순수 함수) ──


def _normalize(text: str) -> str:
    return NOT_WORD_RE.sub("", text)


def char_ngrams(text: str, n: int = 3) -> set[str]:
    flat = _normalize(text)
    return {flat[i:i + n] for i in range(len(flat) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _words(sentence: str) -> list[str]:
    return [w for w in (_normalize(w) for w in sentence.split()) if w]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.findall(text) if _normalize(s)]


def opening(text: str) -> str:
    sentences = _sentences(text)
    return " ".join(_words(sentences[0])[:2]) if sentences else ""


def ending(text: str) -> str:
    sentences = _sentences(text)
    return " ".join(_words(sentences[-1])[-2:]) if sentences else ""


def similarity_report(texts: list[str]) -> dict:
    """답글 목록이 서로 얼마나 비슷한지."""
    grams = [char_ngrams(t) for t in texts]
    pairs = sorted(((jaccard(grams[i], grams[j]), i, j) for i, j in itertools.combinations(range(len(texts)), 2)), reverse=True)
    phrase_counts = Counter()
    for text in texts:
        words = _words(text)
        phrase_counts.update({" ".join(words[i:i + 2]) for i in range(len(words) - 1)})  # 한 답글에서는 한 번만 센다
    min_count = max(2, -(-len(texts) // 4))
    repeated = lambda counter: [[k, v] for k, v in counter.most_common() if k and v >= 2]
    return {
        "count": len(texts),
        "avg_similarity": round(sum(p[0] for p in pairs) / len(pairs), 3) if pairs else 0.0,
        "top_pairs": [{"similarity": round(s, 3), "a": texts[i], "b": texts[j]} for s, i, j in pairs[:3]],
        "openings": repeated(Counter(opening(t) for t in texts)),
        "endings": repeated(Counter(ending(t) for t in texts)),
        "common_phrases": [[k, v] for k, v in phrase_counts.most_common() if v >= min_count][:10],
    }


# ── 측정 데이터 ──


def make_snapshot():
    """fakes 의 가상 가게에 REVIEWS 와 그 답글 할 일을 더한다."""
    from app.planner.data_shapes import Basis, PlanItem, Review
    from Harness.tests.fakes import NOW, at, label
    from Harness.tests.fakes import make_snapshot as base_snapshot

    snapshot = base_snapshot()
    written = at(NOW.date(), 10)
    reviews = [
        Review(review_id=rid, platform="BAEMIN", written_at=written, rating=rating, text=text, customer_key=customer,
               order_id=None, label=label(sentiment, types))
        for rid, rating, text, sentiment, types, _, customer in REVIEWS
    ]
    items = [
        PlanItem(plan_id=f"REVISIT_REPLY:{rid}:2026-11-15", task_type="REVISIT_REPLY", basis=Basis(kind="REVIEW", ref_id=rid),
                 target_date=NOW.date(), approval_request_at=at(NOW.date(), 14), reason_line="이유",
                 planned_at=NOW - dt.timedelta(hours=2), revisit_class=revisit)
        for rid, _, _, _, _, revisit, _ in REVIEWS
    ]
    plan = snapshot.plan.model_copy(update={"plan_items": items})
    return dataclasses.replace(snapshot, reviews=snapshot.reviews + reviews, plan=plan)


def collect(rounds: int, workers: int, draft: Callable | None = None) -> list[list[dict]]:
    """바퀴마다 리뷰 12건의 답글. 한 줄은 {review_id, review, source, text, seconds}."""
    from Harness.agents import reply_agent
    from Harness.spec import RunContext
    from Harness.tests.fakes import NOW

    draft = draft or reply_agent.draft
    results: list[list[dict | None]] = [[None] * len(REVIEWS) for _ in range(rounds)]

    def one(round_no: int, index: int) -> None:
        snapshot = make_snapshot()
        item = snapshot.plan.plan_items[index]
        started = time.perf_counter()
        try:
            proposal = draft(item, RunContext(snapshot=snapshot, now=NOW))
        except Exception as exc:  # 측정은 끝까지 간다
            proposal, error = None, repr(exc)
        else:
            error = None
        text = proposal.content.get("text") if proposal else None
        row = {"review_id": REVIEWS[index][0], "review": REVIEWS[index][2], "source": proposal.source if proposal else "NONE",
               "text": text, "seconds": round(time.perf_counter() - started, 1), "error": error}
        results[round_no][index] = row
        print(f"[{round_no + 1}/{rounds}] {row['review_id']}: {row['source']} ({row['seconds']}초) {text or ''}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in [pool.submit(one, r, i) for r in range(rounds) for i in range(len(REVIEWS))]:
            future.result()
    return results  # type: ignore[return-value]


def summarize(results: list[list[dict]]) -> dict:
    per_round = [similarity_report([row["text"] for row in rows if row["text"]]) for rows in results]
    sources = Counter(row["source"] for rows in results for row in rows)
    return {
        "avg_similarity": round(sum(r["avg_similarity"] for r in per_round) / len(per_round), 3),
        "sources": dict(sources),
        "rounds": per_round,
    }


def run(rounds: int, workers: int) -> dict:
    out = OUT_ROOT / ("diversity-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    clova_usage_log.LOG_PATH = out / "clova_usage.db"
    trace.TRACE_PATH = out / "harness_trace.db"
    cache.clear()
    cache.get = lambda key: None  # 측정 중에는 캐시를 쓰지 않는다

    results = collect(rounds, workers)
    summary = summarize(results)
    tokens_in, tokens_out = _tokens(clova_usage_log.LOG_PATH)
    won = tokens_in * settings.clova_price_input_per_1k / 1000 + tokens_out * settings.clova_price_output_per_1k / 1000
    report = {"at": dt.datetime.now().isoformat(timespec="seconds"), "rounds": rounds, "summary": summary,
              "tokens": [tokens_in, tokens_out], "won": round(won), "detail": results}
    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n출처 {summary['sources']}, 429 {rate_limited(clova_usage_log.LOG_PATH)}번")
    print(f"평균 유사도 (글자 3-gram Jaccard): {summary['avg_similarity']}")
    for number, r in enumerate(summary["rounds"], 1):
        print(f"\n[{number}바퀴] 답글 {r['count']}개, 평균 유사도 {r['avg_similarity']}")
        print(f"  같은 시작: {r['openings'] or '없음'}")
        print(f"  같은 끝: {r['endings'] or '없음'}")
        print(f"  자주 나온 표현: {r['common_phrases'] or '없음'}")
        for pair in r["top_pairs"]:
            print(f"  비슷한 짝 {pair['similarity']}\n    - {pair['a']}\n    - {pair['b']}")
    print(f"\n토큰 입력 {tokens_in:,} / 출력 {tokens_out:,}, 약 {round(won)}원 (.env 단가 기준). 기록: {out}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="실제 CLOVA 로 리뷰 답글끼리 얼마나 비슷한지 측정")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4, help="동시에 돌리는 답글 수")
    parser.add_argument("--concurrency", type=int, default=2, help="CLOVA 동시 호출 한도")
    args = parser.parse_args()
    if not settings.clova_studio_api_key:
        raise SystemExit("server/.env 에 CLOVA_STUDIO_API_KEY 가 없어요")
    limiter.set_max_concurrent(args.concurrency)
    run(args.rounds, args.workers)


if __name__ == "__main__":
    main()
