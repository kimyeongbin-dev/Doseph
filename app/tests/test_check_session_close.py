"""세션 종료 가능 여부 검사기의 단위 테스트.

**왜 이게 있나**

*"지금 `/clear` 해도 잃을 게 없다"* 를 **기억으로 판단해 틀렸다**(2026-09-15).
실제로는 5개가 안 적혀 있었다 — PLAN 상태줄·진행 현황·`CLAUDE.md` 규칙 2개·대장 D34.

사용자 지시: **판단을 기억으로 하지 말고 명령으로 하되, 그 명령은 확실해야 한다.
즉석 `grep` 같은 불확실한 것은 안 된다**(대장 D31 의 연장 — 급조한 정규식은
정본 검증기보다 덜 엄밀한 두 번째 구현이 된다).

그래서 이 검사기는 **두 종류만** 판정한다:

1. **git 이 답하는 것** — 작업물이 파일·원격에 실제로 들어갔는가.
   git 은 이 질문의 정본이다. 추측이 개입할 여지가 없다.
2. **파일 구조가 답하는 것** — 진행 중 PLAN 에 "다음에 무엇을 하는가" 가
   적혀 있는가. 문장 해석이 아니라 **절의 존재** 를 본다.

그리고 **판정할 수 없는 것은 판정하지 않는다.** ``/clear`` 가 지우는 것은
대화 컨텍스트뿐이고, *내 머릿속에만 있고 파일에 없는 것*이 무엇인지는
기계가 열거할 수 없다. 그건 출력해서 **사람에게 묻는다**.
"""

from pathlib import Path

from scripts.check_session_close import (
    find_in_progress_plans,
    git_is_clean,
    plan_has_next_step,
)


# ── git 상태 (git 이 정본) ────────────────────────────────────────────
# 흐름: porcelain/ahead/stash 세 값 -> 전부 0이어야 깨끗
def test_git_clean_requires_all_three_to_be_empty() -> None:
    """작업 트리·미푸시 커밋·stash 가 **전부** 비어야 깨끗하다."""
    assert git_is_clean(dirty=[], unpushed=0, stashes=0) is True


def test_dirty_working_tree_is_not_clean() -> None:
    """커밋 안 된 변경이 있으면 깨끗하지 않다."""
    assert git_is_clean(dirty=["app/x.py"], unpushed=0, stashes=0) is False


def test_unpushed_commit_is_not_clean() -> None:
    """커밋했어도 **푸시 전이면** 원격에 없다 — 로컬 사고 시 잃는다."""
    assert git_is_clean(dirty=[], unpushed=1, stashes=0) is False


def test_stash_is_not_clean() -> None:
    """stash 는 잊히는 대표적인 자리다 — 있으면 깨끗하지 않다.

    `git status` 는 stash 를 보여주지 않는다. 그래서 눈으로 보는 확인에서
    구조적으로 빠진다.
    """
    assert git_is_clean(dirty=[], unpushed=0, stashes=1) is False


# ── 진행 중 PLAN 찾기 (파일 구조가 정본) ─────────────────────────────
# 흐름: PLAN_*.md 수집 -> 상태줄에 진행 표식이 있는 것만
def test_in_progress_plan_is_detected(tmp_path: Path) -> None:
    """상태줄이 '진행 중' 인 PLAN 을 골라낸다."""
    plan = tmp_path / "PLAN_SAMPLE.md"
    plan.write_text("| **상태** | 🟢 **진행 중** — S1 완료 |\n", encoding="utf-8")

    assert find_in_progress_plans(tmp_path) == [plan]


def test_finished_plan_is_ignored(tmp_path: Path) -> None:
    """완료된 PLAN 은 대상이 아니다 — 닫힌 것까지 세면 경보가 소음이 된다."""
    (tmp_path / "PLAN_DONE.md").write_text("| **상태** | ✅ **완료 (2026-09-15)** |\n", encoding="utf-8")

    assert find_in_progress_plans(tmp_path) == []


def test_snapshot_directory_is_not_scanned(tmp_path: Path) -> None:
    """`_legacy` 스냅샷은 과거 기록이다 — 진행 중으로 세면 영원히 빨갛다."""
    legacy = tmp_path / "_legacy"
    legacy.mkdir()
    (legacy / "2026-09-15_PLAN_X.snapshot.md").write_text("| **상태** | 🟢 **진행 중** |\n", encoding="utf-8")

    assert find_in_progress_plans(tmp_path) == []


# ── 다음 단계가 적혀 있는가 (절의 존재만 본다) ───────────────────────
# 흐름: PLAN 본문에 진행 현황 절이 있는지 -> 문장 해석은 하지 않는다
def test_plan_with_progress_section_passes(tmp_path: Path) -> None:
    """'진행 현황' 절이 있으면 통과 — 내용의 옳고 그름은 판정하지 않는다."""
    plan = tmp_path / "PLAN_SAMPLE.md"
    plan.write_text("| **상태** | 🟢 진행 중 |\n\n## 13. 진행 현황\n\n| S2 | 다음 |\n", encoding="utf-8")

    assert plan_has_next_step(plan) is True


def test_plan_without_progress_section_fails(tmp_path: Path) -> None:
    """진행 중인데 어디까지 했는지 적혀 있지 않으면 **이어갈 수 없다**."""
    plan = tmp_path / "PLAN_SAMPLE.md"
    plan.write_text("| **상태** | 🟢 진행 중 |\n\n## 1. 목표\n", encoding="utf-8")

    assert plan_has_next_step(plan) is False
