"""원장 «다음 신규» 게이트 단위 테스트 (트랙 B-14 검증 구간).

⚠️ `tmp_path` 가 필요 없다 — `audit()` 이 **본문 문자열만** 받는다. 저장소 상태를 읽으면
그건 게이트 테스트가 아니라 저장소 스냅샷이다.

🔴 **이 게이트가 존재하는 이유**: `DOC_TRUTH_DRIFT` 의 «다음 신규» 줄이 **5번 연속** 어긋났고,
원장이 정정 배너를 **3개** 달아 두고도 또 틀렸다. 2026-09-21 배너는 원인까지 규명해
*「손으로 유지하는 다음 번호는 구조적으로 썩는다」* 고 적었는데 **줄은 그대로 남았다** —
산문은 조치가 아니다.

🔑 **핵심 음성 대조 = 산문 인용을 선언으로 세지 않는다**(대장 `D69`).
같은 문자열이 «과거에 이 줄이 틀렸던 일» 을 설명하는 산문으로 3곳 더 있다.
"""

import re

from scripts.gates.doc.check_ledger_next_id import Ledger, audit, issued_ids

DRIFT = Ledger(
    path="표본.md",
    prefix="문서",
    declare=re.compile(r"^\*\*다음 신규 = `문서-(?P<n>\d+)`", re.MULTILINE),
    floor=3,
)


def body(rows: list[str], declared: int, extra: str = "") -> str:
    """표본 원장 본문을 만든다.

    Args:
        rows: 표 행들.
        declared: «다음 신규» 로 선언할 번호.
        extra: 뒤에 붙일 산문.

    Returns:
        원장 본문 문자열.
    """
    head = "| ID | 내용 |\n|---|---|\n"
    tail = f"\n**다음 신규 = `문서-{declared}`.** (ID 는 재사용하지 않는다)\n"
    return head + "\n".join(rows) + tail + extra


ROWS = [
    "| **문서-1** | 첫째 |",
    "| **문서-2** | 둘째 |",
    "| **문서-3** | 셋째 |",
]


# ── 음성 대조 — 정상 표본은 통과해야 한다 ────────────────────────────
def test_correct_declaration_passes() -> None:
    """선언이 최대+1 이면 통과한다."""
    problem, summary = audit(DRIFT, body(ROWS, 4))
    assert problem is None, problem
    assert "최대 3" in summary


def test_prose_quotation_is_not_counted_as_a_declaration() -> None:
    """🔴 **산문 인용은 선언이 아니다** — 줄 머리가 아니면 안 센다(`D69`).

    같은 문자열을 인용한 산문이 있어도 선언은 **여전히 1건**이라 통과해야 한다.
    """
    quoted = '\n> 🔴 정정 — 이 줄이 *"다음 신규 = `문서-99`"* 라고 말하고 있었다.\n'
    problem, _ = audit(DRIFT, body(ROWS, 4, extra=quoted))
    assert problem is None, problem


def test_struck_row_still_counts_as_issued() -> None:
    """🔴 **취소선 행도 번호는 쓴 것이다**(`D58`).

    `문서-4` 가 취소선이면 최대는 4 이고 다음은 5 다 — 빼고 세면 4 를 다시 내준다.
    """
    rows = [*ROWS, "| ~~**문서-4**~~ | 취소됨 |"]
    assert issued_ids("\n".join(rows), "문서") == {1, 2, 3, 4}
    problem, _ = audit(DRIFT, body(rows, 5))
    assert problem is None, problem


def test_heading_form_is_counted_too() -> None:
    """표 행과 **제목형** 두 형식 다 센다(`FILING` §3-3 규칙 3)."""
    assert issued_ids("## 문서-7 — 제목\n", "문서") == {7}


# ── 결핍 주입 — 막아야 할 것을 일부러 넣는다 ─────────────────────────
def test_stale_declaration_is_caught() -> None:
    """선언이 이미 발급된 번호를 가리키면 막는다 — **이 게이트의 존재 이유**."""
    sample = body(ROWS, 2)
    assert "다음 신규 = `문서-2`" in sample  # 🔴 주입이 실제로 들어갔는지 단언한다(D46)
    problem, _ = audit(DRIFT, sample)
    assert problem is not None
    assert "이미 문서-3 까지 발급" in problem


def test_missing_declaration_is_fail_closed() -> None:
    """선언이 0건이면 «선언이 없다» 가 아니라 **앵커가 깨진 것**으로 본다."""
    problem, _ = audit(DRIFT, "| ID | 내용 |\n" + "\n".join(ROWS))
    assert problem is not None
    assert "앵커가 깨졌다" in problem


def test_duplicate_declaration_is_caught() -> None:
    """선언이 2건이면 어느 쪽이 정본인지 모른다 — 막는다."""
    problem, _ = audit(DRIFT, body(ROWS, 4) + "\n**다음 신규 = `문서-9`.**\n")
    assert problem is not None
    assert "모호하다" in problem


def test_floor_catches_a_broken_row_parser() -> None:
    """발급 수가 바닥값 아래면 막는다 — **0건은 «깨끗함» 이 아니다**."""
    problem, _ = audit(DRIFT, body(ROWS[:1], 2))
    assert problem is not None
    assert "바닥값 3 아래" in problem
