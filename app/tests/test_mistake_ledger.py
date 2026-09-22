"""실수 대장 공용 파서 단위 테스트 (트랙 B-13 S1').

이 파서는 **게이트 둘이 공유**한다 — `check_mistake_routing`(축 ↔ 라우팅 표)과
신설 `check_mistake_prevention`(예방 값). 파서가 둘이 되면 **서로 다른 수를 센다**(대장 `D31`).

⚠️ 이 테스트는 **실제 대장을 읽지 않는다.** `tmp_path` 표본을 쓴다 —
저장소 상태에 따라 결과가 바뀌면 그건 파서 테스트가 아니라 저장소 스냅샷이다.

🔴 **모집단이 둘이라는 것이 이 파서의 핵심 계약**이다(`D43` — 단위가 다르면 둘 다 사실이다):
- **라우팅 모집단** = `### ID.` 전부. `A4`(안전 패턴)처럼 실수가 아닌 것도 **축으로는 라우팅된다.**
- **예방 모집단** = **마커 안**. *"이 실수를 무엇이 막나"* 가 성립하는 것만.
"""

from pathlib import Path

import pytest

from scripts.gates.doc.mistake_ledger import (
    MARKER_END,
    MARKER_START,
    MarkerError,
    parse_ledger,
    parse_prevention,
)

#: 코드 펜스 표식. 소스에 완성형을 안 남기려고 조립한다(대장 D10).
FENCE = chr(96) * 3

#: 표본 대장. 마커 **밖**에 실수가 아닌 항목(`Z9`)을 두어 두 모집단이 갈리는지 본다.
SAMPLE = """\
# 표본 대장

## ★ 상시 세트

### 절 제목일 뿐 ID 가 없다

<!-- 대장-항목 시작 -->

## 분류 A

### A1. 첫 항목
**축**: `셸-원격실행`
**예방**: `기계` `훅:no-ai-trailers`

- 본문.

### D67. 번호식 항목
**축**: `문서-닫기`
**예방**: `없음`

- 본문에서 **예방**: 을 인용해도 메타로 읽으면 안 된다.

### G1. 다른 계열
**축**: `프론트엔드`

- 예방이 없는 항목.

<!-- 대장-항목 끝 -->

## ☑ 안전 패턴

### Z9. 실수가 아니다
**축**: `셸-원격실행`

- 마커 밖.
"""


def write(tmp_path: Path, text: str) -> Path:
    """표본을 파일로 떨군다.

    Args:
        tmp_path: pytest 임시 디렉터리.
        text: 대장 본문.

    Returns:
        만들어진 파일 경로.
    """
    target = tmp_path / "ledger.md"
    target.write_text(text, encoding="utf-8")
    return target


# ── 모집단 ────────────────────────────────────────────────────────────
# 흐름: 표본 작성 -> parse_ledger -> 라우팅/예방 두 모집단 대조
def test_routing_population_includes_entries_outside_markers(tmp_path: Path) -> None:
    """라우팅 모집단은 **마커 밖 항목도 센다** — 축은 거기서도 읽혀야 한다."""
    ledger = parse_ledger(write(tmp_path, SAMPLE))

    assert [e.id for e in ledger.entries] == ["A1", "D67", "G1", "Z9"]


def test_prevention_population_is_markers_only(tmp_path: Path) -> None:
    """예방 모집단은 **마커 안뿐**이다 — 실수가 아닌 것에 값을 강요하지 않는다."""
    ledger = parse_ledger(write(tmp_path, SAMPLE))

    assert [e.id for e in ledger.population] == ["A1", "D67", "G1"]


def test_missing_marker_is_an_error_not_an_empty_population(tmp_path: Path) -> None:
    """🔴 마커가 없으면 **실패**다 — 빈 모집단을 돌려주면 게이트가 0건을 초록으로 본다."""
    with pytest.raises(MarkerError):
        parse_ledger(write(tmp_path, SAMPLE.replace("<!-- 대장-항목 끝 -->", "")))


# ── 형식 이탈 탐지 ────────────────────────────────────────────────────
# 흐름: ID 없는 `### ` 를 마커 안에 넣기 -> 헤딩 총수 > ID 수
def test_heading_count_exposes_id_less_entries(tmp_path: Path) -> None:
    """🔴 마커 안 `### ` 총수와 ID 매치 수가 갈리면 **조용히 빠져나간 항목**이 있다."""
    broken = SAMPLE.replace("### G1. 다른 계열", "### D68·D45 합동 재발")
    ledger = parse_ledger(write(tmp_path, broken))

    assert ledger.headings_in_population == 3
    assert len(ledger.population) == 2


def test_clean_ledger_has_matching_counts(tmp_path: Path) -> None:
    """음성 대조 — 정상 표본에서는 두 수가 같다."""
    ledger = parse_ledger(write(tmp_path, SAMPLE))

    assert ledger.headings_in_population == len(ledger.population)


# ── 필드 ──────────────────────────────────────────────────────────────
def test_axis_is_read_from_the_meta_block(tmp_path: Path) -> None:
    """`**축**:` 을 항목마다 읽는다."""
    ledger = parse_ledger(write(tmp_path, SAMPLE))

    assert {e.id: e.axis for e in ledger.entries}["A1"] == "셸-원격실행"


def test_entry_without_prevention_reports_none(tmp_path: Path) -> None:
    """예방이 없으면 `None` — 빈 문자열로 뭉개면 «없음» 값과 구별이 안 된다."""
    ledger = parse_ledger(write(tmp_path, SAMPLE))

    assert {e.id: e.prevention for e in ledger.entries}["G1"] is None


def test_body_prose_is_not_read_as_metadata(tmp_path: Path) -> None:
    """🔴 메타 블록은 **헤딩 직후 연속 줄까지**다 — 본문이 필드명을 인용해도 안 먹는다."""
    ledger = parse_ledger(write(tmp_path, SAMPLE))
    d67 = next(e for e in ledger.entries if e.id == "D67")

    assert d67.prevention is not None
    assert d67.prevention.value == "없음"


# ── 예방 값 파싱 ──────────────────────────────────────────────────────
# 흐름: 한 줄 -> (값, 참조, 형식위반)
def test_prevention_with_reference() -> None:
    """`기계` 는 종류 태그를 동반한다."""
    parsed = parse_prevention("**예방**: `기계` `훅:no-ai-trailers`")

    assert parsed is not None
    assert parsed.value == "기계"
    assert parsed.reference == "훅:no-ai-trailers"
    assert not parsed.malformed


def test_prevention_without_reference() -> None:
    """`없음` 은 동반값을 갖지 않는다."""
    parsed = parse_prevention("**예방**: `없음`")

    assert parsed is not None
    assert parsed.reference is None
    assert not parsed.malformed


def test_prose_tail_is_malformed() -> None:
    """🔴 괄호·산문 꼬리는 **형식 위반**이다 — 참조를 기계가 못 대조한다."""
    parsed = parse_prevention("**예방**: `절차` (`CLAUDE.md` §6-4 문장 교정 — 기계는 없다)")

    assert parsed is not None
    assert parsed.malformed


def test_non_prevention_line_returns_none() -> None:
    """다른 줄은 `None` — 파서가 아무 줄이나 먹으면 무엇을 셌는지 알 수 없다."""
    assert parse_prevention("**축**: `문서-닫기`") is None


def test_marker_quoted_in_prose_is_not_a_boundary(tmp_path: Path) -> None:
    """🔴 산문이 마커를 **인용**해도 경계로 읽지 않는다 — 「포함」이 아니라 「그 줄 전체」다.

    실제로 대장 §0 이 마커를 백틱으로 설명하자마자 파서가 거기서 멈췄다(D47: 앵커 없는 패턴).
    """
    quoted_start = "`" + MARKER_START + "`"
    quoted_end = "`" + MARKER_END + "`"
    prose = f"설명: {quoted_start} 와 {quoted_end} 사이가 모집단이다." + chr(10) * 2

    ledger = parse_ledger(write(tmp_path, prose + SAMPLE))

    assert [e.id for e in ledger.population] == ["A1", "D67", "G1"]


def test_headings_inside_code_fence_are_examples(tmp_path: Path) -> None:
    """🔴 펜스 안 헤딩은 **예시**지 항목이 아니다.

    규약을 설명하는 문서는 자기 형식을 반드시 인용하게 되어 있다. 그 인용을 항목으로 세면
    **ID 가 중복돼 dict 에서 뭉개지고**, 총수와 축 합이 조용히 갈린다(D69).
    """
    example = chr(10).join([FENCE, "### D67. 예시일 뿐이다", "**축**: `문서-닫기`", FENCE, "", ""])
    ledger = parse_ledger(write(tmp_path, example + SAMPLE))

    assert [e.id for e in ledger.entries] == ["A1", "D67", "G1", "Z9"]
