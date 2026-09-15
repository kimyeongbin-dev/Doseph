"""세션을 닫아도(``/clear``) 잃을 게 없는지 **명령으로** 판정한다.

수동 실행: ``uv run python scripts/check_session_close.py``

왜 이게 있나
------------
*"지금 `/clear` 해도 잃을 게 없습니다"* 를 **기억으로 판단해 틀렸다**(2026-09-15).
사용자가 *"정말 잃을 게 없어?"* 라고 되묻자 세어 봤고, **5개가 안 적혀 있었다** —
PLAN 상태줄 · 진행 현황 절 · `CLAUDE.md` 규칙 2개 · 대장 D34.

사용자 지시: **판단을 기억이 아니라 명령으로 하되, 그 명령은 확실해야 한다.
즉석 ``grep`` 같은 불확실한 것은 안 된다.** (대장 D31 의 연장 — 급조한 정규식은
정본 검증기보다 **덜 엄밀한 두 번째 구현**이 된다.)

무엇을 판정하고 무엇을 판정하지 않나
------------------------------------
**판정한다 (정본이 답하는 것만)**

1. **git 상태** — 작업 트리가 깨끗한가 · 미푸시 커밋이 있는가 · **stash 가 있는가**.
   git 이 이 질문의 정본이다. ``git status`` 는 stash 를 보여주지 않으므로
   눈으로 보는 확인에서는 구조적으로 빠진다.
2. **정본 게이트 재실행** — 앵커 · 폐기 어휘 · PLAN 아카이브.
   여기서 규칙을 **다시 구현하지 않는다.** 이미 있는 검증기를 그대로 호출한다(D31).
3. **진행 중 PLAN 에 이어갈 지점이 적혀 있는가** — 문장을 해석하지 않고
   *"진행 현황" 절의 존재*만 본다. 구조는 확실하고 문장 해석은 불확실하다.

**판정하지 않는다 (기계가 알 수 없는 것)**

``/clear`` 가 지우는 것은 **대화 컨텍스트뿐**이고 파일은 남는다. 그러므로 잃는 것은
오직 *"내 머릿속에만 있고 파일에 없는 것"* 인데, **그게 무엇인지는 기계가 열거할 수
없다.** 그래서 이 스크립트는 그 항목을 **질문으로 출력**하고 사람이 답하게 한다.
여기에 ``grep`` 을 붙여 "기록됐다" 를 자동 판정하는 순간 **거짓 안심**이 된다.
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess  # git·게이트 재실행에 필요. 입력은 전부 리터럴이다.
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRIVATE_DIR = Path("docs-private")
SNAPSHOT_DIR_NAME = "_legacy"

#: 상태줄이 이 표식을 담고 있으면 "진행 중" 으로 본다.
IN_PROGRESS_MARKS = ("🟢", "진행 중")

#: 진행 중 PLAN 이 반드시 가져야 하는 절. 없으면 다음 세션이 이어갈 수 없다.
PROGRESS_SECTION = "진행 현황"

#: 이미 있는 정본 검증기들. **여기서 규칙을 다시 구현하지 않는다.**
AUTHORITATIVE_GATES = (
    ("QA 앵커 유효성", "scripts/check_anchors.py"),
    ("폐기 어휘 잔존", "scripts/check_comment_staleness.py"),
    ("PLAN 아카이브 누락", "scripts/check_plan_archives.py"),
)

#: 기계가 답할 수 없어 **사람에게 묻는** 항목.
HUMAN_ONLY_QUESTIONS = (
    "이번 세션에서 내린 결정·합의가 파일에 적혔는가 (기억에만 있지 않은가)",
    "새로 발견한 결함이 후속 큐 또는 부채 원장에 등재됐는가",
    "새로 한 실수가 실수·오류 대장에 등재됐는가",
    "새로 배운 개념이 docs-private/study/ 에 남았는가",
)


@dataclass(frozen=True)
class GitState:
    """git 이 답한 사실."""

    dirty: list[str]
    #: ``None`` = 알아내지 못했다 (upstream 미설정 등). **0 과 구별해야 한다.**
    unpushed: int | None
    stashes: int


# ── git 상태 판정 ─────────────────────────────────────────────────────
# 흐름: 세 값 -> 하나라도 비어 있지 않으면 "잃을 것이 있다"
# ⚠️ unpushed 가 None(알 수 없음)이면 **깨끗하다고 하지 않는다**(fail-closed).
#    모르는 것을 0 으로 읽으면 그게 곧 거짓 초록이다.
def git_is_clean(dirty: list[str], unpushed: int | None, stashes: int) -> bool:
    """Return whether nothing is left only on this machine.

    Args:
        dirty: Uncommitted paths from ``git status --porcelain``.
        unpushed: Commits ahead of upstream, or ``None`` when unknown.
        stashes: Entries in ``git stash list``.

    Returns:
        True only when all three are known and empty.
    """
    return not dirty and unpushed == 0 and stashes == 0


def read_git_state() -> GitState:
    """Ask git for the current state.

    Returns:
        Working tree, upstream and stash facts.
    """

    def run(*args: str) -> tuple[int, str]:
        result = subprocess.run(  # 인자가 전부 리터럴이라 셸 주입 여지가 없다.
            ["git", *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout.strip()

    _, status_out = run("status", "--porcelain")
    dirty = [line for line in status_out.splitlines() if line]

    # ⚠️ upstream 이 없으면 이 명령은 **exit 128** 로 죽고 stdout 은 비어 있다(실측).
    #    종료 코드를 안 보고 출력만 읽으면 "0건" 으로 오해해 거짓 초록이 된다.
    #    모르는 것은 0 이 아니라 **None** 으로 돌려준다.
    code, unpushed_out = run("rev-list", "--count", "@{u}..HEAD")
    unpushed = int(unpushed_out) if code == 0 and unpushed_out.isdigit() else None

    _, stash_out = run("stash", "list")
    return GitState(dirty=dirty, unpushed=unpushed, stashes=len([x for x in stash_out.splitlines() if x]))


# ── 진행 중 PLAN 찾기 ─────────────────────────────────────────────────
# 흐름: PLAN_*.md 수집(_legacy 스냅샷 제외) -> 상태줄에 진행 표식이 있는 것만
def find_in_progress_plans(directory: Path) -> list[Path]:
    """Find PLAN documents whose status line says work is ongoing.

    Args:
        directory: Directory holding PLAN documents.

    Returns:
        Paths of in-progress PLANs, sorted.
    """
    if not directory.is_dir():
        return []

    found: list[Path] = []
    for path in sorted(directory.glob("PLAN_*.md")):
        if SNAPSHOT_DIR_NAME in path.parts:
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "상태" not in line:
                continue
            if any(mark in line for mark in IN_PROGRESS_MARKS):
                found.append(path)
            break
    return found


# ── 이어갈 지점이 적혀 있는가 ────────────────────────────────────────
# 흐름: 본문에 "진행 현황" 절이 있는지만 본다 — 내용의 옳고 그름은 판정하지 않는다
def plan_has_next_step(path: Path) -> bool:
    """Return whether the PLAN records where to resume.

    Args:
        path: PLAN document.

    Returns:
        True when a progress section heading exists.
    """
    return any(
        line.startswith("#") and PROGRESS_SECTION in line
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
    )


def _run_gate(script: str) -> bool:
    """Run an existing authoritative gate and report its verdict."""
    result = subprocess.run(  # 인자가 전부 리터럴이다.
        [sys.executable, script],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0


def main() -> int:
    """수동 실행 진입점.

    Returns:
        기계가 판정 가능한 항목이 전부 통과하면 0, 아니면 1.
    """
    blocked: list[str] = []

    state = read_git_state()
    if git_is_clean(state.dirty, state.unpushed, state.stashes):
        print("✅ git — 작업 트리 깨끗 · 미푸시 0 · stash 0")
    else:
        print("🔴 git — 이 기계에만 있는 작업이 있다")
        for path in state.dirty:
            print(f"     미커밋: {path}")
        if state.unpushed is None:
            print("     미푸시 커밋: 알 수 없음 (upstream 미설정 — 모르는 것을 0 으로 읽지 않는다)")
        elif state.unpushed:
            print(f"     미푸시 커밋: {state.unpushed}건")
        if state.stashes:
            print(f"     stash: {state.stashes}건  (git status 에는 안 보인다)")
        blocked.append("git")

    for label, script in AUTHORITATIVE_GATES:
        if _run_gate(script):
            print(f"✅ {label}")
        else:
            print(f"🔴 {label} — `{script}` 를 직접 돌려 내용을 확인한다")
            blocked.append(label)

    for plan in find_in_progress_plans(PRIVATE_DIR):
        if plan_has_next_step(plan):
            print(f"✅ 진행 중 PLAN 에 이어갈 지점 있음 — {plan.as_posix()}")
        else:
            print(f"🔴 진행 중인데 '{PROGRESS_SECTION}' 절이 없다 — {plan.as_posix()}")
            blocked.append(plan.name)

    print("\n── 기계가 판정할 수 없는 것 (사람이 답한다) ──")
    print("   /clear 는 대화 컨텍스트만 지운다. 잃는 것은 '파일에 없고 내 머릿속에만 있는 것'인데,")
    print("   그게 무엇인지는 기계가 열거할 수 없다. 여기에 grep 을 붙이면 거짓 안심이 된다.\n")
    for question in HUMAN_ONLY_QUESTIONS:
        print(f"   [ ] {question}")

    if blocked:
        print(f"\n🔴 기계 판정 실패: {', '.join(blocked)} — 지금 닫으면 잃는다.")
        return 1

    print("\n✅ 기계가 판정 가능한 항목은 전부 통과. 위 질문 4개는 사람이 답해야 한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
