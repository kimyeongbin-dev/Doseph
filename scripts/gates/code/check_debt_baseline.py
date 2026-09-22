"""코드 부채에 **천장**을 씌운다 — 줄지는 몰라도 **늘지는 못한다**.

왜 이 게이트가 있나
-------------------
`CLAUDE.md` 가 요구하는데 **Ruff 가 안 잡던 규칙**을 켜는 중이다(트랙 B-11 S2).
*"규칙을 문서에서 내리려면 먼저 기계가 잡아야 한다"* — 강제 없는 규칙을 내리면
**그냥 사라지기** 때문이다.

그런데 위반이 **0건이 아닌** 규칙은 그냥 켤 수 없다. 두 가지 길이 있는데 하나는 틀렸다::

    ❌ noqa 로 덮는다      만료가 없다 -> 영구 누락 (사용자 지적, 2026-09-22)
    ✅ 천장을 씌운다        건수가 보이고, 줄어들 수만 있다

`mypy_gate.py` · `check_coverage_baseline.py` 가 이미 쓰는 방식이고 이 게이트는 그 이식이다.
**Ruff 에는 baseline 기능이 없어서** 직접 센다.

무엇을 재나
-----------
======================  ======  ==========================================
측정                     천장    `CLAUDE.md` 조항
======================  ======  ==========================================
``ANN401``                  30  §8.3 ``Any`` 회피
``PLC0415``                 26  §8.5 top-level import 강제
300줄 초과 생산 파일         13  §4.2 파일이 300줄을 넘으면 분할
======================  ======  ==========================================

🔴 **천장은 «허용치» 가 아니라 «지금 값» 이다.** 줄면 **손으로 내린다** —
내리는 행위가 곧 *"의식적으로 갚았다"* 는 기록이 된다.

⚠️ 세는 대상을 좁힌 근거 (D43 — «몇 건인가» 는 질문이 덜 된 질문이다)
--------------------------------------------------------------------
- ``PLC0415`` 는 전체 **145건**이지만 그중 **119건이 테스트**다. 테스트 안의 지역 import 는
  **관용**이라(환경 조작 후 import · 지연 import 검증) `per-file-ignores` 로 면제했다.
  여기서 세는 **26건이 생산 코드**이고, §8.5 가 실제로 거짓인 횟수다.
- 300줄 초과는 ``app`` + ``ai_worker`` 전체로 세면 **18개**지만 그중 **5개가 테스트**다
  (seed 데이터·긴 시나리오). §4.2 는 *모듈 분할*에 관한 규칙이라 **생산 코드 13개**만 센다.

🔴 이 게이트가 **못** 하는 것
-----------------------------
- **어느 위반이 정당한지 모른다.** 천장은 총량만 본다 — 한 건을 고치고 다른 한 건을
  새로 만들면 통과한다. 그래서 **줄면 천장을 내려** 그 구멍을 좁힌다.
- **`noqa` 로 덮은 것은 애초에 안 세어진다** — 그건 `QA-51` 이 따로 든다.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.injection_harness import REPO_ROOT, ruff_count

#: 천장 — **지금 값**이다. 줄면 손으로 내린다(내리는 것이 곧 «갚았다» 는 기록).
RUFF_CEILINGS: dict[str, int] = {
    "ANN401": 30,
    "PLC0415": 26,
}

#: `CLAUDE.md` §4.2 — 파일이 이 줄 수를 넘으면 분할을 검토한다.
MAX_FILE_LINES = 300

#: 300줄을 넘는 **생산** 파일 수의 천장.
FILE_CEILING = 13

#: 생산 코드로 치는 최상위 폴더.
PROD_ROOTS = ("app", "ai_worker")


# ── 300줄 초과 생산 파일 세기 ────────────────────────────────────────
# 흐름: app·ai_worker 의 .py 수집 -> 테스트·마이그레이션 제외 -> 줄 수 비교
def oversized_files() -> list[tuple[int, str]]:
    """300줄을 넘는 생산 파이썬 파일을 (줄 수, 경로)로 돌려준다.

    Returns:
        줄 수 내림차순 목록.
    """
    found: list[tuple[int, str]] = []
    for root in PROD_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            parts = path.relative_to(REPO_ROOT).parts
            if "migrations" in parts or "tests" in parts:
                continue
            lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            if lines > MAX_FILE_LINES:
                found.append((lines, path.relative_to(REPO_ROOT).as_posix()))
    return sorted(found, reverse=True)


# ── 판정 ─────────────────────────────────────────────────────────────
# 흐름: 각 측정 -> 천장 대조 -> 초과는 차단 / 미달은 «내려라» 보고
# 🔴 fail-closed: 측정 자체가 실패하면(None) «깨끗하다» 가 아니라 «못 쟀다» 이므로 막는다.
def main() -> int:
    """부채 측정값을 천장과 대조하고 결과를 인쇄한다.

    Returns:
        종료코드 — 천장을 넘거나 측정에 실패하면 1.
    """
    problems: list[str] = []
    lowered: list[str] = []
    measured: list[str] = []

    for rule, ceiling in RUFF_CEILINGS.items():
        count = ruff_count(rule, no_cache=False)
        if count is None:
            problems.append(f"{rule}: 측정 실패 — 「깨끗하다」가 아니라 「못 쟀다」이다(fail-closed)")
            continue
        measured.append(f"{rule} {count}/{ceiling}")
        if count > ceiling:
            problems.append(f"{rule}: {count}건 > 천장 {ceiling} — 새 위반이 들어왔다")
        elif count < ceiling:
            lowered.append(f"{rule}: {count} < {ceiling} — 갚았으면 천장을 {count} 로 내려라")

    oversized = oversized_files()
    measured.append(f"300줄초과 {len(oversized)}/{FILE_CEILING}")
    if len(oversized) > FILE_CEILING:
        newest = ", ".join(f"{p}({n}줄)" for n, p in oversized[:3])
        problems.append(f"300줄 초과 생산 파일 {len(oversized)}개 > 천장 {FILE_CEILING} — 예: {newest}")
    elif len(oversized) < FILE_CEILING:
        lowered.append(f"300줄초과: {len(oversized)} < {FILE_CEILING} — 천장을 내려라")

    if problems:
        print("[거부] 코드 부채가 천장을 넘었다.")
        for item in problems:
            print(f"  - {item}")
        print("\n  천장은 「허용치」가 아니라 「지금 값」이다. 늘리려면 근거가 필요하다.")
        return 1

    print(f"✅ 코드 부채 천장 — {' · '.join(measured)}.")
    for item in lowered:
        print(f"   🟢 {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
