"""E2E 인벤토리 게이트 — **돈 테스트 수가 바닥값 아래로 내려가면 막는다** (B-8 2구간 · QA-08).

왜 «0건» 이 아니라 «줄어든 것» 인가
------------------------------------
🔑 **Playwright 는 0건을 이미 막는다** — 실측(2026-09-22): 수집 0건이면
``Error: No tests found`` 와 함께 **종료코드 1**. 그러니 그걸 또 만들면
**덜 엄밀한 두 번째 구현**이 될 뿐이다(대장 **D31**).

도구가 **안** 막는 것은 이것이다 — **61건이 21건으로 줄어도 종료코드 0** 이다
(같은 실측에서 ``--grep`` 으로 5건만 돌려 확인했다). 이 저장소는 정확히 그 모양으로
한 번 당했다: ``check_utf8_guard`` 의 대상이 **11건 → 1건**이 되고도 초록이었다.

    검사 범위는 조용히 줄어든다. **0건만이 아니라 줄어든 것도 실패로 본다.**

프로젝트 필터 오타 · ``testMatch`` 변경 · 스펙 삭제 · 대량 ``skip`` — 전부 여기로 들어온다.

🔴 이 게이트가 **못 하는 것** (한계 선언 — 안 적으면 초록이 과잉 해석된다)
-------------------------------------------------------------------------
- **테스트가 «옳은지» 를 모른다.** 단언이 0개여도 수만 맞으면 통과한다.
  이 게이트는 **범위 감시**지 품질 측정이 아니다.
- **바닥값은 사람이 올린다.** 테스트가 늘어도 자동으로 안 따라간다 — 일부러다.
  자동 추종은 *"줄어든 것"* 과 *"기준을 낮춘 것"* 을 구별하지 못하게 만든다.
- **`skip` 을 실행으로 세지 않는다.** 데이터 의존 스펙이 조용히 skip 되는 것도
  범위 축소이기 때문이다. 정당한 skip 이 생기면 **바닥값이 아니라 그 스펙을** 고친다.
- **pre-push 는 테스트를 돌리지 않는다**(아래 층 분담).

사용
----
    ... check_e2e_inventory            # CI: 실행 리포트 ↔ 바닥값 대조 (리포트 필요)
    ... check_e2e_inventory verify     # pre-push: E2E **설정**만 검사 (리포트 불필요)

🔴 **왜 로컬 훅과 CI 가 하는 일이 다른가**
-------------------------------------------
대조에는 실행 리포트가 필요하고, 그걸 만들려면 **스택 기동 + 전체 E2E(실측 1.8분)** 가 든다.
매 push 마다 그러면 **사람이 훅을 끈다** — 그러면 검출률이 0 이 된다(`QUALITY_GATES` §2-8).
그렇다고 *"리포트 없으면 통과"* 는 fail-open 이라 이 저장소가 금지한다(§2-5-1).

그래서 **훅과 CI 가 각각 자기가 fail-closed 로 답할 수 있는 질문만** 맡는다:

===========  ====================================  ===========================
층            묻는 것                                필요한 것
===========  ====================================  ===========================
`pre-push`   E2E **설정이 온전한가**                 설정 파일과 스펙 파일뿐
CI           **돈 테스트가 바닥값 이상인가**          실행 리포트
===========  ====================================  ===========================

선례 = `check_coverage_baseline.py` (1구간에서 같은 충돌을 같은 방법으로 풀었다).
"""

import json
from pathlib import Path
import sys

# 한글·이모지를 인쇄하므로 Windows cp949 콘솔에서 죽지 않게 먼저 방어한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
FE_DIR = REPO_ROOT / "medication-frontend"
E2E_DIR = FE_DIR / "e2e"
CONFIG_PATH = FE_DIR / "playwright.config.js"
REPORT_PATH = FE_DIR / "playwright-report.json"

# 🔑 실측값이다. 어림잡지 않는다 — 1구간에서 바닥값을 150 으로 어림잡았다가
#    실측 148 에 게이트가 **자기 첫 실행에서 자기를 막았다**(완료기록 §4).
#    2026-09-22 실측: `npx playwright test --list` → "61 tests in 14 files".
MIN_E2E_TESTS = 61
MIN_SPEC_FILES = 12


# ── ① pre-push — E2E 설정이 온전한가 ──────────────────────────────────
# 흐름: 설정 파일 존재 -> json 리포터 선언 -> 스펙 파일 수 바닥값
# 이 층은 **테스트를 돌리지 않는다.** 돌리려면 스택과 1.8분이 필요한데,
# 매 push 마다 그러면 사람이 훅을 끈다. 대신 «CI 가 셀 수 있게 돼 있는가» 만 묻는다.
def verify() -> int:
    """E2E 설정 산출물만 검사한다 (리포트 불필요).

    Returns:
        종료코드 — 0 이면 통과.
    """
    problems: list[str] = []

    if not CONFIG_PATH.exists():
        problems.append(f"설정이 없다: {CONFIG_PATH.relative_to(REPO_ROOT).as_posix()}")
    else:
        config = CONFIG_PATH.read_text(encoding="utf-8", errors="replace")
        if "'json'" not in config and '"json"' not in config:
            problems.append(
                "`playwright.config.js` 에 **json 리포터가 없다** — 리포트가 없으면 "
                "CI 가 실행 건수를 셀 수 없고, 그러면 이 게이트가 통째로 눈이 먼다"
            )

    specs = sorted(E2E_DIR.glob("*.spec.js")) if E2E_DIR.exists() else []
    if len(specs) < MIN_SPEC_FILES:
        problems.append(
            f"E2E 스펙 파일이 **{len(specs)}개**로 바닥값 {MIN_SPEC_FILES} 아래다 — *0건이 아니라 줄어든 것도 실패다*"
        )

    if problems:
        print("❌ E2E 설정 검사 실패")
        for line in problems:
            print(f"   - {line}")
        return 1

    print(f"✅ E2E 설정 — 스펙 {len(specs)}개(바닥값 {MIN_SPEC_FILES}) · json 리포터 선언됨. **테스트는 안 돌렸다.**")
    return 0


# ── ② CI — 돈 테스트가 바닥값 이상인가 ────────────────────────────────
# 흐름: 리포트 존재(없으면 실패) -> stats 읽기 -> 실행 수 = expected+unexpected+flaky
#       -> 바닥값 대조 -> 실패 0 대조
# 🔴 리포트 부재를 통과로 읽지 않는다 — 그게 fail-open 의 본체다.
def check() -> int:
    """실행 리포트를 바닥값과 대조한다.

    Returns:
        종료코드 — 0 이면 통과.
    """
    if not REPORT_PATH.exists():
        print(f"❌ 실행 리포트가 없다: {REPORT_PATH.relative_to(REPO_ROOT).as_posix()}")
        print("   E2E 가 돌지 않았거나 리포터가 꺼져 있다. **부재는 통과가 아니다**(fail-closed).")
        return 1

    stats = json.loads(REPORT_PATH.read_text(encoding="utf-8", errors="replace")).get("stats", {})
    expected = int(stats.get("expected", 0))
    unexpected = int(stats.get("unexpected", 0))
    flaky = int(stats.get("flaky", 0))
    skipped = int(stats.get("skipped", 0))
    ran = expected + unexpected + flaky

    problems: list[str] = []
    if ran < MIN_E2E_TESTS:
        problems.append(
            f"실행된 테스트가 **{ran}건**으로 바닥값 {MIN_E2E_TESTS} 아래다 — "
            "스펙이 지워졌거나 필터가 좁아졌다. *검사 범위는 조용히 줄어든다*(D31)"
        )
    if unexpected:
        problems.append(f"실패 **{unexpected}건**")
    if skipped:
        problems.append(f"skip **{skipped}건** — skip 은 실행으로 세지 않는다(한계 선언 참고)")

    if problems:
        print("❌ E2E 인벤토리 검사 실패")
        for line in problems:
            print(f"   - {line}")
        return 1

    print(f"✅ E2E 인벤토리 — 실행 {ran}건(바닥값 {MIN_E2E_TESTS}) · 실패 0 · skip 0 · flaky {flaky}.")
    return 0


def main() -> int:
    """서브커맨드를 고른다.

    Returns:
        종료코드.
    """
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "verify":
        return verify()
    if mode == "check":
        return check()
    print(f"알 수 없는 서브커맨드: {mode} (check | verify)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
