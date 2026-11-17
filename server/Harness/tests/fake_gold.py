"""평가 테스트용 3행짜리 가짜 정답지 (실제 리뷰 아님). 열 이름은 정답지 시트 gold 와 같다.

c0001 네이버, 홀, 긍정, balanced/tune, 답변 있음 (전화번호가 든 리뷰)
c0002 쿠팡이츠, 배달, 부정 [TASTE, DELIVERY_DELAY], balanced/holdout, 답변이 리뷰 복사 (reply_equals_review)
c0003 배달의민족, 배달(키워드 없음), 혼합 [PORTION], full_only, 답변 있음
"""

import datetime as dt

from Harness.evals import report

HEADER = ["case_id", "index_id", "별점", "방문상황키워드", "배달상황키워드", "주문일", "손님 리뷰", "사장님 답변일", "사장님 답변",
          "플랫폼", "class", "sentiment", "complaint_types", "complaint_note", "eval_set", "split", "flags"]
ROWS = [
    ["c0001", 11, 5, "점심에 방문, 대기 없이 이용", None, dt.datetime(2026, 5, 1), "국수가 맛있어요 010-1234-5678",
     dt.datetime(2026, 5, 2), "국수 칭찬 고마워요. 셀프바 반찬은 무료로 드세요! 다음에 또 봬요.",
     "네이버플레이스", 1, "POSITIVE", "[]", None, "balanced", "tune", None],
    ["c0002", 12, None, None, "포장 상태 좋음", dt.datetime(2026, 6, 3), "면이 불어서 왔어요",
     dt.datetime(2026, 6, 4), "면이 불어서 왔어요", "쿠팡이츠", 0, "NEGATIVE", '["TASTE", "DELIVERY_DELAY"]', "면 불음",
     "balanced", "holdout", "reply_equals_review,reply_mentions_memory"],
    ["c0003", 13, 4.5, None, None, dt.datetime(2026, 7, 5), "양은 적은데 맛은 좋아요",
     dt.datetime(2026, 7, 6), "양이 아쉬우셨다니 죄송해요. 육수는 매일 직접 끓입니다.", "배달의민족", 2, "MIXED", '["PORTION"]',
     None, "full_only", None, None],
]


def write_gold(path, rows=ROWS, header=HEADER):
    """가짜 정답지를 path 에 쓰고 (경로, sha256) 을 돌려준다."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "gold"
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    workbook.create_sheet("about").append(["가짜 정답지"])
    workbook.save(path)
    return path, report.file_sha256(path)
