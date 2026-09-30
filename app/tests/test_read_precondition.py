"""`read_precondition` 훅 단위 테스트 (`QA-50`).

⚠️ `MARKER_ROOT` 를 `tmp_path` 로 갈아끼운다 — 실제 세션 마커를 건드리면
그건 훅 테스트가 아니라 **내 세션을 망가뜨리는 것**이다.

🔑 **이 훅이 막는 것이 무엇인지가 2026-09-29 에 바뀌었다.** 앞 판은
*"한 번도 안 읽고 고치는 것"* 만 막았다. 읽음 마커가 압축을 그냥 살아남았기 때문인데,
**읽은 «내용» 은 압축 요약에서 탈락한다**(2026-09-22 실측: 본문 0줄).
그래서 압축 후 첫 편집이 **보증이 빈 채로 통과**했다.

이제 `PostCompact` 가 읽음 마커에 **«압축됨» 을 새긴다.** 🔴 **지우지 않고 새기는 이유**는
「한 번도 안 읽었다」 와 「읽었는데 압축이 내용을 지웠다」 를 **다른 문장으로** 말하기 위해서다.
"""

from pathlib import Path

import pytest

from scripts.hooks import read_precondition as hook

SID = "s1"
DOC = "E:/repo/docs-private/ROADMAP.md"
FILING = "E:/repo/docs-private/FILING.md"


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  """마커 뿌리를 임시 폴더로 갈아끼운다.

  Args:
      tmp_path: pytest 임시 디렉터리.
      monkeypatch: 속성 교체기.
  """
  monkeypatch.setattr(hook, "MARKER_ROOT", tmp_path / "markers")


def edit(path: str = DOC) -> dict[str, object] | None:
  """편집 시도 하나를 판정시킨다.

  Args:
      path: 고치려는 파일 경로.

  Returns:
      훅 출력.
  """
  return hook.decide({"session_id": SID, "tool_name": "Edit", "tool_input": {"file_path": path}})


def read(path: str = FILING) -> dict[str, object] | None:
  """읽기 하나를 통과시킨다.

  Args:
      path: 읽는 파일 경로.

  Returns:
      훅 출력.
  """
  return hook.decide({"session_id": SID, "tool_name": "Read", "tool_input": {"file_path": path}})


def reason(out: dict[str, object] | None) -> str:
  """차단 사유 문자열. 차단이 아니면 빈 문자열.

  Args:
      out: 훅 출력.

  Returns:
      사유 문자열.
  """
  if not isinstance(out, dict):
    return ""
  spec = out.get("hookSpecificOutput")
  if not isinstance(spec, dict) or spec.get("permissionDecision") != "deny":
    return ""
  return str(spec.get("permissionDecisionReason", ""))


# ── 결핍 주입 — 막아야 하는 것 ──────────────────────────────────────
def test_editing_without_reading_is_denied() -> None:
  """한 번도 안 읽었으면 막는다."""
  assert "먼저 읽어라" in reason(edit())


def test_editing_after_compaction_is_denied() -> None:
  """🔴 `QA-50` — 압축은 읽은 «내용» 을 지우므로 보증도 무른다."""
  read()
  assert edit() is not None  # 주입되고 통과
  hook.reset_after_compaction(SID)
  assert "압축 이후 첫" in reason(edit())


def test_the_two_denials_say_different_things() -> None:
  """🔑 지우지 않고 «새기는» 이유가 바로 이것이다 — 왜 막혔는지 말할 수 있어야 한다."""
  never = reason(edit())
  read()
  edit()
  hook.reset_after_compaction(SID)
  compacted = reason(edit())
  assert never
  assert compacted
  assert never != compacted


# ── 음성 대조 — 막으면 안 되는 것 ───────────────────────────────────
def test_reading_then_editing_passes_and_injects_once() -> None:
  """읽었으면 통과하고, 상시 세트는 **세션당 한 번만** 주입한다."""
  read()
  first = edit()
  assert isinstance(first, dict)
  spec = first["hookSpecificOutput"]
  assert isinstance(spec, dict)
  assert "additionalContext" in spec
  assert edit() is None, "두 번째 편집에 같은 문구를 또 넣으면 낭비다"


def test_reading_again_clears_the_compaction_mark() -> None:
  """다시 읽으면 보증이 되살아난다 — 안 그러면 영영 막힌다."""
  read()
  edit()
  hook.reset_after_compaction(SID)
  read()
  assert reason(edit()) == "", "다시 읽었는데 막으면 오탐이다"


def test_unfiled_and_outside_paths_are_never_gated() -> None:
  """규약 밖 구역과 `docs-private/` 밖은 묻지 않는다."""
  assert edit("E:/repo/docs-private/_unfiled/a.md") is None
  assert edit("E:/repo/docs-private/_legacy/b.md") is None
  assert edit("E:/repo/app/main.py") is None
  assert edit("E:/repo/docs-private/notes.txt") is None


# ── `PostCompact` 자체 ──────────────────────────────────────────────
def test_reset_drops_injection_and_marks_the_read() -> None:
  """주입 기록은 **지우고**, 읽음 기록은 **새긴다**."""
  read()
  edit()
  assert hook.marker_path(SID, hook.INJECTED).exists()
  hook.reset_after_compaction(SID)
  assert not hook.marker_path(SID, hook.INJECTED).exists()
  assert hook.marker_path(SID, hook.GATED_DOC).read_text(encoding="utf-8") == hook.COMPACTED


def test_reset_is_safe_when_nothing_was_read() -> None:
  """압축이 두 번 와도, 아무것도 안 읽었어도 죽지 않는다."""
  assert hook.reset_after_compaction(SID) == 0
  assert hook.reset_after_compaction(SID) == 0
  assert not hook.marker_path(SID, hook.GATED_DOC).exists()


def test_reset_without_a_session_sweeps_every_folder() -> None:
  """`session_id` 가 비면 모든 세션을 훑는다."""
  read()
  edit()
  assert hook.reset_after_compaction("") == 0
  assert hook.marker_path(SID, hook.GATED_DOC).read_text(encoding="utf-8") == hook.COMPACTED
