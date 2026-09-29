"""«경위의 수» 검사 단위 테스트 (트랙 B-11 3구간 S1).

🔴 **왜 이 검사가 있나**: 3구간은 층②의 **문장을 다시 쓴다.** 그런데 재작성은
*«실측 72건»*·*«2회 위반»*·*«12건을 날렸다»* 같은 **경위의 수를 가장 먼저 지운다** —
문장을 줄이는 가장 쉬운 방법이 괄호 안의 실측치를 빼는 것이기 때문이다.

🔑 **그 수들이 규칙을 되돌리지 못하게 만든다.** 경위가 없으면 규칙은 취향이 되고,
취향은 다음 사람이 뒤집는다(대장 `D30` 이 실증한 형태다).

⚠️ 여기서는 **패턴만** 잠근다. 바닥값 자체는 저장소 상태라 게이트가 본다 —
테스트에 그 수를 박으면 그건 게이트 테스트가 아니라 **저장소 스냅샷**이다.
"""

from scripts.gates.doc.check_rule_enforcement import EVIDENCE


def count(text: str) -> int:
    """그 글에서 «경위의 수» 를 센다.

    Args:
        text: 검사할 글.

    Returns:
        찾은 개수.
    """
    return len(EVIDENCE.findall(text))


# ── 무엇을 세는가 ───────────────────────────────────────────────────
def test_measured_numbers_with_korean_units_are_counted() -> None:
    """실제 층② 문장에서 가져온 표본 — 전부 세어야 한다."""
    assert count("참조 20곳이 그렇게 깨졌다") == 1
    assert count("12건을 날렸다, 대장 D37") == 1
    assert count("게이트 20개 중 단위테스트를 가진 것은 2개뿐이었다") == 2
    assert count("2026-09-15 실측 위반 72건(서비스→모델 31 등)") == 1
    assert count("게이트 단위테스트 181건이 빠진다") == 1
    assert count("**파일 300줄**") == 1


def test_units_found_by_survey_are_counted() -> None:
    """🔴 손으로 지은 단위 목록은 빈다 — 실측으로 메운 다섯 종을 잠근다.

    🔬 2026-09-30 S2 조사에서 `커밋` 이 빠져 있던 것이 드러났다. *«10커밋 · 23커밋»* 은
    이 저장소에서 **가장 많이 인용되는 경위**인데 계측기에 안 보였다.
    메우고 나니 층② 실측이 `58` → `70` 으로 올랐다 — **20%가 사각지대**였다.
    """
    assert count("2026-09-13 10커밋 · 2026-09-15 23커밋") == 2
    assert count("«다 기록했나» 는 2패스다") == 1
    assert count("import 정렬·3그룹") == 1
    assert count("2 패턴 vs 13 import") == 1


def test_korean_numerals_are_deliberately_not_counted() -> None:
    """⚠️ **한계 선언** — `한`·`두`·`세` 는 안 센다.

    실측 `10`개가 있고 *«두 번 위반됐다»* 처럼 진짜 경위도 있다. 그런데 *«위 두 줄»* ·
    *«한 줄 요약»* 은 **구조 서술**이라, 넣으면 **바닥값이 소음을 지키게 된다.**
    ⇒ 세지 않는 대신 **그 문장들을 재작성 대상에서 뺀다.**
    """
    assert count("두 번 위반됐다") == 0
    assert count("위 두 줄이다") == 0


def test_a_bare_year_or_section_number_is_not_evidence() -> None:
    """🔴 단위가 없는 숫자는 안 센다 — 표제 번호와 날짜가 신호를 죽인다.

    🔬 실측 2026-09-30: 층②의 숫자 토큰 `391`개 중 표제 번호만 `74`개였다.
    그래서 «숫자 + 단위» 로 좁혔다.
    """
    assert count("## 6-2-1. 읽은 문서가 어긋나면") == 0
    assert count("사용자 결정 2026-09-28") == 0
    assert count("`QA-50` 과 `문서-46`") == 0


# ── 🔑 이 검사가 실제로 무엇을 막는가 ───────────────────────────────
def test_shortening_a_sentence_is_allowed_when_the_numbers_survive() -> None:
    """🟢 **음성 대조** — 3구간이 하려는 일 자체는 막으면 안 된다."""
    before = "⚠️ 레이어는 «계약에 든 경계만» 강제된다 — 2026-09-15 실측 위반 72건(서비스→모델 31 등)은"
    after = "레이어는 계약에 든 경계만 강제된다 — 위반 72건(서비스→모델 31)"
    assert len(after) < len(before), "표본이 실제로 짧아야 한다"
    assert count(after) == count(before)


def test_dropping_the_measurement_is_caught() -> None:
    """🔴 **결핍 주입** — 수를 지우면 개수가 준다. 그것이 유일한 신호다."""
    before = "게이트 20개 중 단위테스트를 가진 것은 2개뿐이었다"
    after = "게이트 대부분이 단위테스트가 없었다"
    assert count(after) < count(before)


def test_the_floor_cannot_see_a_swap() -> None:
    """⚠️ **한계 선언** — 하나를 지우고 하나를 넣으면 총량이 같아 못 본다.

    게이트 docstring 이 같은 말을 적고 있다. 한 건 단위 보호는 **검토로 남겼다** —
    기준선 파일은 손으로 유지하는 수를 `37`개 만들고, 그건 `문서-49` 가 잡은 실패다.
    """
    before = "실측 위반 72건이다"
    after = "실측 대상 9개다"
    assert count(after) == count(before), "이 한계를 모르는 채로 쓰면 안 된다"
