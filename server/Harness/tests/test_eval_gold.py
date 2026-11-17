"""정답지 읽기(Harness/evals/gold.py)와 평가 세트 만들기(derive.py). 3행짜리 가짜 정답지로만 본다 (실제 리뷰 아님)."""

import argparse
import datetime as dt
import json

import pytest

from Harness.evals import cli, derive, gold, report

openpyxl = pytest.importorskip("openpyxl")

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
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "gold"
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    workbook.create_sheet("about").append(["가짜 정답지"])
    workbook.save(path)
    return path, report.file_sha256(path)


@pytest.fixture
def fake_gold(tmp_path):
    return write_gold(tmp_path / "gold.xlsx")


@pytest.fixture
def cases(fake_gold):
    path, sha = fake_gold
    return gold.load_gold(path, sha)


# ── 정답지 읽기 ──


def test_reads_columns_into_case_shape(cases):
    first, second, third = cases
    assert first == {
        "case_id": "c0001", "store": "s005", "platform": "NAVER", "order_channel": "hall", "rating": 5.0,
        "written_at": "2026-05-01", "text": "국수가 맛있어요 010-1234-5678",
        "visit_keywords": "점심에 방문, 대기 없이 이용", "delivery_keywords": "",
        "gold": {"sentiment": "POSITIVE", "complaint_types": [],
                 "reply": "국수 칭찬 고마워요. 셀프바 반찬은 무료로 드세요! 다음에 또 봬요."},
        "flags": [], "eval_set": "balanced", "split": "tune",
    }
    assert second["platform"] == "COUPANG" and second["order_channel"] == "delivery" and second["rating"] is None
    assert second["gold"]["complaint_types"] == ["TASTE", "DELIVERY_DELAY"]  # JSON 글을 목록으로
    assert second["flags"] == ["reply_equals_review", "reply_mentions_memory"] and second["split"] == "holdout"
    # 배달상황키워드가 없어도 배달 플랫폼이면 delivery
    assert third["platform"] == "BAEMIN" and third["order_channel"] == "delivery"
    assert third["rating"] == 4.5 and third["split"] == "" and third["gold"]["sentiment"] == "MIXED"


def test_reply_copied_from_review_is_not_a_gold_reply(cases):
    assert cases[1]["gold"]["reply"] is None
    assert cases[0]["gold"]["reply"] and cases[2]["gold"]["reply"]


def test_stops_when_sha256_differs(fake_gold):
    path, sha = fake_gold
    with pytest.raises(gold.GoldError, match="sha256 이 달라요"):
        gold.load_gold(path, "0" * 64)
    with pytest.raises(gold.GoldError, match="파일이 없어요"):
        gold.load_gold(path.with_name("없음.xlsx"), sha)


def test_source_from_args_then_env_and_stops_without_path():
    with pytest.raises(gold.GoldError, match="정답지 경로를 주세요"):
        gold.resolve_source(env={})
    with pytest.raises(gold.GoldError, match="sha256 을 주세요"):
        gold.resolve_source("a.xlsx", env={})
    env = {gold.GOLD_ENV: "env.xlsx", gold.SHA_ENV: "ABC "}
    assert gold.resolve_source(env=env) == (gold.Path("env.xlsx"), "abc")
    assert gold.resolve_source("arg.xlsx", "def", env=env) == (gold.Path("arg.xlsx"), "def")


def test_cli_parser_takes_gold_options(fake_gold):
    path, sha = fake_gold
    args = cli.build_parser().parse_args(["critic", "--gold", str(path), "--gold-sha", sha])
    loaded_path, loaded_sha, loaded = gold.from_args(args)
    assert loaded_path == path and loaded_sha == sha and len(loaded) == 3


def test_bad_values_stop_with_case_id(tmp_path):
    bad_json = [list(ROWS[0])]
    bad_json[0][12] = "TASTE"
    path, sha = write_gold(tmp_path / "bad.xlsx", bad_json)
    with pytest.raises(gold.GoldError, match="c0001: complaint_types"):
        gold.load_gold(path, sha)
    path, sha = write_gold(tmp_path / "short.xlsx", [row[:-1] for row in ROWS], HEADER[:-1])
    with pytest.raises(gold.GoldError, match="열이 없어요: flags"):
        gold.load_gold(path, sha)


def test_summary_and_config_entry_hide_folder(cases, fake_gold):
    assert gold.summary(cases) == {
        "rows": 3, "balanced": 2, "tune": 1, "holdout": 1,
        "sentiment": {"POSITIVE": 1, "NEGATIVE": 1, "MIXED": 1},
        "order_channel": {"hall": 1, "delivery": 2}, "with_reply": 2,
    }
    path, sha = fake_gold
    assert gold.config_entry(path, sha, {"reply_tune": "x"}) == {"file": "gold.xlsx", "sha256": sha, "sets": {"reply_tune": "x"}}


# ── 평가 세트 ──


def test_sets_are_the_same_for_the_same_seed(cases):
    first = derive.build_sets(cases)
    again = derive.build_sets(json.loads(json.dumps(cases)))
    assert first == again and derive.set_hashes(first) == derive.set_hashes(again)
    assert [c["case_id"] for c in first["label_balanced"]] == ["c0001", "c0002"]
    assert [c["case_id"] for c in first["label_full"]] == ["c0001", "c0002", "c0003"]
    assert [c["case_id"] for c in first["reply_tune"]] == ["c0001"]
    assert [c["case_id"] for c in first["holdout"]] == ["c0002"]


def test_injection_appends_instruction_without_touching_source(cases):
    templates = derive.load_templates()
    rows = derive.injection_set(cases, templates)
    assert [row["case_id"] for row in rows] == ["c0001-inj"]  # tune 에서만 고른다
    row = rows[0]
    assert row["text"].startswith(cases[0]["text"]) and row["text"].endswith(row["injection"]["instruction"])
    assert row["injection"]["follow_markers"] and row["source_case_id"] == "c0001"
    assert cases[0]["text"] == "국수가 맛있어요 010-1234-5678" and "injection" not in cases[0]


def test_violation_uses_only_policy_fit_replies_outside_holdout(cases):
    templates = derive.load_templates()
    rows = derive.violation_set(cases, templates)
    assert {row["source_case_id"] for row in rows} == {"c0001", "c0003"}  # c0002 는 holdout 이고 답변도 없다
    for row in rows:
        assert row["good_reply"] != row["bad_reply"]
        assert row["condition"] == templates["violation"][row["kind"]]["condition"]
        if row["kind"] == "swap":
            other = next(case for case in cases if case["case_id"] == row["swapped_from"])
            assert row["bad_reply"] == other["gold"]["reply"] and row["inserted"] is None
        else:
            assert row["inserted"] in row["bad_reply"] and row["swapped_from"] is None
            assert row["bad_reply"].replace(f" {row['inserted']}", "", 1) == row["good_reply"]  # 끼운 문장 말고는 그대로


def test_violation_kinds_rotate_and_swap_falls_back_without_partner(cases):
    templates = derive.load_templates()
    one_reply = [cases[0], cases[1]]
    for seed in range(derive.SEED, derive.SEED + 10):
        (row,) = derive.violation_set(one_reply, templates, seed=seed)
        assert row["kind"] != "swap"  # 바꿔 끼울 다른 답변이 없다
    kinds = {row["kind"] for seed in range(derive.SEED, derive.SEED + 20)
             for row in derive.violation_set(cases, templates, seed=seed)}
    assert kinds == set(derive.VIOLATION_KINDS)


def test_insert_sentence_keeps_reply_and_adds_once():
    rng = derive.random.Random(1)
    reply = "감사합니다. 또 오세요!"
    for _ in range(10):
        out = derive.insert_sentence(reply, "끼운 문장.", rng)
        assert out.count("끼운 문장.") == 1 and out.replace(" 끼운 문장.", "", 1) == reply


def test_write_set_goes_to_run_folder_and_hash_matches(cases, tmp_path):
    sets = derive.build_sets(cases)
    sha = derive.write_set(tmp_path, "reply_tune", sets["reply_tune"])
    written = tmp_path / "sets" / "reply_tune.json"
    assert sha == derive.set_hashes(sets)["reply_tune"] == report.file_sha256(written)
    assert json.loads(written.read_text(encoding="utf-8")) == sets["reply_tune"]


def test_fact_candidates_collect_sentences_with_fact_words(cases):
    found = derive.fact_candidates(cases)
    assert [entry["sentence"] for entry in found] == ["셀프바 반찬은 무료로 드세요!", "육수는 매일 직접 끓입니다."]
    assert found[0]["words"] == ["무료", "셀프바"] and found[0]["case_ids"] == ["c0001"]
    masked = derive.fact_candidates([{**cases[0], "gold": {**cases[0]["gold"], "reply": "무료 문의 010-9999-8888."}}])
    assert "010-9999-8888" not in masked[0]["sentence"]


def test_gold_main_prints_summary(fake_gold, capsys):
    path, sha = fake_gold
    gold.main(["--gold", str(path), "--gold-sha", sha])
    assert json.loads(capsys.readouterr().out)["rows"] == 3
    with pytest.raises(SystemExit, match="sha256 이 달라요"):
        gold.main(["--gold", str(path), "--gold-sha", "0" * 64])


def test_namespace_without_gold_uses_env(monkeypatch, fake_gold):
    path, sha = fake_gold
    monkeypatch.setenv(gold.GOLD_ENV, str(path))
    monkeypatch.setenv(gold.SHA_ENV, sha)
    assert len(gold.from_args(argparse.Namespace())[2]) == 3
