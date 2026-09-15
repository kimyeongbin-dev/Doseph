"""주석 stale 게이트 단위 테스트 (안정화 구간 S1.5).

**왜 이 게이트가 있나 — 실측 근거**

커밋 ``c395776`` 은 QA-01(soft delete 폐지) 이후에도 거짓으로 남아 있던 문장
**57줄**을 정정했다. 그중 2줄은 OpenAPI ``summary`` 와 DTO ``description`` 으로
**사용자에게까지 노출**돼 있었다. 그 57줄을 표본으로 각 수단의 검출률을 셌다:

===========================  =========  ==========
수단                         검출        성격
===========================  =========  ==========
폐기 어휘 사전                47 / 57    차단
주석 속 식별자 실재 검사      +2 → 49    차단
(의미 일치 일반)              불가        —
===========================  =========  ==========

**남는 8줄은 전부 "주석이 계약을 서술"한 것**이라 기계로는 못 잡는다.
그건 게이트가 아니라 규칙으로 막는다(CLAUDE.md: 계약은 테스트가 말한다).

⚠️ 표본은 `tmp_path` 로 만든다. 실제 저장소를 읽으면 저장소 상태에 따라
결과가 바뀌는 **스냅샷 테스트**가 되지, 게이트 테스트가 아니다.
"""

from pathlib import Path

import pytest

from scripts.gates.code.check_comment_staleness import (
    find_banned_vocabulary,
    find_missing_identifiers,
    load_vocabulary_rules,
)


# ── 폐기 어휘 사전 ────────────────────────────────────────────────────
# 흐름: 폐기어 목록 -> 소스 스캔 -> 주석/문서열에 남아 있으면 보고
def test_banned_word_in_comment_is_reported(tmp_path: Path) -> None:
    """폐기된 개념의 어휘가 주석에 남아 있으면 잡는다.

    실제 사례: QA-01 이 soft delete 를 폐지했는데 47줄이 그대로 남았다.
    """
    source = tmp_path / "svc.py"
    source.write_text('"""Delete challenge (soft delete)."""\n', encoding="utf-8")

    hits = find_banned_vocabulary(tmp_path, banned=["soft delete"], allow=[])

    assert len(hits) == 1
    assert hits[0].line == 1
    assert "soft delete" in hits[0].text


def test_banned_word_in_code_is_also_reported(tmp_path: Path) -> None:
    """주석뿐 아니라 **식별자·문자열**도 본다.

    OpenAPI ``summary="... (soft delete)"`` 가 사용자에게 노출돼 있었다 —
    그건 주석이 아니라 코드였다. 주석만 보면 가장 비싼 거짓을 놓친다.
    """
    source = tmp_path / "router.py"
    source.write_text('summary = "Bulk delete (soft delete)"\n', encoding="utf-8")

    assert len(find_banned_vocabulary(tmp_path, banned=["soft delete"], allow=[])) == 1


def test_allowed_location_is_not_reported(tmp_path: Path) -> None:
    """사유가 등록된 위치는 통과한다.

    폐기어에도 **정당한 사용**이 있다 — OCR draft 의 ``consumed_at`` 은 진짜
    soft delete 다. 허용이 없으면 게이트는 거짓말쟁이가 되고 곧 꺼진다.
    """
    source = tmp_path / "ocr.py"
    source.write_text("# soft delete — consumed_at 으로 감춘다\n", encoding="utf-8")

    hits = find_banned_vocabulary(tmp_path, banned=["soft delete"], allow=["ocr.py"])

    assert hits == []


def test_vocabulary_rules_require_a_reason(tmp_path: Path) -> None:
    """허용목록 항목은 **사유가 있어야** 로드된다.

    사유 없는 허용목록은 곧 통과 기계가 된다 — 아무나 한 줄 추가하면 끝이라
    무엇을 왜 봐주는지 아무도 모르게 된다.
    """
    rules = tmp_path / "vocab.toml"
    rules.write_text(
        '[[banned]]\nword = "soft delete"\nreason = "QA-01 에서 폐지"\n'
        '[[allow]]\npath = "app/services/ocr_service.py"\nreason = "consumed_at 은 진짜 soft delete"\n',
        encoding="utf-8",
    )

    banned, allow = load_vocabulary_rules(rules)

    assert banned == ["soft delete"]
    assert allow == ["app/services/ocr_service.py"]


def test_allow_entry_without_reason_is_rejected(tmp_path: Path) -> None:
    """사유 없는 허용 항목은 **로드 자체가 실패**한다."""
    rules = tmp_path / "vocab.toml"
    rules.write_text('[[banned]]\nword = "x"\nreason = "y"\n[[allow]]\npath = "a.py"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="reason"):
        load_vocabulary_rules(rules)


# ── 주석 속 식별자 실재 검사 ──────────────────────────────────────────
# 흐름: 주석에서 ``이름`` 추출 -> 저장소 어디에도 없으면 보고
def test_comment_naming_a_missing_symbol_is_reported(tmp_path: Path) -> None:
    """주석이 말하는 이름이 코드에 없으면 잡는다.

    실제 사례: 주석이 ``_cascade_delete_profile`` 을 말했는데 실제 이름은
    ``cascade_delete_profile`` 이었다. 오늘 30곳을 고치면서도 못 봤다.
    """
    (tmp_path / "svc.py").write_text(
        "# SELF guard 우회: ``_cascade_delete_profile`` 직접 호출\ndef cascade_delete_profile():\n    pass\n",
        encoding="utf-8",
    )

    missing = find_missing_identifiers(tmp_path)

    assert [m.name for m in missing] == ["_cascade_delete_profile"]


def test_comment_naming_an_existing_symbol_passes(tmp_path: Path) -> None:
    """실재하는 이름은 보고하지 않는다."""
    (tmp_path / "svc.py").write_text(
        "# 흐름: ``cascade_delete_profile`` 을 호출\ndef cascade_delete_profile():\n    pass\n",
        encoding="utf-8",
    )

    assert find_missing_identifiers(tmp_path) == []
