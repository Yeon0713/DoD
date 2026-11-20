"""글자 폭 계산과 말할 숫자 읽기 (문서 6장, 12장)."""

from voice import speech, width


def test_width_counts_hangul_as_one_and_others_as_half():
    assert width.width("7시에 단체 손님 열두 분이 오세요.") == 16.5  # 문서 6장의 예
    for text, expected in [("오늘 일정 브리핑 준비했어요", 13.5), ("좋은 리뷰 3개, 아쉬운 리뷰 2개예요.", 17.5),
                           ("한국시리즈 저녁 6시 30분", 12), ("금요일 저녁엔 배달 시간을 10분 넉넉히 안내해 보세요", 25.5)]:
        assert width.width(text) == expected, text


def test_violations_finds_fields_over_the_limit():
    response = {
        "headline": "아주아주아주아주아주아주 긴 첫마디예요",
        "say": [{"text": "괜찮아요", "caption": "짧아요", "focus": []}],
        "suggestions": ["처음부터 다시 말해 주세요", "리뷰 보여 줘"],  # 11.5 + 5 = 16.5
        "cards": [{"type": "counts", "id": "c", "items": [{"id": "a", "label": "좋은 리뷰", "count": 1}]}],
    }
    found = width.violations(response)
    assert any(f.startswith("headline") for f in found)
    assert any("suggestions 합친 폭" in f for f in found)
    assert any("정확히 2" in f for f in found)
    assert not any("say[0]" in f for f in found)


def test_fit_picks_the_first_choice_that_fits():
    assert width.fit("caption", "강남 페스티벌과 한국시리즈가 있어요. 정말로요", "페스티벌과 한국시리즈가 있어요.") == "페스티벌과 한국시리즈가 있어요."


def test_native_numbers_and_clock_labels():
    import datetime as dt

    assert [speech.native(n) for n in (1, 2, 3, 4, 5, 10, 12, 14, 20, 21, 99)] == \
        ["한", "두", "세", "네", "다섯", "열", "열두", "열네", "스무", "스물한", "아흔아홉"]
    assert speech.count(12, "분") == "열두 분"
    day = dt.datetime(2026, 11, 17, 18, 30)
    assert speech.clock_label(day) == "저녁 6시 반"
    assert speech.clock_label(day.replace(minute=15)) == "저녁 6시 15분"
    assert speech.clock_label(day.replace(hour=8, minute=0)) == "아침 8시"
    assert speech.clock_label(day.replace(hour=11, minute=0)) == "오전 11시"
    assert speech.clock_label(day.replace(hour=17, minute=0)) == "오후 5시"
    assert speech.josa("강남 페스티벌", "과", "와") == "강남 페스티벌과" and speech.josa("한국시리즈", "이", "가") == "한국시리즈가"


def test_too_long_tells_the_agent_in_letters():
    assert width.too_long("title", "땅콩 알레르기 손님 대체 메뉴 준비", "staff.title") == (
        "title 칸이 길어요 (지금 16.5자, 16자까지. 띄어쓰기·숫자는 반 자). 더 짧게 다시 써 주세요")
    assert width.limit_note("staff.detail") == "한글 48자까지, 띄어쓰기·숫자는 반 자"
