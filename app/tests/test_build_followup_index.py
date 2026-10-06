"""트랙 상태 판정의 회귀 테스트 — `문서-55` S5.

🔑 **주입 스크립트와 역할이 다르다.** `scripts/injections/track_status_injection.py` 는
*«정본에 결함을 넣으면 게이트가 Red 인가»* 를 묻고(무장 확인), 여기서는 *«판정 함수가
무엇을 열림으로 세는가»* 를 **표본으로 고정**한다. 정본이 바뀌어도 이 계약은 안 바뀐다.
"""

from scripts.gates.doc.build_followup_index import (
  CLOSED_TOKENS,
  OPEN,
  PENDING,
  PROGRESS,
  collect_track_a,
  track_open_count,
)


# ── 열림 어휘 ────────────────────────────────────────────────────────
def test_pending_and_progress_are_not_closed_tokens() -> None:
  """`보류`·`진행` 을 닫힘으로 세면 열린 과제가 조용히 사라진다."""
  assert PENDING not in CLOSED_TOKENS
  assert PROGRESS not in CLOSED_TOKENS
  assert OPEN not in CLOSED_TOKENS


# ── 트랙 판정 ────────────────────────────────────────────────────────
def test_open_count_reads_the_status_token() -> None:
  """상태 칸은 **마지막 셀**이고, 닫힘 어휘가 아니면 열림이다."""
  rows = [
    ("v2.0", ["무료 스택 재배포", "`완료`"]),
    ("v2.1", ["Quick wins", "`부분`"]),
    ("v2.2", ["모노레포", "`보류`"]),
    ("v2.3", ["회귀 안전망", "`진행`"]),
    ("v2.4", ["BE 성능", "`보류` (선행 v2.3)"]),
  ]
  opened, why = track_open_count(rows, "트랙 A")
  assert why is None
  assert opened == 4, "`완료` 하나만 닫힘이다"


def test_a_missing_token_returns_zero_and_a_message() -> None:
  """🔴 fail-closed — 못 센 것을 0 으로 답하지 않는다. 이모지·산문 복귀를 막는 자리다."""
  rows = [
    ("B-7", ["의존성 정리", "`열림` (미착수)"]),
    ("B-8", ["테스트 표준", "🔶 **2구간 완료 2026-09-22**"]),
  ]
  opened, why = track_open_count(rows, "트랙 B")
  assert opened == 0, "토큰이 빠지면 열림 수를 믿을 수 없다"
  assert why is not None
  assert "B-8" in why


def test_done_wording_in_the_body_cell_is_not_a_status() -> None:
  """음성 대조 — 결함과 가장 닮았지만 정상인 표본.

  트랙 C 의 `C-2`·`C-6`·`C-8` 은 내용 셀에 *«완료 2026-09-23»* 산문을 들고 있다.
  상태 칸만 보지 않으면 그 산문이 판정을 뒤집는다(`D47`).
  """
  rows = [("C-10", ["🟠 누적 실재 — 같은 고장의 전례가 있다. 2026-09-20 완료 확인", "중", "`열림`"])]
  opened, why = track_open_count(rows, "트랙 C")
  assert why is None
  assert opened == 1, "내용 셀의 «완료» 는 상태가 아니다"


# ── 트랙 A 수집 ──────────────────────────────────────────────────────
def test_track_a_collection_puts_status_last() -> None:
  """`track_open_count` 가 칸 위치를 추측하지 않도록 수집이 정규화한다."""
  body = "| v2.3   | 회귀 안전망 | 중 | `진행` | 핵심 flow 5종 E2E |\n"
  rows, problems = collect_track_a(body)
  assert problems == []
  assert rows == [("v2.3", ["회귀 안전망", "`진행`"])]


def test_track_a_row_with_too_few_cells_is_reported() -> None:
  """🔴 상태 칸을 특정할 수 없으면 **추측하지 않고 멈춘다**."""
  body = "| v2.9   | 칸이 모자란 행 |\n"
  rows, problems = collect_track_a(body)
  assert rows == []
  assert len(problems) == 1
  assert "v2.9" in problems[0]
